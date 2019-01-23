# Standard Library Imports
import argparse
import logging
import sys
import os

# Package imports
from .utils import ensure_unicode, unicode_cmdargs
from .support import logger


class RealPath(argparse.Action):
    """
    Custom action to convert given path to a full canonical path,
    eliminating any symbolic links if encountered.
    """
    def __call__(self, _, namespace, value, option_string=None):
        value = unicode_cmdargs(value)
        setattr(namespace, self.dest, os.path.realpath(value))


class AppendSplitter(argparse.Action):
    """
    Custom action to split multiple parameters which are
    separated by a comma, and append then to a default list.
    """
    def __call__(self, _, namespace, values, option_string=None):
        values = unicode_cmdargs(values)
        items = self.default if isinstance(self.default, list) else []
        items.extend(value.strip() for value in values.split(","))
        setattr(namespace, self.dest, items)


# Create Parser to parse the required arguments
parser = argparse.ArgumentParser(description="Execute kodi plugin")
parser.add_argument("addon", action=RealPath,
                    help="The path to the addon that will be executed. Path can be full or relative.")

parser.add_argument("-d", "--debug", action="store_true",
                    help="Show debug logging output")

parser.add_argument("-c", "--compact", action="store_true",
                    help="Compact view, one line per listitem.")

parser.add_argument("-n", "--no-crop", action="store_true",
                    help="Disable croping of long lines of text when in detailed mode.")

parser.add_argument("-p", "--preselect",
                    help="Comma separated list of pre selections")

parser.add_argument("-t", "--content-type",
                    help="Type of content that the addon provides. Used when there is more than one type specified"
                    "within provides section of addon.xml. If this is not set it will default to video.")

parser.add_argument("-o", "--custom-repos", action=AppendSplitter, dest="repos",
                    help="Comma separated list of custom repo urls.")

parser.add_argument("-l", "--local-repos", action=AppendSplitter, dest="local_repos",
                    help="Comma separated list of directorys where kodi addons are stored..")


def main():
    # Parse the cli arguments
    args = parser.parse_args()

    # Enable debug logging if logging flag was given
    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Convert any preselection into a list of selections
    preselect = list(map(int, map(str.strip, args.preselect.split(",")))) if args.preselect else None

    # Execute the addon in interactive mode
    plugin_path = args.addon
    arguments = [plugin_path, preselect]
    if args.content_type:
        arguments.append(args.content_type)

    # Check if plugin actually exists
    if os.path.exists(plugin_path):
        interactive(*arguments, compact_mode=args.compact, no_crop=args.no_crop)

    # Check if we are already in the requested plugin directory if pluginpath was a plugin id
    elif args.pluginpath.startswith("plugin.") and os.path.basename(os.getcwd()) == args.pluginpath:
        arguments[0] = ensure_unicode(os.getcwd(), sys.getfilesystemencoding())
        interactive(*arguments, compact_mode=args.compact, no_crop=args.no_crop)
    else:
        raise RuntimeError("unable to find requested add-on: {}".format(plugin_path.encode("utf8")))


# This is only here for development
# Allows this script to be call directly
if __name__ == "__main__":
    main()
