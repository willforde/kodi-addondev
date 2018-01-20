from contextlib import contextmanager
import xbmcgui
import xbmc


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
