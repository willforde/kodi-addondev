# -*- coding: utf-8 -*-
from __future__ import print_function

# Standard Library Imports
import sys
import os

# Package imports
from addondev import repo, support2


def initializer(addon_path, content_type=None):
    """
    Setup & initialize the mock kodi environment.

    When a plugin path is givin, all environment variables that relate to kodi will be setup.
    All the add-on's required dependencies will be downloaded and a dummy kodi directory will be created.

    :param str addon_path: Path to the add-on.
    :param str content_type: The content type to use when multiple providers are set within addon.xml
    """

    # Load the given addon, raise ValueError if addon is not valid
    xml_path = os.path.join(addon_path, "addon.xml")
    if os.path.exists(xml_path):
        addon = support2.Addon.from_file(xml_path)
        addon.setup_paths()
    else:
        raise ValueError("'{}' is not a valid kodi addon, missing 'addon.xml'".format(addon_path))

    # Download required dependencies
    repo.process_dependencies(addon.dependencies)

    # Setup environment
    sys.path.insert(0, addon_path)
    content_type = addon.valid_type(content_type)
    sys.argv = ["plugin://{}".format(addon.id), -1, "?content_type={}".format(content_type) if content_type else ""]
