# -*- coding: utf-8 -*-
"""Copy named register fields onto an ORM object when the attribute exists."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def apply_fields(obj: Any, data: Mapping[str, Any], names: Iterable[str]) -> None:
    for name in names:
        if name not in data:
            continue
        if hasattr(obj, name):
            setattr(obj, name, data[name])
