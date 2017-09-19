# -*- coding: utf-8 -*-

# Standard Library Imports
from argparse import ArgumentParser
import logging
import sys
import os

# Package imports
from addondev.interactive import interactive
from addondev.utils import safe_path, ensure_unicode
from addondev.support import logger, Repo

# Create Parser to parse the required arguments
parser = ArgumentParser(description="Execute kodi plugin")
parser.add_argument("pluginpath",
                    help="The path to the plugin to execute. Path can be full or relative")

parser.add_argument("-d", "--debug",
                    help="Show debug logging output", action="store_true")

parser.add_argument("-p", "--preselect",
                    help="Comma separated list of pre selections")

parser.add_argument("-c", "--content-type",
                    help="The content type to list, if more than one type is available")

parser.add_argument("-r", "--repo",
                    help="The official kodi repository to use when downloading dependencies. (krypton)",
                    default="krypton")


def main():
    # Parse the cli arguments
    args = parser.parse_args(sys.argv[1:])

    # Enable debug logging if logging flag was given
    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Convert any preselection into a list of selections
    preselect = list(map(int, args.preselect.split(","))) if args.preselect else None

    # Set the repo to use for dependency resolving
    Repo.repo = args.repo

    # Execute the addon in interactive mode
    plugin_path = os.path.realpath(decode_arg(args.pluginpath))
    arguments = [plugin_path, preselect]
    if args.content_type:
        arguments.append(args.content_type)

    # Check if plugin actually exists
    if os.path.exists(safe_path(plugin_path)):
        interactive(*arguments)

    # Check if we are already in the requested plugin directory if pluginpath was a plugin id
    elif args.pluginpath.startswith("plugin.") and os.path.basename(os.getcwd()) == args.pluginpath:
        arguments[0] = ensure_unicode(os.getcwd(), sys.getfilesystemencoding())
        interactive(*arguments)
    else:
        raise RuntimeError("unable to find requested add-on: {}".format(plugin_path.encode("utf8")))


def decode_arg(path):
    # Execute the addon in interactive mode
    if isinstance(path, bytes):
        try:
            # There is a possibility that this will fail
            return path.decode(sys.getfilesystemencoding())
        except UnicodeDecodeError:
            try:
                # Attept decoding using utf8
                return path.decode("utf8")
            except UnicodeDecodeError:
                # Fall back to latin-1
                return path.decode("latin-1")
                # If this fails then we are fucked
    else:
        return path


# This is only here for development
# Allows this script to be call directly
if __name__ == "__main__":
    main()
