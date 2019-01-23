# Standard Library Imports
import sys

PY3 = sys.version_info >= (3, 0)
unicode_type = type(u"")


class CacheProperty(object):
    """
    Converts a class method into a property and cache result after first use.

    When property is accessed for the first time, the result is computed and returned.
    The class property is then replaced with an instance attribute with the computed result.
    """

    def __init__(self, func):
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__
        self._func = func

    def __get__(self, instance, owner):
        if instance:
            attr = self._func(instance)
            setattr(instance, self.__name__, attr)
            return attr
        else:
            return self


def ensure_native_str(data, encoding="utf8"):
    """
    Ensures that given string is returned as a native str type, bytes on python2 or unicode on python3.

    :param data: String to convert if needed.
    :param encoding: The encoding to use when encoding.
    :returns: The given string as UTF-8.
    :rtype: str
    """
    if isinstance(data, str):
        return data
    elif isinstance(data, unicode_type):
        # Only executes on python 2
        return data.encode(encoding)
    elif isinstance(data, bytes):
        # Only executes on python 3
        return data.decode(encoding)
    else:
        str(data)


def ensure_unicode(data, encoding="utf8"):
    """
    Ensures that given string is return as a unicode string.

    :param data: String to convert if needed.
    :param encoding: The encoding to use when decoding.
    :returns: The given string as unicode.
    :rtype: unicode
    """
    if isinstance(data, bytes):
        return data.decode(encoding)
    else:
        return unicode_type(data)


def unicode_cmdargs(cmdarg):
    """Convert a command line string to unicode."""
    if isinstance(cmdarg, bytes):
        try:
            # There is a possibility that this will fail
            return cmdarg.decode(sys.getfilesystemencoding())
        except UnicodeDecodeError:
            try:
                # Attept decoding using utf8
                return cmdarg.decode("utf8")
            except UnicodeDecodeError:
                # Fall back to latin-1
                return cmdarg.decode("latin-1")
                # If this fails then we are fucked
    else:
        return cmdarg
