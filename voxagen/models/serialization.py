from __future__ import annotations

import dataclasses
import typing
from typing import Any, TypeVar

T = TypeVar("T")


def to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj


def _coerce(tp: Any, value: Any) -> Any:
    origin = typing.get_origin(tp)
    if dataclasses.is_dataclass(tp) and isinstance(value, dict):
        return from_dict(tp, value)
    if origin is typing.Union or str(origin) == "types.UnionType":
        if value is None:
            return None
        for arg in typing.get_args(tp):
            if arg is type(None):
                continue
            try:
                return _coerce(arg, value)
            except (TypeError, ValueError):
                continue
        return value
    if origin in (list, tuple) and isinstance(value, (list, tuple)):
        args = typing.get_args(tp)
        inner = args[0] if args else Any
        return [_coerce(inner, v) for v in value]
    if origin is dict and isinstance(value, dict):
        args = typing.get_args(tp)
        inner = args[1] if len(args) == 2 else Any
        return {k: _coerce(inner, v) for k, v in value.items()}
    if tp is float and isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if tp is int and isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    if tp is bool:
        return bool(value)
    if tp is str and value is not None:
        return str(value)
    return value


def from_dict(cls: type[T], data: dict | None) -> T:
    if data is None:
        return cls()
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name in data:
            try:
                kwargs[f.name] = _coerce(hints.get(f.name, Any), data[f.name])
            except Exception:
                pass
    return cls(**kwargs)
