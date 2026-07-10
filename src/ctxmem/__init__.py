"""ctxmem - shareable, git-native project memory for AI coding agents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ctxmem")
except PackageNotFoundError:  # not installed (e.g. running from a source tree)
    __version__ = "0.0.0"
