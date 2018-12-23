# -*- coding: utf-8 -*-
from __future__ import print_function

# Standard Library Imports
import sys
import os

# Package imports
from addondev import repo, support2


def initializer(addon_path):
    """
    Setup & initialize the mock kodi environment.

    When a plugin path is givin, all environment variables that relate to kodi will be setup.
    All the add-on's required dependencies will be downloaded and a dummy kodi directory will be created.

    :param str addon_path: Path to the add-on.
    """

    # Load the given addon, raise ValueError if addon is not valid
    xml_path = os.path.join(addon_path, "addon.xml")
    if os.path.exists(xml_path):
        addon = support2.Addon.from_file(xml_path)
    else:
        raise ValueError("'{}' is not a valid kodi addon, missing 'addon.xml'".format(addon_path))

    # Download required dependencies
    addons = list(repo.process_dependencies(addon.dependencies))
    addons.append(addon)

    # Setup environment

    sys.argv = ["plugin://{}".format(addon.id), -1, ""]
    if addon.type == "xbmc.python.pluginsource":
        sys.path.insert(0, addon.path)
    else
