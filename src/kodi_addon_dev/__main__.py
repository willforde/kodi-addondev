# Standard Library Imports
import argparse
import logging

# Package imports
from kodi_addon_dev import repo, utils
from kodi_addon_dev.interactive import Interact
from kodi_addon_dev.utils import RealPath, RealPathList, CommaList
from kodi_addon_dev.support import base_logger, Addon, setup_paths

try:
    import urllib.parse as urlparse
except ImportError:
    # noinspection PyUnresolvedReferences
    import urlparse


# Create Parser to parse the required arguments
parser = argparse.ArgumentParser(description="Execute kodi plugin")
run_group = parser.add_argument_group(
    title="Interactive Mode",
    description="Arguments related to runing a kodi addon in interactive and debug mode"
)

run_group.add_argument("path", metavar="addon", action=RealPath,
                       help="The path to the addon that will be executed. Path can be full or relative.")

run_group.add_argument("-l", "--log", action="store_true",
                       help="Show logging messages in stdout.")

run_group.add_argument("-d", "--detailed", action="store_true",
                       help="Show listitems in a detailed view.")

run_group.add_argument("-n", "--no-crop", action="store_true",
                       help="Disable croping of long lines of text.")

run_group.add_argument("-c", "--clean-slate", action="store_true",
                       help="Wipe the mock kodi directory, and start with a clean slate.")

run_group.add_argument("-p", "--preselect", metavar="1,2", action=CommaList, default=[],
                       help="Comma separated list of pre selections")

run_group.add_argument("-t", "--content-type", metavar="type",
                       help="Type of content that the addon provides. Used when there is more than one type specified"
                       "within provides section of addon.xml. If this is not set it will default to video.")

run_group.add_argument("-r", "--remote-repos", metavar="url", nargs="+", action=RealPathList, default=[],
                       help="List of custom repo urls, separated by a space.")

run_group.add_argument("-o", "--local-repos", metavar="path", nargs="+", action=RealPathList, default=[],
                       help="List of directorys where kodi addons are stored, separated by a space.")


def main():
    # Parse the cli arguments
    cmdargs = parser.parse_args()
    if cmdargs.log:
        base_handler = utils.CusstomStreamHandler()
        base_handler.setFormatter(utils.CustomFormatter())
        base_handler.setLevel(logging.DEBUG)
        base_logger.addHandler(base_handler)

    # Wipe the mock kodi directory, If requested
    setup_paths(cmdargs.clean_slate)

    # Load the given addon
    addon = Addon.from_path(cmdargs.path)
    cached = repo.LocalRepo(cmdargs.local_repos, cmdargs.remote_repos, addon)

    # Create base kodi url
    query = "content_type={}".format(cmdargs.content_type) if cmdargs.content_type else ""
    url = "plugin://{}/?{}".format(addon.id, query)
    url_parts = urlparse.urlsplit(url)

    # Execute the addon in interactive mode
    inter = Interact(cmdargs, cached)
    inter.start(url_parts)

    # Close all logging handlers
    logging.shutdown()


# This is only here for development
# Allows this script to be call directly
if __name__ == "__main__":
    main()
