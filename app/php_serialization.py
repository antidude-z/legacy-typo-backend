"""Serialize scalar calculation arrays without PHP object deserialization."""
from decimal import Decimal
import math


def dumps(value) -> str:
    if value is None:
        return "N;"
    if isinstance(value, bool):
        return f"b:{int(value)};"
    if isinstance(value, int):
        return f"i:{value};"
    if isinstance(value, (float, Decimal)):
        if not math.isfinite(float(value)):
            raise ValueError("Non-finite calculation value")
        return f"d:{value};"
    if isinstance(value, str):
        return f's:{len(value.encode("utf-8"))}:"{value}";'
    if isinstance(value, (list, tuple)):
        value = dict(enumerate(value))
    if isinstance(value, dict):
        return f"a:{len(value)}:{{" + "".join(dumps(key) + dumps(item) for key, item in value.items()) + "}"
    raise TypeError(f"Unsupported PHP scalar type: {type(value).__name__}")