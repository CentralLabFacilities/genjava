#!/usr/bin/env python

##############################################################################
# Imports
##############################################################################

from __future__ import print_function

import sys
import os
import shutil
import subprocess
from catkin_pkg.packages import find_packages
import rospkg
import rosjava_build_tools.catkin

##############################################################################
# Utils
##############################################################################

import pwd


def author_name():
    """
    Utility to compute logged in user name

    :returns: name of current user, ``str``
    """
    import getpass
    name = getpass.getuser()
    try:
        login = name
        name = pwd.getpwnam(login)[4]
        name = ''.join(name.split(','))  # strip commas
        # in case pwnam is not set
        if not name:
            name = login
    except:
        #pwd failed
        pass
    #if type(name) == str:
    #    name = name.decode('utf-8')
    return name

def read_template(tmplf):
    f = open(tmplf, 'r')
    try:
        t = f.read()
    finally:
        f.close()
    return t

def get_genjava_wrapper():
    #have to find pkg.
    rospack = rospkg.RosPack()
    gradle_binary = os.path.join(rospack.get_path('rosjava_build_tools'), 'gradle', 'gradlew')

    return gradle_binary

##############################################################################
# Methods acting on classes
##############################################################################


def instantiate_genjava_template(template, project_name, project_version, pkg_directory, author, msg_dependencies, sources_dir):
    if sources_dir is None:
        sources_dir = ""
    sources_dir = sources_dir.replace(";", ":")
    return template % locals()


def get_templates():
    template_dir = os.path.join(os.path.dirname(__file__), 'templates', 'genjava_project')
    templates = {}
    templates['build.gradle'] = read_template(os.path.join(template_dir, 'build.gradle.in'))
    return templates


def populate_project(project_name, project_version, pkg_directory, gradle_project_dir, msg_dependencies, sources_dir):
    author = author_name()
    for filename, template in get_templates().iteritems():
        contents = instantiate_genjava_template(template, project_name, project_version, pkg_directory, author, msg_dependencies, sources_dir)
        try:
            p = os.path.abspath(os.path.join(gradle_project_dir, filename))
            f = open(p, 'w')
            f.write(contents)
            #console.pretty_print("Created file: ", console.cyan)
            #console.pretty_println("%s" % p, console.yellow)
        finally:
            f.close()


def create_dependency_string(project_name, msg_package_index):
    package = msg_package_index[project_name]
    gradle_dependency_string = ""
    for dep in package.build_depends:
        try:
            dependency_package = msg_package_index[dep.name]
        except KeyError:
            continue  # it's not a message package
        gradle_dependency_string += "  compile 'org.ros.rosjava_messages:" + dependency_package.name + ":" + dependency_package.version + "'\n"
    return gradle_dependency_string


def create_msg_package_index(print_lists=True, verbosity=False):
    """
      Scans the package paths and creates a package index always taking the
      highest in the workspace chain (i.e. takes an overlay in preference when
      there are multiple instances of the package).

      :returns: the package index
      :rtype: { name : catkin_pkg.Package }
    """
    # should use this, but it doesn't sequence them properly, so we'd have to make careful version checks
    # this is inconvenient since it would always mean we should bump the version number in an overlay
    # when all that is necessary is for it to recognise that it is in an overlay
    # ros_paths = rospkg.get_ros_paths()
    package_index = {}
    ros_paths = rospkg.get_ros_package_path()
    ros_paths = [x for x in ros_paths.split(':') if x]
    if print_lists:
        print("Blacklisted packages:")
        print(rosjava_build_tools.catkin.message_package_blacklist)
        print("Whitelisted packages:")
        print(rosjava_build_tools.catkin.message_package_whitelist)
    # packages that don't properly identify themselves as message packages (fix upstream).
    for path in reversed(ros_paths):  # make sure we pick up the source overlays last
        for package_path, package in find_packages(path).items():
            if ('message_generation' in [dep.name for dep in package.build_depends] or
                'genmsg' in [dep.name for dep in package.build_depends] or
                package.name in rosjava_build_tools.catkin.message_package_whitelist):
                if (package.name not in rosjava_build_tools.catkin.message_package_blacklist):
                    if print_lists and verbosity:
                        if package.name in package_index:
                            print("!!Overlay!!")
                            print("  %s" % package.name)
                            print("    path: %s, (OLD: %s)" % (path + "/" + package_path, package_index[package.name].filename))
                            print("    version: %s, (OLD: %s)" % (package.version, package_index[package.name].version))
                    package_index[package.name] = package

    if print_lists and verbosity:
        print("Message package list:")
        for package in package_index:
            pkg = package_index[package]
            print(package)
            # for attr in dir(pkg):
            #     print("pkg.%s = %r" % (attr, getattr(pkg, attr)))
            print("  file: %s" % pkg.filename)
            print("  version: %s" % pkg.version)
            print("  dependency:")
            for dep in pkg.build_depends:
                if not (dep.name == 'message_generation'):
                    print("         : %s" % dep)

    return package_index

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def handle(function, path, excinfo):
    eprint("error:", function, path, excinfo)


def create(msg_pkg_name, output_dir, sources_dir = None, verbosity=False, print_lists=True):
    '''
    Creates a standalone single project gradle build instance in the specified output directory and
    populates it with gradle wrapper and build.gradle file that will enable building of the artifact later.
    :param str project_name:
    :param dict msg_package_index:  { name : catkin_pkg.Package }
    :param str output_dir:
    '''
    genjava_gradle_dir = os.path.join(output_dir, msg_pkg_name)
    #print("creating genjava project pid", os.getpid(), "dir", genjava_gradle_dir)
    if os.path.exists(genjava_gradle_dir):
        shutil.rmtree(genjava_gradle_dir, onerror=handle)
    os.makedirs(genjava_gradle_dir)
    msg_package_index = create_msg_package_index(print_lists=print_lists, verbosity=verbosity)
    if msg_pkg_name not in msg_package_index.keys():
        raise IOError("could not find %s among message packages. Does the that package have a <build_depend> on message_generation in its package.xml?" % msg_pkg_name)

    msg_dependencies = create_dependency_string(msg_pkg_name, msg_package_index)

    pkg_directory = os.path.abspath(os.path.dirname(msg_package_index[msg_pkg_name].filename))
    msg_pkg_version = msg_package_index[msg_pkg_name].version
    if verbosity:
        eprint("Create Message Package: %s:%s" % (msg_pkg_name, msg_pkg_version))
    populate_project(msg_pkg_name, msg_pkg_version, pkg_directory, genjava_gradle_dir, msg_dependencies, sources_dir)
    return 0


def build(msg_pkg_name, output_dir, verbosity):
    # Are there droppings? If yes, then this genjava has marked this package as
    # needing a compile (it's new, or some msg file changed).
    droppings_file = os.path.join(output_dir, msg_pkg_name, 'droppings')
    #if not os.path.isfile(droppings_file):
        #print("Nobody left any droppings - nothing to do! %s" % droppings_file)
        #return
    #print("Scooping the droppings! [%s]" % droppings_file)
    #os.remove(droppings_file)
    cmd = [get_genjava_wrapper()]
    cmd.append('--console=plain')
    cmd.append('--no-daemon')
    if not verbosity:
        cmd.append('--quiet')
    #print("COMMAND: %s" % cmd)

    if verbosity:
        info = cmd[:]
        info.append('info')
        subprocess.call(info)
        print("CALLING COMMAND: %s" % cmd)

    return subprocess.call(cmd, stderr=subprocess.STDOUT,)


def standalone_create_and_build(msg_pkg_name, output_dir, verbosity, avoid_rebuilding=False, print_lists=False):
    '''
    Brute force create and build the message artifact disregarding any smarts
    such as whether message files changed or not. For use with the standalone
    package builder.
    :param str msg_pkg_name:
    :param str output_dir:
    :param bool verbosity:
    :param bool avoid_rebuilding: don't rebuild if working dir is already there
    :return bool : whether it built, or skipped because it was avoiding a rebuild
    '''
    genjava_gradle_dir = os.path.join(output_dir, msg_pkg_name)
    if os.path.exists(genjava_gradle_dir) and avoid_rebuilding:
        return False
    create(msg_pkg_name, output_dir, verbosity=verbosity, print_lists=print_lists)
    working_directory = os.path.join(os.path.abspath(output_dir), msg_pkg_name)
    gradle_wrapper = get_genjava_wrapper()
    cmd = [gradle_wrapper, '-p', working_directory]
    cmd.append('--console=plain')
    cmd.append('--no-daemon')
    if not verbosity:
        cmd.append('--quiet')
    #print("COMMAND........................%s" % cmd)
    ret = subprocess.call(cmd, stderr=subprocess.STDOUT,)
    if ret is 0:
        return True
    else:
        return ret
