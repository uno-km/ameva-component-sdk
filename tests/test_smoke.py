# Copyright (c) 2026 Uno Kim / AMEVA Foundation. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Import and dataclass smoke tests (the package must stay importable on Python 3.8)."""
import dataclasses
import importlib
import pkgutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import ameva_component


def test_every_module_imports():
    names = [m.name for m in pkgutil.iter_modules(ameva_component.__path__)]
    assert len(names) >= 14
    for name in names:
        importlib.import_module("ameva_component." + name)


def test_version_matches_metadata():
    assert ameva_component.__version__ == "0.1.2"


def test_dataclasses_do_not_require_slots():
    # slots=True needs Python 3.10; the classes must be plain dataclasses.
    for name in ("identity", "instance", "manifest"):
        mod = importlib.import_module("ameva_component." + name)
        classes = [c for c in vars(mod).values()
                   if isinstance(c, type) and dataclasses.is_dataclass(c) and c.__module__ == mod.__name__]
        assert classes, name
        for cls in classes:
            assert "__slots__" not in cls.__dict__, cls
