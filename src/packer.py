#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
#############################################################
#                                                           #
#      Copyright @ 2018 -  Dashingsoft corp.                #
#      All rights reserved.                                 #
#                                                           #
#      pyarmor                                              #
#                                                           #
#      Version: 4.3.2 -                                     #
#                                                           #
#############################################################
#
#
#  @File: packer.py
#
#  @Author: Jondy Zhao(jondy.zhao@gmail.com)
#
#  @Create Date: 2018/11/08
#
#  @Description:
#
#   Pack obfuscated Python scripts with any of third party
#   tools: py2exe, py2app, cx_Freeze
#

'''Pack obfuscated scripts to one bundle, distribute the
bundle as a folder or file to other people, and they can
execute your program without Python installed.

The prefer way is

    pip install pyinstaller
    parmor pack /path/to/src/hello.py

'''

import logging
import os
import shutil
import subprocess
import sys
import time

from distutils.util import get_platform
from glob import glob
from py_compile import compile as compile_file
from shutil import split
from zipfile import PyZipFile

try:
    import argparse
except ImportError:
    # argparse is new in version 2.7
    import polyfills.argparse as argparse

# Default output path, library name, command options for setup script
DEFAULT_PACKER = {
    'py2app': ('dist', 'library.zip', ['py2app', '--dist-dir']),
    'py2exe': ('dist', 'library.zip', ['py2exe', '--dist-dir']),
    'PyInstaller': ('dist', '', ['-m', 'PyInstaller', '--distpath']),
    'cx_Freeze': (
        os.path.join(
            'build', 'exe.%s-%s' % (get_platform(), sys.version[0:3])),
        'python%s%s.zip' % sys.version_info[:2],
        ['build', '--build-exe'])
}

def logaction(func):
    def wrap(*args, **kwargs):
        logging.info('')
        logging.info('%s', func.__name__)
        return func(*args, **kwargs)
    return wrap

@logaction
def update_library(obfdist, libzip):
    '''Update compressed library generated by py2exe or cx_Freeze, replace
the original scripts with obfuscated ones.

    '''
    # # It's simple ,but there are duplicated .pyc files
    # with PyZipFile(libzip, 'a') as f:
    #     f.writepy(obfdist)
    filelist = []
    for root, dirs, files in os.walk(obfdist):
        filelist.extend([os.path.join(root, s) for s in files])

    with PyZipFile(libzip, 'r') as f:
        namelist = f.namelist()
        f.extractall(obfdist)

    for s in filelist:
        if s.lower().endswith('.py'):
            compile_file(s, s + 'c')

    with PyZipFile(libzip, 'w') as f:
        for name in namelist:
            f.write(os.path.join(obfdist, name), name)

@logaction
def run_setup_script(src, entry, build, script, packcmd, obfdist):
    '''Update entry script, copy pytransform.py to source path, then run
setup script to build the bundle.

    '''
    obf_entry = os.path.join(obfdist, entry)

    tempfile = '%s.armor.bak' % entry
    shutil.move(os.path.join(src, entry), tempfile)
    shutil.move(obf_entry, src)
    shutil.copy('pytransform.py', src)

    p = subprocess.Popen([sys.executable, script] + packcmd, cwd=build,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdoutdata, _ = p.communicate()

    shutil.move(tempfile, os.path.join(src, entry))
    os.remove(os.path.join(src, 'pytransform.py'))

    if p.returncode != 0:
        logging.error('\n\n%s\n\n', stdoutdata)
        raise RuntimeError('Run setup script failed')

@logaction
def copy_runtime_files(runtimes, output):
    for s in 'pyshield.key', 'pyshield.lic', 'product.key', 'license.lic':
        shutil.copy(os.path.join(runtimes, s), output)
    for dllname in glob(os.path.join(runtimes, '_pytransform.*')):
        shutil.copy(dllname, output)

def call_armor(args):
    logging.info('')
    logging.info('')
    p = subprocess.Popen([sys.executable, 'pyarmor.py'] + list(args))
    p.wait()
    if p.returncode != 0:
        raise RuntimeError('Call pyarmor failed')

def pathwrapper(func):
    def wrap(*args, **kwargs):
        oldpath = os.getcwd()
        os.chdir(os.path.abspath(os.path.dirname(__file__)))
        logging.info('Change path to %s', os.getcwd())
        try:
            return func(*args, **kwargs)
        finally:
            os.chdir(oldpath)
    return wrap

@pathwrapper
def _packer(src, entry, build, script, packcmd, output, libname):
    project = os.path.join('projects', 'build-for-packer-v0.1')
    obfdist = os.path.join(project, 'dist')

    args = 'init', '-t', 'app', '--src', src, '--entry', entry, project
    call_armor(args)

    filters = ('global-include *.py', 'prune build, prune dist',
               'exclude %s pytransform.py' % entry)
    args = ('config', '--runtime-path', '',
            '--manifest', ','.join(filters), project)
    call_armor(args)

    args = 'build', project
    call_armor(args)

    run_setup_script(src, entry, build, script, packcmd, obfdist)

    update_library(obfdist, os.path.join(output, libname))

    copy_runtime_files(obfdist, output)

    shutil.rmtree(project)

@logaction
def check_setup_script(_type, setup):
    if os.path.exists(setup):
        return

    logging.info('Please run the following command to generate setup.py')
    if _type == 'py2exe':
        logging.info('\tpython -m py2exe.build_exe -W setup.py hello.py')
    elif _type == 'cx_Freeze':
        logging.info('\tcxfreeze-quickstart')
    else:
        logging.info('\tvi setup.py')
    raise RuntimeError('No setup script %s found', setup)

@logaction
def run_pyi_makespec(project, obfdist, src, entry, packcmd):
    s = os.pathsep
    d = os.path.relpath(obfdist, project)
    datas = [
        '--add-data', '%s%s.' % (os.path.join(d, '*.lic'), s),
        '--add-data', '%s%s.' % (os.path.join(d, '*.key'), s),
        '--add-data', '%s%s.' % (os.path.join(d, '_pytransform.*'), s)
    ]
    scripts = [os.path.join(src, entry), os.path.join(obfdist, entry)]

    options = ['-y', '--specpath', project]
    options.extend(datas)
    options.extend(scripts)

    p = subprocess.Popen([sys.executable] + packcmd + options,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdoutdata, _ = p.communicate()

    if p.returncode != 0:
        logging.error('\n\n%s\n\n', stdoutdata)
        raise RuntimeError('Make specfile failed')

@logaction
def update_specfile(project, obfdist, src, entry, specfile):
    with open(specfile) as f:
        lines = f.readlines()

    patched_lines = (
    "", "# Patched by PyArmor",
    "a.scripts[0] = '%s', '%s', 'PYSOURCE'" % (
        entry[:-3], os.path.join(obfdist, entry)),
    "for i in range(len(a.pure)):",
    "    if a.pure[i][1].startswith(a.pathex[0]):",
    "        a.pure[i] = a.pure[i][0], a.pure[i][1].replace(" \
    "a.pathex[0], '%s'), a.pure[i][2]" % os.path.abspath(obfdist),
    "# Patch end.", "", "")

    for i in range(len(lines)):
        if lines[i].startswith("pyz = PYZ(a.pure"):
            break
    else:
        raise RuntimeError('Unsupport specfile, no PYZ line found')
    lines[i:i] = '\n'.join(patched_lines)

    patched_file = specfile[:-5] + '-patched.spec'
    with open(patched_file, 'w') as f:
        f.writelines(lines)

    return patched_file

@logaction
def run_pyinstaller(project, src, entry, specfile, packcmd):
    p = subprocess.Popen(
        [sys.executable] + packcmd + ['-y', specfile],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdoutdata, _ = p.communicate()

    if p.returncode != 0:
        logging.error('\n\n%s\n\n', stdoutdata)
        raise RuntimeError('Run pyinstaller failed')

@pathwrapper
def _pyinstaller(src, entry, packcmd, output):
    project = os.path.join('projects', 'pyinstaller')
    obfdist = os.path.join(project, 'dist')
    spec = os.path.join(project, os.path.basename(entry)[:-3] + '.spec')

    args = 'obfuscate', '-r', '--src', src, '--entry', entry, '-O', obfdist
    call_armor(args)

    run_pyi_makespec(project, obfdist, src, entry, packcmd)

    patched = update_specfile(project, obfdist, src, entry, spec)

    run_pyinstaller(project, src, entry, patched, packcmd)

    shutil.rmtree(project)

def packer(args):
    _type = args.type
    src = os.path.abspath(os.path.dirname(args.entry[0]))
    entry = os.path.basename(args.entry[0])
    extra_options = [] if args.options is None else split(args.options)

    if args.setup is None:
        build = src
        script = 'setup.py'
    else:
        build = os.path.abspath(os.path.dirname(args.setup))
        script = os.path.basename(args.setup)

    if args.output is None:
        dist = DEFAULT_PACKER[_type][0]
        output = os.path.normpath(os.path.join(build, dist))
    else:
        output = args.output if os.path.isabs(args.output) \
            else os.path.join(build, args.output)

    libname = DEFAULT_PACKER[_type][1]
    packcmd = DEFAULT_PACKER[_type][2] + [output] + extra_options

    logging.info('Prepare to pack obfuscated scripts with %s', _type)
    if _type == 'PyInstaller':
        _pyinstaller(src, entry, packcmd, output)
    else:
        check_setup_script(_type, os.path.join(build, script))
        _packer(src, entry, build, script, packcmd, output, libname)

    logging.info('')
    logging.info('Pack obfuscated scripts successfully in the path')
    logging.info('')
    logging.info('\t%s', output)

def add_arguments(parser):
    parser.add_argument('-v', '--version', action='version', version='v0.1')

    parser.add_argument('-t', '--type', default='PyInstaller', metavar='TYPE',
                        choices=DEFAULT_PACKER.keys(),
                        help=', '.join(DEFAULT_PACKER.keys()))
    # parser.add_argument('-p', '--path',
    #                     help='Base path, default is the path of entry script')
    parser.add_argument('-s', '--setup',
                        help='Setup script, default is setup.py, ' \
                             'or ENTRY.spec for PyInstaller')
    parser.add_argument('-O', '--output',
                        help='Directory to put final built distributions in' \
                        ' (default is output path of setup script)')
    parser.add_argument('-e', '--options',
                        help='Extra options to run pack command')
    parser.add_argument('entry', metavar='SCRIPT', nargs=1,
                        help='Entry script')

def main(args):
    parser = argparse.ArgumentParser(
        prog='packer.py',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Pack obfuscated scripts',
        epilog=__doc__,
    )
    add_arguments(parser)
    packer(parser.parse_args(args))

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)-8s %(message)s',
    )
    main(sys.argv[1:])
