"""Auto-discovers languages/*.py (LANGUAGE) and frameworks/*.py (FRAMEWORKS).

Adding a language or framework = dropping a module into the right folder; nothing else to register.
"""
from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache

from . import frameworks as _fw_pkg
from . import languages as _lang_pkg
from .frameworks.base import Framework
from .languages.base import Language


def _modules(pkg):
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name != "base":
            yield importlib.import_module(f"{pkg.__name__}.{info.name}")


@lru_cache(maxsize=1)
def languages() -> dict[str, Language]:
    out = {}
    for mod in _modules(_lang_pkg):
        lang = getattr(mod, "LANGUAGE", None)
        if lang is not None:
            out[lang.name] = lang
    return dict(sorted(out.items()))


@lru_cache(maxsize=1)
def frameworks() -> list[Framework]:
    out: list[Framework] = []
    for mod in _modules(_fw_pkg):
        out.extend(getattr(mod, "FRAMEWORKS", ()))
    return sorted(out, key=lambda f: f.name)


@lru_cache(maxsize=1)
def code_extensions() -> set[str]:
    return {"." + e for lang in languages().values() for e in lang.extensions}
