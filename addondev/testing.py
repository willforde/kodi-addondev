import xbmc


def mock_keyboard(data):
    xbmc.Keyboard.mock_data.append(data)

