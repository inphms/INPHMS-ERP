from __future__ import annotations
import re
import functools
import logging
import uuid
import os
import textwrap

from lxml import etree
from rjsmin import jsmin as rjsmin
from contextlib import closing
from subprocess import PIPE, Popen

from inphms.tools.json import scriptsafe as json
from inphms.tools import file_open, file_path, find_in_path, profiler

_logger = logging.getLogger(__name__)


#########
# CONST #
#########
EXTENSIONS = (".js", ".css", ".scss", ".sass", ".less", ".xml")
ANY_UNIQUE = '_' * 7

#############
# EXCEPTION #
#############

class AssetError(Exception):
    pass

class AssetNotFound(AssetError):
    pass

class CompileError(RuntimeError):
    pass

class XMLAssetError(Exception):
    pass


################
# CLASS HELPER #
################

class WebAsset(object):
    _content = None
    _filename = None
    _ir_attach = None
    _id = None

    def __init__(self, bundle, inline=None, url=None, filename=None, last_modified=None):
        self.bundle = bundle
        self.inline = inline
        self._filename = filename
        self.url = url
        self._last_modified = last_modified
        if not inline and not url:
            raise Exception("An asset should either be inlined or url linked, defined in bundle '%s'" % bundle.name)

    def generate_error(self, msg):
        msg = f'{msg!r} in file {self.url!r}'
        _logger.error(msg)  # log it in the python console in all cases.
        return msg

    @functools.cached_property
    def id(self):
        if self._id is None:
            self._id = str(uuid.uuid4())
        return self._id

    @functools.cached_property
    def unique_descriptor(self):
        return f'{self.url or self.inline},{self.last_modified}'

    @functools.cached_property
    def name(self):
        return '<inline asset>' if self.inline else self.url

    def stat(self):
        if not (self.inline or self._filename or self._ir_attach):
            try:
                # Test url against ir.attachments
                self._ir_attach = self.bundle.env['ir.attachment'].sudo()._get_serve_attachment(self.url)
                self._ir_attach.ensure_one()
            except ValueError:
                raise AssetNotFound("Could not find %s" % self.name)

    @property
    def last_modified(self):
        if self._last_modified is None:
            try:
                self.stat()
            except Exception:  # most likely nor a file or an attachment, skip it
                pass
            if self._filename and self.bundle.is_debug_assets:  # usually _last_modified should be set exept in debug=assets
                self._last_modified = os.path.getmtime(self._filename)
            elif self._ir_attach:
                self._last_modified = self._ir_attach.write_date.timestamp()
            if not self._last_modified:
                self._last_modified = -1
        return self._last_modified

    @property
    def content(self):
        if self._content is None:
            self._content = self.inline or self._fetch_content()
        return self._content

    def _fetch_content(self):
        """ Fetch content from file or database"""
        try:
            self.stat()
            if self._filename:
                with closing(file_open(self._filename, 'rb', filter_ext=EXTENSIONS)) as fp:
                    return fp.read().decode('utf-8')
            else:
                return self._ir_attach.raw.decode()
        except UnicodeDecodeError:
            raise AssetError('%s is not utf-8 encoded.' % self.name)
        except IOError:
            raise AssetNotFound('File %s does not exist.' % self.name)
        except:  # noqa: E722
            raise AssetError('Could not get content for %s.' % self.name)

    def minify(self):
        return self.content

    def with_header(self, content=None):
        if content is None:
            content = self.content
        return f'\n/* {self.name} */\n{content}'


class StylesheetAsset(WebAsset):
    rx_import = re.compile(r"""@import\s+('|")(?!'|"|/|https?://)""", re.U)
    rx_url = re.compile(r"""(?<!")url\s*\(\s*('|"|)(?!'|"|/|https?://|data:|#{str)""", re.U)
    rx_sourceMap = re.compile(r'(/\*# sourceMappingURL=.*)', re.U)
    rx_charset = re.compile(r'(@charset "[^"]+";)', re.U)

    def __init__(self, *args, rtl=False, autoprefix=False, **kw):
        self.rtl = rtl
        self.autoprefix = autoprefix
        super().__init__(*args, **kw)

    @property
    def bundle_version(self):
        return self.bundle.get_version('css')

    @functools.cached_property
    def unique_descriptor(self):
        direction = (self.rtl and 'rtl') or 'ltr'
        autoprefixed = (self.autoprefix and 'autoprefixed') or ''
        return f'{self.url or self.inline},{self.last_modified},{direction},{autoprefixed}'

    def _fetch_content(self):
        try:
            content = super()._fetch_content()
            web_dir = os.path.dirname(self.url)

            if self.rx_import:
                content = self.rx_import.sub(
                    r"""@import \1%s/""" % (web_dir,),
                    content,
                )

            if self.rx_url:
                content = self.rx_url.sub(
                    r"url(\1%s/" % (web_dir,),
                    content,
                )

            if self.rx_charset:
                # remove charset declarations, we only support utf-8
                content = self.rx_charset.sub('', content)

            return content
        except AssetError as e:
            self.bundle.css_errors.append(str(e))
            return ''

    def get_source(self):
        content = self.inline or self._fetch_content()
        return "/*! %s */\n%s" % (self.id, content)

    def minify(self):
        # remove existing sourcemaps, make no sense after re-mini
        content = self.rx_sourceMap.sub('', self.content)
        # comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.S)
        # space
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r' *([{}]) *', r'\1', content)
        return self.with_header(content)


class PreprocessedCSS(StylesheetAsset):
    rx_import = None

    def get_command(self):
        raise NotImplementedError

    def compile(self, source):
        command = self.get_command()
        try:
            compiler = Popen(command, stdin=PIPE, stdout=PIPE,
                             stderr=PIPE, encoding='utf-8')
        except Exception:
            raise CompileError("Could not execute command %r" % command[0])

        out, err = compiler.communicate(input=source)
        if compiler.returncode:
            cmd_output = out + err
            if not cmd_output:
                cmd_output = u"Process exited with return code %d\n" % compiler.returncode
            raise CompileError(cmd_output)
        return out


class JavascriptAsset(WebAsset):

    def __init__(self, bundle, **kwargs):
        super().__init__(bundle, **kwargs)
        self._is_transpiled = None
        self._converted_content = None

    def generate_error(self, msg):
        msg = super().generate_error(msg)
        return f'console.error({json.dumps(msg)});'

    @property
    def bundle_version(self):
        return self.bundle.get_version('js')

    @property
    def is_transpiled(self):
        if self._is_transpiled is None:
            from inphms.tools.js_transpiler import is_inphms_module  # noqa: PLC0415
            self._is_transpiled = bool(is_inphms_module(self.url, super().content))
        return self._is_transpiled

    @property
    def content(self):
        content = super().content
        if self.is_transpiled:
            if not self._converted_content:
                from inphms.tools.js_transpiler import transpile_javascript  # noqa: PLC0415
                self._converted_content = transpile_javascript(self.url, content)
            return self._converted_content
        return content

    def minify(self):
        return self.with_header(rjsmin(self.content))

    def _fetch_content(self):
        try:
            return super()._fetch_content()
        except AssetError as e:
            return self.generate_error(str(e))


    def with_header(self, content=None, minimal=True):
        if minimal:
            return super().with_header(content)

        # format the header like
        #   /**************************
        #   *  Filepath: <asset_url>  *
        #   *  Lines: 42              *
        #   **************************/
        line_count = content.count('\n')
        lines = [
            f"Filepath: {self.url}",
            f"Lines: {line_count}",
        ]
        length = max(map(len, lines))
        return "\n".join([
            "",
            "/" + "*" * (length + 5),
            *(f"*  {line:<{length}}  *" for line in lines),
            "*" * (length + 5) + "/",
            content,
        ])


class XMLAsset(WebAsset):
    def _fetch_content(self):
        try:
            content = super()._fetch_content()
        except AssetError as e:
            return self.generate_error(str(e))

        parser = etree.XMLParser(ns_clean=True, remove_comments=True, resolve_entities=False)
        try:
            root = etree.fromstring(content.encode('utf-8'), parser=parser)
        except etree.XMLSyntaxError as e:
            return self.generate_error(f'Invalid XML template: {e.msg}')
        if root.tag in ('templates', 'template'):
            return ''.join(etree.tostring(el, encoding='unicode') for el in root)
        return etree.tostring(root, encoding='unicode')

    def generate_error(self, msg):
        msg = super().generate_error(msg)
        raise XMLAssetError(msg)

    @property
    def bundle_version(self):
        return self.bundle.get_version('js')

    def with_header(self, content=None):
        if content is None:
            content = self.content

        # format the header like
        #   <!--=========================-->
        #   <!--  Filepath: <asset_url>  -->
        #   <!--  Bundle: <name>         -->
        #   <!--  Lines: 42              -->
        #   <!--=========================-->
        line_count = content.count('\n')
        lines = [
            f"Filepath: {self.url}",
            f"Lines: {line_count}",
        ]
        length = max(map(len, lines))
        return "\n".join([
            "",
            "<!--  " + "=" * length + "  -->",
            *(f"<!--  {line:<{length}}  -->" for line in lines),
            "<!--  " + "=" * length + "  -->",
            content,
        ])

##################
# CLASS HELPER 2 #
##################

class SassStylesheetAsset(PreprocessedCSS):
    rx_indent = re.compile(r'^( +|\t+)', re.M)
    indent = None
    reindent = '    '

    def minify(self):
        return self.with_header()

    def get_source(self):
        content = textwrap.dedent(self.inline or self._fetch_content())

        def fix_indent(m):
            # Indentation normalization
            ind = m.group()
            if self.indent is None:
                self.indent = ind
                if self.indent == self.reindent:
                    # Don't reindent the file if identation is the final one (reindent)
                    raise StopIteration()
            return ind.replace(self.indent, self.reindent)

        try:
            content = self.rx_indent.sub(fix_indent, content)
        except StopIteration:
            pass
        return "/*! %s */\n%s" % (self.id, content)

    def get_command(self):
        try:
            sass = find_in_path('sass')
        except IOError:
            sass = 'sass'
        return [sass, '--stdin', '-t', 'compressed', '--unix-newlines', '--compass',
                '-r', 'bootstrap-sass']


class ScssStylesheetAsset(PreprocessedCSS):
    @property
    def bootstrap_path(self):
        return file_path('web/static/lib/bootstrap/scss')

    precision = 8
    output_style = 'expanded'

    def compile(self, source):
        try:
            import sass as libsass  # noqa: PLC0415
        except ModuleNotFoundError:
            return super().compile(source)

        def scss_importer(path, *args):
            *parent_path, file = os.path.split(path)
            try:
                parent_path = file_path(os.path.join(*parent_path))
            except FileNotFoundError:
                parent_path = file_path(os.path.join(self.bootstrap_path, *parent_path))
            return [(os.path.join(parent_path, file),)]

        try:
            profiler.force_hook()
            return libsass.compile(
                string=source,
                include_paths=[
                    self.bootstrap_path,
                ],
                importers=[(0, scss_importer)],
                output_style=self.output_style,
                precision=self.precision,
            )
        except libsass.CompileError as e:
            raise CompileError(e.args[0])

    def get_command(self):
        try:
            sassc = find_in_path('sassc')
        except IOError:
            sassc = 'sassc'
        return [sassc, '--stdin', '--precision', str(self.precision), '--load-path', self.bootstrap_path, '-t', self.output_style]


class LessStylesheetAsset(PreprocessedCSS):
    def get_command(self):
        try:
            if os.name == 'nt':
                lessc = find_in_path('lessc.cmd')
            else:
                lessc = find_in_path('lessc')
        except IOError:
            lessc = 'lessc'
        return [lessc, '-', '--no-js', '--no-color']
