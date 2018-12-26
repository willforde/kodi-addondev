# -*- coding: utf-8 -*-
from __future__ import print_function

# Standard Library Imports
from collections import OrderedDict
import sys
import os

# Third party imports
import appdirs

# Package Imports
from addondev.utils import ensure_unicode, safe_path


def setup_paths():
    # Location of support files
    system_dir = os.path.join(ensure_unicode(os.path.dirname(__file__), sys.getfilesystemencoding()), u"data")
    kodi_paths["support"] = system_dir

    # Kodi path structure
    kodi_paths["home"] = home = appdirs.user_cache_dir(u"kodi_mock")
    kodi_paths["addons"] = addon_dir = os.path.join(home, u"addons")
    kodi_paths["packages"] = os.path.join(addon_dir, u"packages")
    kodi_paths["temp"] = temp_dir = os.path.join(home, u"temp")
    kodi_paths["system"] = os.path.join(home, u"system")
    kodi_paths["profile"] = userdata = os.path.join(home, u"userdata")
    kodi_paths["data"] = os.path.join(userdata, u"addon_data")
    kodi_paths["database"] = os.path.join(userdata, u"Database")
    kodi_paths["thumbnails"] = os.path.join(userdata, u"Thumbnails")
    kodi_paths["playlists"] = playlists = os.path.join(userdata, u"playlists")
    kodi_paths["musicplaylists"] = os.path.join(playlists, u"music")
    kodi_paths["videoplaylists"] = os.path.join(playlists, u"video")

    # Ensure that all directories exists
    for path in kodi_paths.values():
        path = safe_path(path)
        if not os.path.exists(path):
            os.makedirs(path)

    # Rest of kodi's special paths
    kodi_paths["logpath"] = os.path.join(temp_dir, u"kodi.log")
    kodi_paths["masterprofile"] = userdata
    kodi_paths["masterprofile"] = userdata
    kodi_paths["userdata"] = userdata
    kodi_paths["subtitles"] = temp_dir
    kodi_paths["recordings"] = temp_dir
    kodi_paths["screenshots"] = temp_dir
    kodi_paths["cdrips"] = temp_dir
    kodi_paths["skin"] = temp_dir
    kodi_paths["xbmc"] = home

    # Return the support system directory and addon directory
    return system_dir, addon_dir


def handle_prompt(prompt):
    if data_pipe:
        data_pipe.send({"prompt": prompt})
        return data_pipe.recv()
    else:
        return input(prompt)
