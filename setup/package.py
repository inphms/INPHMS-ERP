#!/usr/bin/env python3

import os
import sys
import argparse
import logging
import time
import traceback
import shutil
import tempfile
import subprocess

import pexpect

from glob import glob
from datetime import datetime
from pathlib import Path
from xmlrpc import client as xmlrpclib


#
# UTILS
# 
ROOTDIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
TSTAMP = time.strftime("%U%m%d", time.gmtime())
TSEC = time.strftime("%H%M%S", time.gmtime())

# Get some vars from release.py
VERSION = ...
exec(open(os.path.join(ROOTDIR, 'inphms', 'release.py'), 'rb').read())
VERSION = VERSION.split('-')[0].replace('saas~', '')
DOCKERVERSION = VERSION.replace('+', '')
INSTALL_TIMEOUT = 600
GPGID = os.getenv("GPGID")
GPGPASSPHRASE = os.getenv("GPGPASSPHRASE")

DOCKERUSER = """
RUN mkdir /var/lib/inphms && \
    groupadd -g %(group_id)s inphms && \
    useradd -u %(user_id)s -g inphms inphms -d /var/lib/inphms && \
    mkdir /data && \
    chown inphms:inphms /var/lib/inphms /data
USER inphms
""" % {'group_id': os.getgid(), 'user_id': os.getuid()}


class InphmsTestTimeoutError(Exception):
    pass

class InphmsTestError(Exception):
    pass


def run_cmd(cmd, chdir=None, timeout=None):
    logging.info("Running command: '%s'", ' '.join(cmd))
    return subprocess.run(cmd, cwd=chdir, timeout=timeout)


def _rpc_count_modules(addr="http:127.0.0.1", port=8888, dbname="testdb"):
    server_uri = '%s:%s/xmlrpc/2/' % (addr, port)
    uid = xmlrpclib.ServerProxy(server_uri + 'common').authenticate(
        dbname, 'admin', 'admin', {}
    )
    modules = xmlrpclib.ServerProxy(server_uri + 'object').execute(
        dbname, uid, 'admin', 'ir.module.module', 'search', [('state', '=', 'installed')]
    )
    if len(modules) > 1:
        toinstallmods = xmlrpclib.ServerProxy(server_uri + 'object').execute(
            dbname, uid, 'admin', 'ir.module.module', 'search', [('state', '=', 'to install')]
        )
        if toinstallmods:
            logging.error("Package test: FAILED. not able to install dependancies of base.")
            raise InphmsTestError("Installation of package failed")
        else:
            logging.info("Package test: successfuly installed %s modules" % len(modules))
    else:
        logging.error("Package test: FAILED. Not able to install base.")
        raise InphmsTestError("Package test: FAILED. Not able to install base.")


def publish(args, pub_type, extensions):
    """
    Publush build package (move build files and generate a symlink to the latests)
    
    :param args: parsed program arguments
    :param pub_type: oneof [deb, exe]
    :param extensions: list of extensions to publish
    :returns: published files
    """
    def _publish(release):
        build_path = os.path.join(args.build_dir, release)
        filename = release.split(os.path.sep)[-1]
        release_dir = os.path.join(args.pub, pub_type)
        release_path = os.path.join(release_dir, filename)
        os.renames(build_path, release_path)

        # Latest/symlink handler
        release_abspath = os.path.abspath(release_path)
        latest_abspath = release_abspath.replace(TSTAMP, 'latest')
        
        if os.path.islink(latest_abspath):
            os.unlink(latest_abspath)
        os.symlink(release_abspath, latest_abspath)

        return release_path

    published = []
    for ext in extensions:
        release = glob("%s/inphms_*.%s" % (args.build_dir, ext))
        if release:
            published.append(_publish(release[0]))
    return published


# 
# Generate packages, sources and release files of debian package
#
def generate_deb_package(args, published_files):
    # Exec command to produce file_name in path, and moves it to args.pub/deb
    def _generate_file(args, command, filename, path):
        cur_tmp_filepath = os.path.join(path, filename)
        with open(cur_tmp_filepath, 'w') as out:
            subprocess.call(command, stdout=out, cwd=path)
        shutil.copy(cur_tmp_filepath, os.path.join(args.pub, 'deb', filename))

    # Copy files to temp dir (is a must because the working dir must contain only the
    # files of the last release)
    temp_path = tempfile.mkdtemp(suffix='debPackages')
    for pub_file_path in published_files:
        shutil.copy(pub_file_path, temp_path)

    commands = [
        (['dpkg-scanpackages', '--multiversion', '.'], "Packages"), # Generate Packages files
        (['dpkg-scansources', '.'], "Sources"), # Generate Sources file
        (['apt-ftparchive', 'release', '.'], "Release") # Generate Release file
    ]
    # Genereate files
    for command in commands:
        _generate_file(args, command[0], command[-1], temp_path)
    
    # Remove temp dir
    shutil.rmtree(temp_path)

    if args.sign:
        # Generate Release.gpg (= signed Release)
        # Options -abs: -a (Create ASCII armored output),
        #   -b (Make detach signature),
        #   -s (Make a signature)
        # handle in a more secure way.
        try:
            process = subprocess.Popen([
                'gpg',
                '--default-key', GPGID,
                '--passphrase-fd','0',
                '--yes',
                '-abs',
                '--no-tty',
                '-o', 'Release.gpg',
                'Release'
            ], cwd=os.path.join(args.pub, 'deb'),
               stdin=subprocess.PIPE,
               stdout=subprocess.PIPE,
               stderr=subprocess.PIPE,
               text=True)
            stdout, stderr = process.communicate(input=GPGPASSPHRASE)
        except Exception as e:
            logging.error("Signing debian  packages failed %s" % str(e))



def _prepare_build_dir(args, win32=False, move_addons=True):
    """
    Copy files to the build directory.
    """
    logging.info("Preparing build dir '%s'", args.build_dir)
    cmd = ['rsync', '-a', '--delete', '--exclude', '.git', '--exclude', '*.pyc', '--exclude', '*.pyo']
    if win32 is False:
        cmd += ['--exclude', 'setup/win32']
    
    run_cmd(cmd + ['%s/' % args.inphms_dir, args.build_dir])
    if not move_addons:
        return
    for addon_path in glob(os.path.join(args.build_dir, 'addons/*')):
        if args.blacklist is None or os.path.basename(addon_path) not in args.blacklist:
            try:
                shutil.move(addon_path, os.path.join(args.build_dir, 'inphms/addons'))
            except shutil.Error as e:
                logging.warning("Shutil Error: '%s'\n while moving: '%s'", e, addon_path)
                if addon_path.startswith(args.build_dir) and os.path.isdir(addon_path):
                    logging.info("Removing '{}'".format(addon_path))
                    try:
                        shutil.rmtree(addon_path)
                    except shutil.Error as rm_error:
                        logging.warning("Cannot remove '{}': {}".format(addon_path, rm_error))


#
# DOCKER
#
class Docker():
    """ Docker class Mixin, must be inherited by specific Docker builder class."""
    arch = None

    def __init__(self, args):
        self.args = args
        self.tag = 'inphms-%s-%s-nightly-tests' % (DOCKERVERSION, self.arch)
        self.container_name = None
        self.exposed_port = None
        docker_templates = {
            'deb': os.path.join(args.build_dir, 'setup/package.dfdebian')
        }
        self.docker_template = Path(docker_templates[self.arch]).read_text(encoding='utf-8').replace("USER inphms", DOCKERUSER)
        self.test_log_file = '/data/src/test-%s.log' % self.arch
        self.docker_dir = Path(self.args.build_dir) / 'docker'
        if not self.docker_dir.exists():
            self.docker_dir.mkdir()
        self.build_image()

    def build_image(self):
        """Build the dockerimage by copying Docker file into build_dir/docker"""
        docker_file = self.docker_dir / 'Dockerfile'
        docker_file.write_text(self.docker_template)
        shutil.copy(os.path.join(self.args.build_dir, 'requirements.txt'), self.docker_dir)
        run_cmd(["docker", 'build', '--rm=True', '-t', self.tag, '.'], chdir=self.docker_dir, timeout=1200).check_returncode()
        shutil.rmtree(self.docker_dir)

    def run(self, cmd, build_dir, container_name, user='inphms', exposed_port=None, detach=False, timeout=None):
        self.container_name = container_name
        docker_cmd = [
            "docker",
            "run",
            "--user=%s" % user,
            "--name=%s" % container_name,
            "--rm",
            "--volume=%s:/data/src" % build_dir
        ]
        if exposed_port:
            docker_cmd.extend(['-p', '127.0.0.1:%s:%s' % (exposed_port, exposed_port)])
            self.exposed_port = exposed_port
        if detach:
            docker_cmd.append('-d')
            # preserve log in case of detached docker container
            cmd = '(%s) > %s 2>&1' % (cmd, self.test_log_file)

        docker_cmd.extend([
            self.tag,
            '/bin/bash',
            '-c',
            'cd /data/src && %s' % cmd
        ])
        run_cmd(docker_cmd, timeout=timeout).check_returncode()

    def is_running(self):
        dinspect = subprocess.run(['docker', 'container', 'inspect', self.container_name], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        return True if dinspect.returncode == 0 else False

    def stop(self):
        run_cmd(["docker", "stop", self.container_name]).check_returncode()

    def test_inphms(self):
        logging.info("Starting to test Inphms install test")
        start_time = time.time()
        while self.is_running() and (time.time() - start_time) < INSTALL_TIMEOUT:
            time.sleep(5) # give some time for inphms to install and start
            if os.path.exists(os.path.join(args.build_dir, 'inphms.pid')):
                try:
                    _rpc_count_modules(port=self.exposed_port)
                    return
                finally:
                    self.stop()
        if self.is_running():
            self.stop()
            raise InphmsTestTimeoutError("Inphms pid file never appeared after %s sec." % INSTALL_TIMEOUT)
        raise InphmsTestError("Error while installing/starting Inphms after %s sec.\nSee testlogs.txt in build dir" % int(time.time() - start_time))

    def build(self):
        """ To be overriden by individual builder """
        pass

    def start_test(self):
        """ To be overriden by individual builder """
        pass

class DockerDeb(Docker):
    arch = 'deb'

    def build(self):
        logging.info("Start building debian package")
        cmds = ['sed -i "1s/^.*$/inphms (%s.%s) stable; urgency=low/" debian/changelog' % (VERSION, TSTAMP)]
        cmds.append('dpkg-buildpackage -rfakeroot -uc -us -tc')
        cmds.append("mv ../inphms_* ./")
        self.run(" && ".join(cmds), self.args.build_dir, 'inphms-debian-build-%s' % TSTAMP)
        logging.info("Finished building debian package")

    def start_test(self):
        if not self.args.test:
            return
        logging.info("Start testing debian package")
        cmds = [
            'service postgresql start',
            '/usr/bin/apt-get update -y',
            f'/usr/bin/apt-get install -y /data/src/inphms_{VERSION}.{TSTAMP}_all.deb',
            'su inphms -s /bin/bash -c "inphms -d testdb -i base --pidfile=/data/src/inphms.pid"',
        ]
        self.run(' && '.join(cmds), self.args.build_dir, 'inphms-debian-test-%s' % TSTAMP, user='root', detach=True, exposed_port=8888, timeout=300)
        self.test_inphms()
        logging.info("Finished testing debian package")



def parse_args():
    ap = argparse.ArgumentParser()
    build_dir = "%s-%s-%s" % (ROOTDIR, TSEC, TSTAMP)
    loglevels = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR, "critical": logging.CRITICAL}

    ap.add_argument("-b", '--build-dir',
                    default=build_dir,
                    help="Build directory (%s(default)s)",
                    metavar="DIR")
    ap.add_argument("-p", '--pub',
                    default=None,
                    help="publish directory %(default)s",
                    metavar="DIR")
    ap.add_argument("--logging",
                    action="store",
                    choices=list(loglevels.keys()),
                    default="info",
                    help="Logging level")
    ap.add_argument('--build-deb',
                    action='store_true')
    ap.add_argument('--build-win',
                    action="store_true")
    
    ap.add_argument('-t', '--test',
                    action='store_true',
                    default=False,
                    help="Test built packages")
    ap.add_argument('-s', '--sign',
                    action="store_true",
                    default=False,
                    help="Sign debian package / generate Rpm repo")
    ap.add_argument('--no-remove',
                    action="store_true",
                    help="don't remove build dir")
    ap.add_argument('--blacklist',
                    nargs="*",
                    help="modules to blacklist in package")
    
    parsed_args = ap.parse_args()
    logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", datefmt='%Y-%m-%d %I:%M:%S', level=loglevels[parsed_args.logging])
    parsed_args.inphms_dir = ROOTDIR
    return parsed_args

def main(args):
    try:
        if args.build_deb:
            _prepare_build_dir(args, move_addons=False)
            docker_deb = DockerDeb(args)
            docker_deb.build()
            try:
                docker_deb.start_test()
                published_files = publish(args, 'deb', ['deb', 'dsc', 'changes', 'tar.xz'])
                generate_deb_package(args, published_files)
            except Exception as e:
                logging.error("Won't publish the deb release.\n Exception: %s", str(e))
    except Exception as e:
        logging.error("Something bad happened ! : {}".format(e))
        traceback.print_exc()
    finally:
        if args.no_remove:
            logging.info("Build dir '%s' not removed", args.build_dir)
        else:
            if os.path.exists(args.build_dir):
                shutil.rmtree(args.build_dir)
                logging.info("Build dir %s removed", args.build_dir)


if __name__ == '__main__':
    args = parse_args()
    if os.path.exists(args.build_dir):
        logging.error('Build dir "%s" already exists.', args.build_dir)
        sys.exit(1)
    main(args)