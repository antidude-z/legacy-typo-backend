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


def loads(value: str, max_bytes: int = 5_000_000, max_depth: int = 64):
    """Decode scalar PHP arrays only. Objects/references are never instantiated."""
    if len(value) > max_bytes:
        raise ValueError("Serialized data too large")
    data = value.encode("utf-8")
    if len(data) > max_bytes: raise ValueError("Serialized data too large")
    position = 0
    nodes = 0

    def token_until(delimiter):
        nonlocal position
        end = data.find(delimiter, position)
        if end < 0: raise ValueError("Truncated serialized value")
        result = data[position:end]; position = end + len(delimiter)
        return result

    def expect(expected):
        nonlocal position
        if data[position:position + len(expected)] != expected:
            raise ValueError("Malformed serialized value")
        position += len(expected)

    def parse(depth=0):
        nonlocal position, nodes
        nodes += 1
        if depth > max_depth or nodes > 100_000: raise ValueError("Serialized data limits exceeded")
        kind = data[position:position + 1]; position += 1
        if kind == b"N": expect(b";"); return None
        if kind not in (b"b", b"i", b"d", b"s", b"a"):
            raise ValueError("Only scalar arrays are supported")
        expect(b":")
        if kind in (b"b", b"i", b"d"):
            raw = token_until(b";")
            if kind == b"b":
                if raw not in (b"0", b"1"): raise ValueError("Invalid boolean")
                return raw == b"1"
            if kind == b"i": return int(raw)
            number = Decimal(raw.decode("ascii"))
            if not number.is_finite(): raise ValueError("Invalid number")
            return number
        size = int(token_until(b":"))
        if size < 0 or size > max_bytes: raise ValueError("Invalid size")
        if kind == b"s":
            expect(b'"')
            raw = data[position:position + size]; position += size
            expect(b'";')
            return raw.decode("utf-8")
        if size > 50_000: raise ValueError("Too many array entries")
        expect(b"{")
        result = {}
        for _ in range(size):
            key = parse(depth + 1)
            if not isinstance(key, (str, int)) or isinstance(key, bool): raise ValueError("Invalid array key")
            result[key] = parse(depth + 1)
        expect(b"}")
        return result

    result = parse()
    if position != len(data): raise ValueError("Trailing serialized data")
    return result