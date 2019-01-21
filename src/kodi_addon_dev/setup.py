# Standard Library Imports
import sys

# Package imports
from . import tesseract
import xbmc


def initializer(addon_path, repos=None):
    """
    Setup & initialize the mock kodi environment.

    When a plugin path is givin, all environment variables that relate to kodi will be setup.
    All the add-on's required dependencies will be downloaded and a dummy kodi directory will be created.

    The format for the repo url is as follows: 'http://mirrors.kodi.tv/addons/krypton'

    :param str addon_path: Path to the add-on.
    :param list repos: List of unofficial kodi repos to use.
    """
    xbmc.session = tracker = tesseract.Tesseract(addon_path, repos)
    addon = tracker.get_addon()
    sys.argv = ["plugin://{}".format(addon.id), -1, ""]
