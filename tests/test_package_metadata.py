"""Scaffold sanity checks: the package is installed, importable, and
version-consistent."""

import re
from importlib.metadata import version

import finsight


def test_version_has_semver_format() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", finsight.__version__)


def test_version_matches_installed_metadata() -> None:
    assert version("finsight") == finsight.__version__
