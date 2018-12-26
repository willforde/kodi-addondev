from contextlib import contextmanager
import xbmcaddon
import xbmcgui
import xbmc

from addondev.support_old import data_log, plugin_data

from copy import deepcopy as _deepcopy

_org_plugin_data = _deepcopy(plugin_data)


def reset_plugin_data():
    plugin_data.clear()
    new_data = _deepcopy(_org_plugin_data)
    plugin_data.update(new_data)


@contextmanager
def mock_keyboard(*data):
    xbmc.Keyboard.mock_data.extend(data)
    try:
        yield
    finally:
        del xbmc.Keyboard.mock_data[:]


@contextmanager
def mock_select_dialog(data):
    xbmcgui.Dialog.mock_data["select"].append(data)
    try:
        yield
    finally:
        del xbmcgui.Dialog.mock_data["select"][:]


@contextmanager
def mock_setting(setting_id, value):
    xbmcaddon.mock_data["setting"][setting_id] = value
    try:
        yield
    finally:
        del xbmcaddon.mock_data["setting"][setting_id]
