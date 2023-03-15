#!/usr/bin/python3
""" geet: a git/gh wrapper that implements geet's workflow.

geet is a user-friendly wrapper (aka "porcelain") around the "git" and
"gh-cli" tools  geet is an opinionated tool that implements a specific,
simple, powerful workflow.

"geet" is also an instructional tool: by showing each command as it
executes, geet helps users learn git.

## Features:

Uses the "worktree" feature so that:

* every branch is always visible in its own directory.
* switching branches is accomplished by changing directory.
* it's harder to accidentally save changes to the wrong branch.
* users can have uncommitted changes pending in more than one branch.

All branch directories are named ~/geet/<REPO>/<BRANCH>.

All local commits are automatically backed up to github.

Tracks "parentage" (which branch is derived from which).

Sets up and enforces use of ssh for all interactions with github.

Supports multi-homed development (user can do work on various hosts
without NFS-mounted home directories).

## An example of simple use:

1. Run "geet init" to clone and check out the enfabrica/internal repo.
   This only needs to be done once per home directory.

2. "cd ~/geet/internal/main" to start in the main branch.

3. Make a feature branch: "geet make_branch my_feature"
   Then: "cd $(geet gcd my_feature)"

4. Make some changes, and call "geet commit" whenever needed to checkpoint
   your work.

5. Call "geet update" to pull new changes from upstream.

6. When ready to send your change out for review:

    geet fix  # runs all automatic code formatters
    geet commit -a -m "ran geet fix"
    geet make_pr  # creates a pull request.

7. You can continue to make updates to your branch, and update your
   PR by running "geet commit".

8. When approved, run "geet submit_pr" to merge your change.

## An example of more complex use:

You can continue to develop a second feature while the first feature is out for
review.

1. Make a branch of a branch:

     cd $(geet gcd my_feature)
     geet mkbr my_feature2

2. Do work in the child branch:

     cd $(geet gcd my_feature2)

3. Recursively update a chain of branches:

     geet rupdate

## Philosophy

* No non-standard-library python dependencies.

* If I have to look it up on stack overflow, it should get encoded in
geet.

* Automatic but not automagic.  No surprises.  Show your work.  Never
change the system in a way the user doesn't expect.  When in doubt, ask.

* Do what I mean: I'm lysdexic, so a lot of the commands have reverse
order aliases.

Definitions:

   $OWNER: the owner of the upstream repository.
   $GHUSER: the github username of this user.
   upstream: the original repo we have forked ($OWNER/$REPO)
             we issue pull requests to this repo, and we integrate
             changes from here.
   origin:   the user's forked repo ($GHUSER/$REPO)
             we pull and push to this repo.
   upstream/main: top of tree
   origin/main: user's top-of-tree with no local changes,
       updated periodically from upstream/main.
   main: local repo top of tree, no local changes,
       updated periodically from upstream/main.
   $feature: fork of main (or other $feature), contains
       local changes.  May have 0 or 1 PRs associated with it.
   origin/$feature: github backup of $feature branch.

Updates flow in one direction through these branches:

  upstream/main -> main -> origin/main -> $feature -> origin/$feature

The user only commits changes to $feature.

Changes then migrate from origin/$feature back to upstream/main when a PR
is approved and merged.

Note: We are transitioning from "master" to "main."  Gee always tries to
find a "main" remote branch first, but falls back to "master" if "main"
does not exist.
"""

import argparse
import re
import subprocess
import textwrap

## Command line and configuration file parsing

class AngleBracketsHelpFormatter(argparse.HelpFormatter):
    def _get_default_metavar_for_positional(self, action):
        default = super()._get_default_metavar_for_positional(action)
        return f'<{default}>'

# Thanks mike.depalatis.net:
cli = argparse.ArgumentParser(formatter_class=AngleBracketsHelpFormatter)
subparsers = cli.add_subparsers(title="subcommands", description="")


def _add_subcommand(parent, func):
    """Creates a subcommand from a function's docstring.

    The first line of the doc-string specifies the name of the subcommand
    and the short "help" description.  For example:

        subvert: topples the dominant paradigm.

    Aliases can be added by adding an "Aliases:" section to the docstring, for
    example:

        Aliases: sub, subv, s

    Arguments are defined in an Args: block, and must have the form:

        paradigm: (string) A positional string argument
        input: (file) A filename (auto-completes to a filename).
        new_branch: (branch) A positional branch name argument (auto-completes
           to a branch name).
        -k|--kill: An example of a boolean flag
        -c|--comment=string: An example of a string flag

    The following argument types are special: "file" specifies that autocomplete
    should help the user file a specific file.  "branch" specifies that autocomplete
    should name an existing branch in the current repo.

    As a simplifying assumption: positional arguments are always mandatory,
    flag arguments are always optional.  Usage strings are automatically
    generated:

        Usage: subvert <paradigm> [--kill]
    """
    docstr = func.__doc__
    paragraphs = [textwrap.dedent(s) for s in docstr.strip().split("\n\n")]

    name, shorthelp = paragraphs[0].split(": ")
    del paragraphs[0]
    
    args_list = []
    try:
        index = [x.startswith("Args:\n") for x in paragraphs].index(True)
        args_list = [x[5:] for x in paragraphs if x.startswith("Args:\n")]
        del paragraphs[index]
    except ValueError:
        pass

    aliases = []
    try:
        index = [x.startswith("Aliases:") for x in paragraphs].index(True)
        aliases = [x.strip() for x in paragraphs[index][9:].split(",")]
        del paragraphs[index]
    except ValueError:
        pass

    longhelp = "\n\n".join(paragraphs)

    parser = parent.add_parser(name, help=shorthelp, description=longhelp, aliases=aliases, formatter_class=AngleBracketsHelpFormatter)
    parser.set_defaults(func=func)
    if args_list:
        args = re.sub(r"\s*\n\s{4,}", " ", args_list[0])
        args_list = [x.strip() for x in args.split("\n")]
        for arg, arghelp in [x.split(": ") for x in args_list if x]:
            if arg.startswith("-"):
                if '=' in arg:
                    kwargs = {"action": "store", "type": "str"}
                    (arg, atype) = arg.split('=')
                    if atype.endswith("..."):
                        kwargs["action"] = "append"
                        kwargs["default"] = []
                        atype = atype[:-3]
                    if atype == "int":
                        kwargs["type"] = int
                else:
                    kwargs = {"action": "store_true"}
            else:
                kwargs = {"action": "store", "type": str}
                if arg.endswith("..."):
                    kwargs = {"action": "append", "nargs": "+"}
                    arg = arg[:-3]
            kwargs["help"] = arghelp
            parser.add_argument(*(arg.split("|")), **kwargs)


def subcommand(parent=subparsers):
    # TODO(jonathan): parse args from doc string
    def decorator(func):
        _add_subcommand(parent, func)
    return decorator

def argument(*name, **kwargs):
    return([*name], kwargs)

## Logging

## Subprocess wrappers

## Helpers

## Commands

@subcommand()
def testing(args):
    """testing: testing the cli api

    Aliases: t, test

    Args:
       branch: branch to integrate
       files...: One or more files.
       -k|--kill: kill
    """
    print(f"{args!r}")

@subcommand()
def foobar(args):
    """foobar: foo the bars

    foo foo bar bar
    """
    pass

## main

def main():
    args = cli.parse_args()
    print(f"args={args!r}")
    if not args.func:
        cli.print_help()
    else:
        args.func(args)

if __name__ == "__main__":
    main()
