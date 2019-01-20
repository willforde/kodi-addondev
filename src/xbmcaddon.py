# Package imports
import xbmc

__author__ = 'Team Kodi <http://kodi.tv>'
__credits__ = 'Team Kodi'
__date__ = 'Fri May 01 16:22:07 BST 2015'
__platform__ = 'ALL'
__version__ = '2.25.0'


# noinspection PyShadowingBuiltins, PyPep8Naming
class Addon(object):
    """
    Addon(id=None)

    Creates a new Addon class.

    :param str id: [opt] id of the addon as specified in addon.xml

    .. note: Specifying the addon id is not needed.
             Important however is that the addon folder has the same name as the AddOn id provided in addon.xml.
             You can optionally specify the addon id from another installed addon to retrieve settings from it.

    example::

        self.Addon = xbmcaddon.Addon()
        self.Addon = xbmcaddon.Addon('script.foo.bar')
    """

    def __init__(self, id=None):
        try:
            self._addon = xbmc.session.get_addon(id)
        except KeyError:
            raise KeyError("unknown addon id or missing dependency'{}', ".format(id))

    def getAddonInfo(self, id):
        """
        Returns the value of an addon property as a string.

        :type id: str
        :param id: string - id of the property that the module needs to access.
        :returns: AddOn property as a string.
        :rtype: str

        Choices are::

            author, changelog, description, disclaimer, fanart, icon,
            id, name, path, profile, stars, summary, type, version

        Example::

            version = self.Addon.getAddonInfo('version')
        """
        return self._addon.get_info(id)

    def getLocalizedString(self, id):
        """
        Returns an addon's localize 'unicode string'.

        :param int id: integer - id# for string you want to localize.
        :returns: Localized 'unicode string'
        :rtype: unicode

        Example::

            locstr = self.Addon.getLocalizedString(32000)
        """
        return self._addon.strings[id]

    def getSetting(self, id):
        """
        Returns the value of a setting as a unicode string.

        :param str id: string - id of the setting that the module needs to access.
        :returns: Setting as a unicode string
        :rtype: unicode

        Example::

            apikey = self.Addon.getSetting('apikey')
        """
        return self._addon.settings.get(id, u"")

    def getSettingBool(self, id):
        """
        Returns the value of a setting as a boolean.

        :param str id: string - id of the setting that the module needs to access.
        :returns: Setting as a boolean
        :rtype: bool

        Example::

            enabled = self.Addon.getSettingBool('enabled')
        """
        setting = self.getSetting(id).lower()
        return setting == u"true" or setting == u"1"

    def getSettingInt(self, id):
        """
        Returns the value of a setting as an integer.

        :param str id: string - id of the setting that the module needs to access.
        :returns: Setting as an integer
        :rtype: int

        Example::

            max = self.Addon.getSettingInt('max')
        """
        return int(self.getSetting(id))

    def getSettingNumber(self, id):
        """
        Returns the value of a setting as a floating point number.

        :param str id: string - id of the setting that the module needs to access.
        :returns: Setting as a floating point number
        :rtype: float

        Example::

            max = self.Addon.getSettingNumber('max')
        """
        return float(self.getSetting(id))

    def getSettingString(self, id):
        """
        Returns the value of a setting as a unicode string.

        :param str id: string - id of the setting that the module needs to access.
        :returns: Setting as a unicode string
        :rtype: unicode

        Example::

            apikey = self.Addon.get_setting('apikey')
        """
        return self.getSetting(id)

    # noinspection PyMethodMayBeStatic
    def openSettings(self):
        """Opens this addon settings dialog."""
        pass

    def setSetting(self, id, value):
        """
        Sets a script setting.

        :param str id: string - id of the setting that the module needs to access.
        :param value: string or unicode - value of the setting.
        :type value: str or unicode

        .. note:: You can use the above as keywords for arguments.

        Example::

            self.Addon.setSetting(id='username', value='teamkodi')
        """
        return self._addon.set_setting(id, value)

    def setSettingBool(self, id, value):
        """
        Sets a script setting.

        :param str id: string - id of the setting that the module needs to access.
        :param bool value: boolean - value of the setting.

        :returns: True if the value of the setting was set, false otherwise
        :rtype: bool

        .. note:: You can use the above as keywords for arguments.

        Example::

            self.Addon.setSettingBool(id='enabled', value=True)
        """
        return self.setSetting(id, str(value).lower()) if isinstance(value, bool) else False

    def setSettingInt(self, id, value):
        """
        Sets a script setting.

        :param str id: string - id of the setting that the module needs to access.
        :param int value: integer - value of the setting.

        :returns: True if the value of the setting was set, false otherwise
        :rtype: bool

        .. note:: You can use the above as keywords for arguments.

        Example::

            self.Addon.setSettingInt(id='max', value=5)
        """
        return self.setSetting(id, str(value)) if isinstance(value, int) else False

    def setSettingNumber(self, id, value):
        """
        Sets a script setting.

        :param str id: string - id of the setting that the module needs to access.
        :param value: float - value of the setting.
        :type value: float

        :returns: True if the value of the setting was set, false otherwise
        :rtype: bool

        .. note:: You can use the above as keywords for arguments.

        Example::

            self.Addon.setSettingNumber(id='max', value=5.5)
        """
        return self.setSetting(id, str(value)) if isinstance(value, float) else False

    def setSettingString(self, id, value):
        """
        Sets a script setting.

        :param str id: string - id of the setting that the module needs to access.
        :param value: string or unicode - value of the setting.

        :returns: True if the value of the setting was set, false otherwise
        :rtype: bool

        .. note:: You can use the above as keywords for arguments.

        Example::

            self.Addon.setSettingString(id='username', value='teamkodi')
        """
        return self.setSetting(id, value)
