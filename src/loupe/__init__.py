"""loupe: a research testbed for looking inside language models."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("loupelab")
except PackageNotFoundError:
    __version__ = "0.0.0"
