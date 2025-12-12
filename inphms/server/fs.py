from __future__ import annotations
import re
import os
import contextlib
import glob
import collections
import json
import base64
import time
from hashlib import sha512
from datetime import datetime
from os.path import getmtime, isfile, join as opj, isdir, dirname as osdirname, normpath


from .utils import SESSION_DELETION_TIMER, STORED_SESSION_BYTES, SESSION_LIFETIME, request, get_default_session
from inphms.tools._vendor import sessions
from inphms.service import security


_base64_urlsafe_re = re.compile(r'^[A-Za-z0-9_-]{84}$')
_session_identifier_re = re.compile(r'^[A-Za-z0-9_-]{%s}$' % STORED_SESSION_BYTES)


class FilesystemSessionStore(sessions.FilesystemSessionStore):
    """ Place where to load and save session objects. """
    def get_session_filename(self, sid):
        # scatter sessions across 4096 (64^2) directories
        if not self.is_valid_key(sid):
            raise ValueError(f'Invalid session id {sid!r}')
        sha_dir = sid[:2]
        dirname = opj(self.path, sha_dir)
        session_path = opj(dirname, sid)
        return session_path

    def save(self, session):
        session_path = self.get_session_filename(session.sid)
        dirname = osdirname(session_path)
        if not isdir(dirname):
            with contextlib.suppress(OSError):
                os.mkdir(dirname, 0o0755)
        super().save(session)

    def delete_old_sessions(self, session):
        if 'gc_previous_sessions' in session:
            if session['create_time'] + SESSION_DELETION_TIMER < time.time():
                self.delete_from_identifiers([session.sid[:STORED_SESSION_BYTES]])
                del session['gc_previous_sessions']
                self.save(session)

    def get(self, sid):
        # retro compatibility
        old_path = super().get_session_filename(sid)
        session_path = self.get_session_filename(sid)
        if isfile(old_path) and not isfile(session_path):
            dirname = osdirname(session_path)
            if not isdir(dirname):
                with contextlib.suppress(OSError):
                    os.mkdir(dirname, 0o0755)
            with contextlib.suppress(OSError):
                os.rename(old_path, session_path)
        session = super().get(sid)
        return session

    def rotate(self, session, env, soft=False):
        if soft:
            static = session.sid[:STORED_SESSION_BYTES]
            recent_session = self.get(session.sid)
            if 'next_sid' in recent_session:
                session.sid = recent_session['next_sid']
                return
            next_sid = static + self.generate_key()[STORED_SESSION_BYTES:]
            session['next_sid'] = next_sid
            session['deletion_time'] = time.time() + SESSION_DELETION_TIMER
            self.save(session)
            # Now prepare the new session
            session['gc_previous_sessions'] = True
            session.sid = next_sid
            del session['deletion_time']
            del session['next_sid']
        else:
            self.delete(session)
            session.sid = self.generate_key()
        if session.uid and env:
            session.session_token = security.compute_session_token(session, env)
        session.should_rotate = False
        session['create_time'] = time.time()
        self.save(session)

    def vacuum(self, max_lifetime=SESSION_LIFETIME):
        from . import root
        threshold = time.time() - max_lifetime
        for fname in glob.iglob(opj(root.session_store.path, '*', '*')):
            path = opj(root.session_store.path, fname)
            with contextlib.suppress(OSError):
                if getmtime(path) < threshold:
                    os.unlink(path)

    def generate_key(self, salt=None):
        key = str(time.time()).encode() + os.urandom(64)
        hash_key = sha512(key).digest()[:-1]  # prevent base64 padding
        return base64.urlsafe_b64encode(hash_key).decode('utf-8')

    def is_valid_key(self, key):
        return _base64_urlsafe_re.match(key) is not None

    def get_missing_session_identifiers(self, identifiers):
        identifiers = set(identifiers)
        directories = {normpath(opj(self.path, identifier[:2]))
                       for identifier in identifiers}
        # Remove the identifiers for which a file is present on the filesystem.
        for directory in directories:
            with contextlib.suppress(OSError), os.scandir(directory) as session_files:
                identifiers.difference_update(sf.name[:42] for sf in session_files)
        return identifiers

    def delete_from_identifiers(self, identifiers: list):
        files_to_unlink = []
        for identifier in identifiers:
            # Avoid to remove a session if it does not match an identifier.
            # This prevent malicious user to delete sessions from a different
            # database by specifying a custom ``res.device.log``.
            if not _session_identifier_re.match(identifier):
                raise ValueError("Identifier format incorrect, did you pass in a string instead of a list?")
            normalized_path = normpath(opj(self.path, identifier[:2], identifier + '*'))
            if normalized_path.startswith(self.path):
                files_to_unlink.extend(glob.glob(normalized_path))
        for fn in files_to_unlink:
            with contextlib.suppress(OSError):
                os.unlink(fn)


class Session(collections.abc.MutableMapping):
    """ Structure containing data persisted across requests. """
    __slots__ = ('can_save', '_Session__data', 'is_dirty', 'is_new',
                 'should_rotate', 'sid')

    def __init__(self, data, sid, new=False):
        self.can_save = True
        self.__data = {}
        self.update(data)
        self.is_dirty = False
        self.is_new = new
        self.should_rotate = False
        self.sid = sid

    def __getitem__(self, item):
        return self.__data[item]

    def __setitem__(self, item, value):
        value = json.loads(json.dumps(value))
        if item not in self.__data or self.__data[item] != value:
            self.is_dirty = True
        self.__data[item] = value

    def __delitem__(self, item):
        del self.__data[item]
        self.is_dirty = True

    def __len__(self):
        return len(self.__data)

    def __iter__(self):
        return iter(self.__data)

    def clear(self):
        self.__data.clear()
        self.is_dirty = True

    #
    # Session properties
    #
    @property
    def uid(self):
        return self.get('uid')

    @uid.setter
    def uid(self, uid):
        self['uid'] = uid

    @property
    def db(self):
        return self.get('db')

    @db.setter
    def db(self, db):
        self['db'] = db

    @property
    def login(self):
        return self.get('login')

    @login.setter
    def login(self, login):
        self['login'] = login

    @property
    def context(self):
        return self.get('context')

    @context.setter
    def context(self, context):
        self['context'] = context

    @property
    def debug(self):
        return self.get('debug')

    @debug.setter
    def debug(self, debug):
        self['debug'] = debug

    @property
    def session_token(self):
        return self.get('session_token')

    @session_token.setter
    def session_token(self, session_token):
        self['session_token'] = session_token

    #
    # Session methods
    #
    def authenticate(self, env, credential):
        wsgienv = {'interactive': True,
                   'base_location': request.httprequest.url_root.rstrip('/'),
                   'HTTP_HOST': request.httprequest.environ['HTTP_HOST'],
                   'REMOTE_ADDR': request.httprequest.environ['REMOTE_ADDR'],}
        env = env(user=None, su=False)
        auth_info = env['res.users'].authenticate(credential, wsgienv)
        pre_uid = auth_info['uid']

        self.uid = None
        self['pre_login'] = credential['login']
        self['pre_uid'] = pre_uid

        env = env(user=pre_uid)

        # if 2FA is disabled we finalize immediately
        user = env['res.users'].browse(pre_uid)
        if auth_info.get('mfa') == 'skip' or not user._mfa_url():
            self.finalize(env)

        if request and request.session is self and request.db == env.registry.db_name:
            request.env = env(user=self.uid, context=self.context)

        return auth_info

    def finalize(self, env):
        """ Finalizes a partial session, should be called on MFA validation
            to convert a partial / pre-session into a logged-in one.
        """
        login = self.pop('pre_login')
        uid = self.pop('pre_uid')

        env = env(user=uid)
        user_context = dict(env['res.users'].context_get())

        self.should_rotate = True
        self.update({
            'db': env.registry.db_name,
            'login': login,
            'uid': uid,
            'context': user_context,
            'session_token': env.user._compute_session_token(self.sid),
        })

    def logout(self, keep_db=False):
        db = self.db if keep_db else get_default_session()['db']  # None
        debug = self.debug
        self.clear()
        self.update(get_default_session(), db=db, debug=debug)
        self.should_rotate = True

        if request and request.env:
            request.env['ir.http']._post_logout()

    def touch(self):
        self.is_dirty = True

    def update_trace(self, request):
        """ :return: dict if a device log has to be inserted, ``None`` otherwise
        """
        if self.get('_trace_disable'):
            # To avoid generating useless logs, e.g. for automated technical sessions,
            # a session can be flagged with `_trace_disable`. This should never be done
            # without a proper assessment of the consequences for auditability.
            # Non-admin users have no direct or indirect way to set this flag, so it can't
            # be abused by unprivileged users. Such sessions will of course still be
            # subject to all other auditing mechanisms (server logs, web proxy logs,
            # metadata tracking on modified records, etc.)
            return

        user_agent = request.httprequest.user_agent
        platform = user_agent.platform
        browser = user_agent.browser
        ip_address = request.httprequest.remote_addr
        now = int(datetime.now().timestamp())
        for trace in self['_trace']:
            if trace['platform'] == platform and trace['browser'] == browser and trace['ip_address'] == ip_address:
                # If the device logs are not up to date (i.e. not updated for one hour or more)
                if bool(now - trace['last_activity'] >= 3600):
                    trace['last_activity'] = now
                    self.is_dirty = True
                    return trace
                return
        new_trace = {
            'platform': platform,
            'browser': browser,
            'ip_address': ip_address,
            'first_activity': now,
            'last_activity': now
        }
        self['_trace'].append(new_trace)
        self.is_dirty = True
        return new_trace

    def _delete_old_sessions(self):
        from . import root
        root.session_store.delete_old_sessions(self)
