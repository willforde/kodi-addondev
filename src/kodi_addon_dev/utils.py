# Standard Library Imports
import argparse
import logging
import sys
import os

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


class RealPath(argparse.Action):
    """
    Custom action to convert given path to a full canonical path.
    Eliminating any symbolic links, expanding user path and environment variables if encountered.
    """
    def __call__(self, _, namespace, value, option_string=None):
        value = unicode_cmdargs(value)
        path = fullpath(value)
        setattr(namespace, self.dest, path)


class RealPathList(argparse.Action):
    """
    Custom action to convert a list of path to a full canonical list of paths.
    Eliminating any symbolic links, expanding user path and environment variables if encountered.
    """
    def __call__(self, _, namespace, values, option_string=None):
        values = map(unicode_cmdargs, values)
        values = map(fullpath, values)
        setattr(namespace, self.dest, list(values))


class CommaList(argparse.Action):
    """
    Custom action to split multiple parameters which are
    separated by a comma, and append then to a empty list.
    """
    def __call__(self, _, namespace, values, option_string=None):
        values = unicode_cmdargs(values)
        items = [value.strip() for value in values.split(",")]
        setattr(namespace, self.dest, items)


class CusstomStreamHandler(logging.StreamHandler):
    """
    A handler class which writes logging records, appropriately formatted, to a stream.
    Debug & Info records will be logged to sys.stdout, and all other records will be logged to sys.stderr.
    """

    def __init__(self):
        super(CusstomStreamHandler, self).__init__(sys.stdout)

    # noinspection PyBroadException
    def emit(self, record):
        """Swap out the stdout stream with stderr if log level is WARNING or greater."""
        if record.levelno >= 30:
            org_stream = self.stream
            self.stream = sys.stderr
            try:
                super(CusstomStreamHandler, self).emit(record)
            finally:
                self.stream = org_stream
        else:
            super(CusstomStreamHandler, self).emit(record)


class CustomFormatter(object):
    def __init__(self):
        self.default_fmt = logging.Formatter("%(relativeCreated)-19s %(levelname)5s: %(message)s")
        self.fmts = {"kodi.dev": logging.Formatter("%(relativeCreated)-19s %(levelname)5s: [kodi-addon-dev] %(message)s")}

    def format(self, record):
        formater = self.fmts.get(record.name, self.default_fmt)
        return formater.format(record)


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


def fullpath(path):  # type: (str) -> str
    """
    Converts given path to a full canonical path. Eliminating any symbolic links,
    expanding user path and environment variables if encountered.
    """
    return os.path.realpath(os.path.expanduser(os.path.expandvars(path)))
