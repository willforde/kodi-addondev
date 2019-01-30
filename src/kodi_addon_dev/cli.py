# Standard Library Imports
import argparse
import logging

# Package imports
from . import repo
from .interactive import Interact
from .utils import RealPath, RealPathList, CommaList
from .support import logger, Addon

try:
    import urllib.parse as urlparse
except ImportError:
    # noinspection PyUnresolvedReferences
    import urlparse


# Create Parser to parse the required arguments
parser = argparse.ArgumentParser(description="Execute kodi plugin")
parser.add_argument("addon", action=RealPath,
                    help="The path to the addon that will be executed. Path can be full or relative.")

parser.add_argument("-d", "--debug", action="store_true",
                    help="Show debug logging output")

parser.add_argument("-c", "--compact", action="store_true",
                    help="Compact view, one line per listitem.")

parser.add_argument("-n", "--no-crop", action="store_true",
                    help="Disable croping of long lines of text.")

parser.add_argument("-p", "--preselect", action=CommaList, default=[],
                    help="Comma separated list of pre selections")

parser.add_argument("-t", "--content-type",
                    help="Type of content that the addon provides. Used when there is more than one type specified"
                    "within provides section of addon.xml. If this is not set it will default to video.")

parser.add_argument("-o", "--custom-repos", dest="remote_repos", nargs="+", action=RealPathList, default=[],
                    help="List of custom repo urls, separated by a space.")

parser.add_argument("-l", "--local-repos", dest="local_repos", nargs="+", action=RealPathList, default=[],
                    help="List of directorys where kodi addons are stored, separated by a space.")


def main():
    # Parse the cli arguments
    cmdargs = parser.parse_args()
    if cmdargs.debug:
        # Enable debug logging
        logger.setLevel(logging.DEBUG)

    # Reverse the list of preselection for faster access
    cmdargs.preselect.reverse()

    # Load the given addon
    addon = Addon.from_path(cmdargs.addon)
    cached = repo.LocalRepo(cmdargs.local_repos, cmdargs.remote_repos, addon)

    # Create base kodi url
    query = "content_type={}".format(cmdargs.content_type) if cmdargs.content_type else ""
    url = "plugin://{}/?{}".format(addon.id, query)
    url_parts = urlparse.urlsplit(url)

    # Execute the addon in interactive mode
    inter = Interact(cmdargs, cached)
    inter.start(url_parts)


# This is only here for development
# Allows this script to be call directly
if __name__ == "__main__":
    main()
