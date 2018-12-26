# -*- coding: utf-8 -*-

# Standard Library Imports
from argparse import ArgumentParser
import logging
import sys
import os

# Package imports
from addondev.interactive_old import interactive
from addondev.utils import safe_path, ensure_unicode
from addondev.support_old import logger, Repo

# Create Parser to parse the required arguments
parser = ArgumentParser(description="Execute kodi plugin")
parser.add_argument("addonpath",
                    help="The path to the addon to execute. Path can be full or relative")

parser.add_argument("-d", "--debug", action="store_true",
                    help="Show debug logging output")

parser.add_argument("-c", "--compact", action="store_true",
                    help="Compact listitem view, to one line per listitem."
                    "In this mode, text length will not be croped to fit withen terminal window.")

parser.add_argument("-n", "--no-crop", action="store_true",
                    help="Disable croping of long lines of text when in detailed mode. Ignored when in compact mode.")

parser.add_argument("-p", "--preselect",
                    help="Comma separated list of pre selections")

parser.add_argument("-t", "--content-type",
                    help="Type of content that the addon provides. Used when there is more than one type specified"
                    "within provides section of addon.xml. If this is not set it will default to video.")

parser.add_argument("-r", "--repo", default="krypton",
                    help="The official kodi repository to use when downloading dependencies. (krypton)")


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
    plugin_path = os.path.realpath(decode_arg(args.addonpath))
    arguments = [plugin_path, preselect]
    if args.content_type:
        arguments.append(args.content_type)

    # Check if plugin actually exists
    if os.path.exists(safe_path(plugin_path)):
        interactive(*arguments, compact_mode=args.compact, no_crop=args.no_crop)

    # Check if we are already in the requested plugin directory if pluginpath was a plugin id
    elif args.pluginpath.startswith("plugin.") and os.path.basename(os.getcwd()) == args.pluginpath:
        arguments[0] = ensure_unicode(os.getcwd(), sys.getfilesystemencoding())
        interactive(*arguments, compact_mode=args.compact, no_crop=args.no_crop)
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
