import pkgutil
import importlib
import pytest


def test_all_imports():
    """ Ensures no circular import or missing module errors across codebase.
    """
    for _, name, _ in pkgutil.walk_packages(["inphms"]):
        importlib.import_module(f"inphms.{name}")
