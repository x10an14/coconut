#!/usr/bin/env python
# -*- coding: utf-8 -*-

#-----------------------------------------------------------------------------------------------------------------------
# INFO:
#-----------------------------------------------------------------------------------------------------------------------

"""
Authors: Evan Hubinger, Fred Buchanan
License: Apache 2.0
Description: The Coconut command-line utility.
"""

#-----------------------------------------------------------------------------------------------------------------------
# IMPORTS:
#-----------------------------------------------------------------------------------------------------------------------

from __future__ import print_function, absolute_import, unicode_literals, division

from coconut.root import *  # NOQA

import sys
import os
import time
import traceback
import webbrowser
import functools
from contextlib import contextmanager
from subprocess import CalledProcessError

from coconut.compiler import Compiler
from coconut.exceptions import (
    CoconutException,
    CoconutInternalException,
)
from coconut.logging import logger
from coconut.constants import (
    code_exts,
    comp_ext,
    watch_interval,
    tutorial_url,
    documentation_url,
    icoconut_kernel_dirs,
    minimum_recursion_limit,
)
from coconut.command.util import (
    openfile,
    writefile,
    readfile,
    fixpath,
    showpath,
    rem_encoding,
    Runner,
    multiprocess_wrapper,
    Prompt,
    ensure_time_elapsed,
    handle_broken_process_pool,
    kill_children,
    run_cmd,
)
from coconut.compiler.header import gethash
from coconut.command.cli import arguments

#-----------------------------------------------------------------------------------------------------------------------
# MAIN:
#-----------------------------------------------------------------------------------------------------------------------


class Command(object):
    """The Coconut command-line interface."""
    comp = None  # current coconut.compiler.Compiler
    show = False  # corresponds to --display flag
    runner = None  # the current Runner
    jobs = 0  # corresponds to --jobs flag
    executor = None  # runs --jobs
    exit_code = 0  # exit status to return
    errmsg = None  # error message to display
    mypy_args = None  # corresponds to --mypy flag

    def __init__(self):
        """Creates the CLI."""
        self.prompt = Prompt()

    def start(self, run=False):
        """Processes command-line arguments."""
        if run:
            args, argv = ["-rq"], []
            for i in range(1, len(sys.argv)):
                arg = sys.argv[i]
                if arg.startswith("-"):
                    args.append(arg)
                else:
                    args.append(arg)
                    argv = sys.argv[i:]
                    break
            sys.argv = argv
        else:
            args = None
        self.cmd(args)

    def cmd(self, args=None, interact=True):
        """Processes command-line arguments."""
        if args is None:
            args = arguments.parse_args()
        else:
            args = arguments.parse_args(args)
        self.exit_code = 0
        with self.handling_exceptions():
            self.use_args(args, interact)
        self.exit_on_error()

    def setup(self, *args, **kwargs):
        """Sets parameters for the compiler."""
        if self.comp is None:
            self.comp = Compiler(*args, **kwargs)
        else:
            self.comp.setup(*args, **kwargs)

    def exit_on_error(self):
        """Exits if exit_code is abnormal."""
        if self.exit_code:
            if self.errmsg is not None:
                logger.show_error("Exiting due to " + self.errmsg + ".")
                self.errmsg = None
            if self.jobs != 0:
                kill_children()
            sys.exit(self.exit_code)

    def set_recursion_limit(self, limit):
        """Sets the Python recursion limit."""
        if limit < minimum_recursion_limit:
            raise CoconutException("--recursion-limit must be at least " + str(minimum_recursion_limit))
        else:
            sys.setrecursionlimit(limit)

    def use_args(self, args, interact=True):
        """Handles command-line arguments."""
        logger.quiet, logger.verbose = args.quiet, args.verbose
        if args.recursion_limit is not None:
            self.set_recursion_limit(args.recursion_limit)
        if args.jobs is not None:
            self.set_jobs(args.jobs)
        if args.tutorial:
            self.launch_tutorial()
        if args.documentation:
            self.launch_documentation()
        if args.style is not None:
            self.prompt.set_style(args.style)
        if args.display:
            self.show = True
        if args.mypy is not None:
            self.mypy_args = args.mypy

        self.setup(
            target=args.target,
            strict=args.strict,
            minify=args.minify,
            line_numbers=args.line_numbers,
            keep_lines=args.keep_lines,
        )

        if args.source is not None:
            if args.run and os.path.isdir(args.source):
                raise CoconutException("source path must point to file not directory when --run is enabled")
            elif args.watch and os.path.isfile(args.source):
                raise CoconutException("source path must point to directory not file when --watch is enabled")
            elif args.interact and args.run:
                raise CoconutException("extraneous --run; --interact implies --run when used in compilation")

            if args.dest is None:
                if args.nowrite:
                    dest = None  # no dest
                else:
                    dest = True  # auto-generate dest
            elif args.nowrite:
                raise CoconutException("destination path cannot be given when --nowrite is enabled")
            elif os.path.isfile(args.dest):
                raise CoconutException("destination path must point to directory not file")
            else:
                dest = args.dest
            if args.package and args.standalone:
                raise CoconutException("cannot compile as both --package and --standalone")
            elif args.package:
                package = True
            elif args.standalone:
                package = False
            else:
                package = None  # auto-decide package

            with self.running_jobs():
                self.compile_path(args.source, dest, package, args.run or args.interact, args.force)

        elif (args.run
              or args.nowrite
              or args.force
              or args.package
              or args.standalone
              or args.watch):
            raise CoconutException("a source file/folder must be specified when options that depend on the source are enabled")

        if args.code is not None:
            self.execute(self.comp.parse_block(args.code))
        stdin = not sys.stdin.isatty()  # check if input was piped in
        if stdin:
            self.execute(self.comp.parse_block(sys.stdin.read()))
        if args.jupyter is not None:
            self.start_jupyter(args.jupyter)
        if args.interact or (interact and not (
                stdin
                or args.source
                or args.code
                or args.tutorial
                or args.documentation
                or args.watch
                or args.jupyter is not None
        )):
            self.start_prompt()
        if args.watch:
            self.watch(args.source, dest, package, args.run, args.force)

    def register_error(self, code=1, errmsg=None):
        """Updates the exit code."""
        if errmsg is not None:
            if self.errmsg is None:
                self.errmsg = errmsg
            elif errmsg not in self.errmsg:
                self.errmsg += ", " + errmsg
        self.exit_code = max(self.exit_code, code)

    @contextmanager
    def handling_exceptions(self):
        """Performs proper exception handling."""
        try:
            with handle_broken_process_pool():
                yield
        except SystemExit as err:
            self.register_error(err.code)
        except BaseException as err:
            if isinstance(err, CoconutException):
                logger.print_exc()
            elif not isinstance(err, KeyboardInterrupt):
                traceback.print_exc()
            self.register_error(errmsg=err.__class__.__name__)

    def compile_path(self, path, write=True, package=None, run=False, force=False):
        """Compiles a path."""
        path = fixpath(path)
        if write is not None and write is not True:
            write = fixpath(write)
        if os.path.isfile(path):
            if package is None:
                package = False
            self.compile_file(path, write, package, run, force)
        elif os.path.isdir(path):
            if package is None:
                package = True
            self.compile_folder(path, write, package, run, force)
        else:
            raise CoconutException("could not find source path", path)

    def compile_folder(self, directory, write=True, package=True, run=False, force=False):
        """Compiles a directory."""
        for dirpath, dirnames, filenames in os.walk(directory):
            if write is None or write is True:
                writedir = write
            else:
                writedir = os.path.join(write, os.path.relpath(dirpath, directory))
            for filename in filenames:
                if os.path.splitext(filename)[1] in code_exts:
                    self.compile_file(os.path.join(dirpath, filename), writedir, package, run, force, allow_mypy=False)
            for name in dirnames[:]:
                if name != "." * len(name) and name.startswith("."):
                    if logger.verbose:
                        logger.show_tabulated("Skipped directory", name, "(explicitly pass as source to override).")
                    dirnames.remove(name)  # directories removed from dirnames won't appear in further os.walk iteration
        if write is True:
            self.run_mypy(directory)
        elif write is not None:
            self.run_mypy(write)

    def compile_file(self, filepath, write=True, package=False, run=False, force=False, allow_mypy=True):
        """Compiles a file."""
        if write is None:
            destpath = None
        elif write is True:
            destpath = filepath
        else:
            destpath = os.path.join(write, os.path.basename(filepath))
        if destpath is not None:
            base, ext = os.path.splitext(os.path.splitext(destpath)[0])
            if not ext:
                ext = comp_ext
            destpath = base + ext
        if filepath == destpath:
            raise CoconutException("cannot compile " + showpath(filepath) + " to itself (incorrect file extension)")
        self.compile(filepath, destpath, package, run, force)
        if allow_mypy and destpath is not None:
            self.run_mypy(destpath)

    def compile(self, codepath, destpath=None, package=False, run=False, force=False):
        """Compiles a source Coconut file to a destination Python file."""
        logger.show_tabulated("Compiling", showpath(codepath), "...")

        with openfile(codepath, "r") as opened:
            code = readfile(opened)

        if destpath is not None:
            destdir = os.path.dirname(destpath)
            if not os.path.exists(destdir):
                os.makedirs(destdir)
            if package is True:
                self.create_package(destdir)

        foundhash = None if force else self.hashashof(destpath, code, package)
        if foundhash:
            logger.show_tabulated("Left unchanged", showpath(destpath), "(pass --force to override).")
            if self.show:
                print(foundhash)
            if run:
                self.execute_file(destpath)

        else:

            if package is True:
                compile_method = "parse_module"
            elif package is False:
                compile_method = "parse_file"
            else:
                raise CoconutInternalException("invalid value for package", package)

            def callback(compiled):
                if destpath is None:
                    logger.show_tabulated("Finished", showpath(codepath), "without writing to file.")
                else:
                    with openfile(destpath, "w") as opened:
                        writefile(opened, compiled)
                    logger.show_tabulated("Compiled to", showpath(destpath), ".")
                if self.show:
                    print(compiled)
                if run:
                    if destpath is None:
                        self.execute(compiled, path=codepath, allow_show=False)
                    else:
                        self.execute_file(destpath)

            self.submit_comp_job(codepath, callback, compile_method, code)

    def submit_comp_job(self, path, callback, method, *args, **kwargs):
        """Submits a job on self.comp to be run in parallel."""
        if self.executor is None:
            with self.handling_exceptions():
                callback(getattr(self.comp, method)(*args, **kwargs))
        else:
            path = showpath(path)
            with logger.in_path(path):  # pickle the compiler in the path context
                future = self.executor.submit(multiprocess_wrapper(self.comp, method), *args, **kwargs)

            def callback_wrapper(completed_future):
                """Ensures that all errors are always caught, since errors raised in a callback won't be propagated."""
                with logger.in_path(path):  # handle errors in the path context
                    with self.handling_exceptions():
                        result = completed_future.result()
                        callback(result)
            future.add_done_callback(callback_wrapper)

    def set_jobs(self, jobs):
        """Sets --jobs."""
        if jobs == "sys":
            self.jobs = None
        else:
            try:
                jobs = int(jobs)
            except ValueError:
                jobs = -1
            if jobs < 0:
                raise CoconutException("--jobs must be an integer >= 0 or 'sys'")
            else:
                self.jobs = jobs

    @contextmanager
    def running_jobs(self):
        """Initialize multiprocessing."""
        with self.handling_exceptions():
            if self.jobs == 0:
                yield
            else:
                from concurrent.futures import ProcessPoolExecutor
                try:
                    with ProcessPoolExecutor(self.jobs) as self.executor:
                        with ensure_time_elapsed():
                            yield
                finally:
                    self.executor = None
        self.exit_on_error()

    def create_package(self, dirpath):
        """Sets up a package directory."""
        filepath = os.path.join(fixpath(dirpath), "__coconut__.py")
        with openfile(filepath, "w") as opened:
            writefile(opened, self.comp.headers("package"))

    def hashashof(self, destpath, code, package):
        """Determines if a file has the hash of the code."""
        if destpath is not None and os.path.isfile(destpath):
            with openfile(destpath, "r") as opened:
                compiled = readfile(opened)
                hashash = gethash(compiled)
                if hashash is not None and hashash == self.comp.genhash(package, code):
                    return compiled
        return None

    def get_input(self, more=False):
        """Prompts for code input."""
        try:
            return self.prompt.input(more)
        except KeyboardInterrupt:
            logger.printerr("\nKeyboardInterrupt")
        except EOFError:
            print()
            self.exit_runner()
        return None

    def start_running(self):
        """Starts running the Runner."""
        self.check_runner()
        self.running = True

    def start_prompt(self):
        """Starts the interpreter."""
        logger.print("Coconut Interpreter:")
        logger.print('(type "exit()" or press Ctrl-D to end)')
        self.start_running()
        while self.running:
            code = self.get_input()
            if code:
                compiled = self.handle_input(code)
                if compiled:
                    self.execute(compiled, use_eval=None)

    def exit_runner(self, exit_code=0):
        """Exits the interpreter."""
        self.register_error(exit_code)
        self.running = False

    def handle_input(self, code):
        """Compiles Coconut interpreter input."""
        if not self.prompt.multiline:
            if not self.comp.should_indent(code):
                try:
                    return self.comp.parse_block(code)
                except CoconutException:
                    pass
            while True:
                line = self.get_input(more=True)
                if line is None:
                    return None
                elif line.strip():
                    code += "\n" + line
                else:
                    break
        try:
            return self.comp.parse_block(code)
        except CoconutException:
            logger.print_exc()
        return None

    def execute(self, compiled=None, path=None, use_eval=False, allow_show=True):
        """Executes compiled code."""
        self.check_runner()
        if compiled is not None:
            if allow_show and self.show:
                print(compiled)
            self.run_mypy("-c", compiled)
            if path is not None:  # path means header is included, and thus encoding must be removed
                compiled = rem_encoding(compiled)
            self.runner.run(compiled, use_eval=use_eval, path=path, all_errors_exit=(path is not None))

    def execute_file(self, destpath):
        """Executes compiled file."""
        self.check_runner()
        self.runner.run_file(destpath)

    def check_runner(self):
        """Makes sure there is a runner."""
        if os.getcwd() not in sys.path:
            sys.path.append(os.getcwd())
        if self.runner is None:
            self.runner = Runner(self.comp, self.exit_runner)

    def launch_tutorial(self):
        """Opens the Coconut tutorial."""
        webbrowser.open(tutorial_url, 2)

    def launch_documentation(self):
        """Opens the Coconut documentation."""
        webbrowser.open(documentation_url, 2)

    def run_mypy(self, *args):
        """Run MyPy with arguments."""
        if self.mypy_args is not None:
            args = ["mypy"] + list(args)

            for arg in self.mypy_args:
                if arg == "--fast-parser":
                    logger.warn("unnecessary --mypy argument", arg, extra="passed automatically if available")
                elif arg == "--py2" or arg == "-2":
                    logger.warn("unnecessary --mypy argument", arg, extra="passed automatically when needed")
                elif path == fixpath(arg):
                    logger.warn("unnecessary --mypy argument", arg, extra="path to compiled files passed automatically")
                    continue
                args.append(arg)

            if not ("--py2" in args or "-2" in args) and not self.comp.target.startswith("3"):
                args.append("--py2")
            if "--fast-parser" not in args:
                try:
                    import typed_ast  # NOQA
                except ImportError:
                    if not self.comp.target.startswith("3"):
                        logger.warn("missing typed_ast module; MyPy may not properly analyze added type annotation comments",
                                    extra="run 'pip install typed_ast' or pass '--target 3' to fix")
                else:
                    args.append("--fast-parser")

            try:
                run_cmd(args)
            except CalledProcessError:
                raise CoconutException("failed to run MyPy command", args)

    def start_jupyter(self, args):
        """Starts Jupyter with the Coconut kernel."""
        install_func = functools.partial(run_cmd, show_output=logger.verbose or not args)

        try:
            install_func(["jupyter", "--version"])
        except CalledProcessError:
            jupyter = "ipython"
        else:
            jupyter = "jupyter"

        for icoconut_kernel_dir in icoconut_kernel_dirs:
            install_args = [jupyter, "kernelspec", "install", icoconut_kernel_dir, "--replace"]
            try:
                install_func(install_args)
            except CalledProcessError:
                user_install_args = install_args + ["--user"]
                try:
                    install_func(user_install_args)
                except CalledProcessError:
                    logger.warn("kernel install failed on command'", " ".join(install_args))
                    self.register_error(errmsg="Jupyter error")

        if args:
            if args[0] == "console":
                ver = "2" if PY2 else "3"
                try:
                    install_func(["python" + ver, "-m", "coconut.main", "--version"])
                except CalledProcessError:
                    kernel_name = "coconut"
                else:
                    kernel_name = "coconut" + ver
                run_args = [jupyter, "console", "--kernel", kernel_name] + args[1:]
            elif args[0] == "notebook":
                run_args = [jupyter, "notebook"] + args[1:]
            else:
                raise CoconutException('first argument after --jupyter must be either "console" or "notebook"')
            self.register_error(run_cmd(run_args, raise_errs=False), errmsg="Jupyter error")

    def watch(self, source, write=True, package=None, run=False, force=False):
        """Watches a source and recompiles on change."""
        from coconut.command.watch import Observer, RecompilationWatcher

        source = fixpath(source)

        logger.print()
        logger.show_tabulated("Watching", showpath(source), "(press Ctrl-C to end)...")

        def recompile(path):
            if os.path.isfile(path) and os.path.splitext(path)[1] in code_exts:
                with self.handling_exceptions():
                    self.compile_path(path, write, package, run, force)

        observer = Observer()
        observer.schedule(RecompilationWatcher(recompile), source, recursive=True)

        with self.running_jobs():
            observer.start()
            try:
                while True:
                    time.sleep(watch_interval)
            except KeyboardInterrupt:
                logger.show("Got KeyboardInterrupt; stopping watcher.")
            finally:
                observer.stop()
                observer.join()
