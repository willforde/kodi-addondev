import xbmcgui
import xbmc


def mock_keyboard(data):
    xbmc.Keyboard.mock_data.append(data)


def mock_select_dialog(data):
    xbmcgui.Dialog.mock_data["select"].append(data)
