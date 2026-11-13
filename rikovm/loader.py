"""Program image format (``RKP1``) and loader (spec section 7).

Image layout, all multi-byte fields little-endian:

    offset  size  field
    0       4     magic bytes: ``RKP1``
    4       2     entry point address
    6       2     code length in bytes (must equal the remaining size)
    8       N     code bytes

The loader validates everything before touching the machine: a bad
image faults without a partial load.
"""

from .errors import LoadError

MAGIC = b"RKP1"
HEADER_SIZE = 8
MEMORY_SIZE = 65536


def build_image(code, entry=0x0000):
    """Build an RKP1 image from raw ``code`` bytes and an entry point."""
    if not 0 <= entry <= 0xFFFF:
        raise LoadError(f"entry point {entry:#x} is out of range")
    if len(code) > 0xFFFF:
        raise LoadError(f"code of {len(code)} bytes does not fit the image format")
    if entry + len(code) > MEMORY_SIZE:
        raise LoadError(
            f"code of {len(code)} bytes at entry {entry:#06x} "
            "does not fit in memory"
        )
    return (
        MAGIC
        + entry.to_bytes(2, "little")
        + len(code).to_bytes(2, "little")
        + bytes(code)
    )


def parse_image(data):
    """Validate an image; return ``(entry, code)``.

    Raises LoadError on bad magic, truncation, length mismatch, or
    code that would not fit in memory.
    """
    data = bytes(data)
    if len(data) < HEADER_SIZE:
        raise LoadError(
            f"image is {len(data)} bytes, smaller than the "
            f"{HEADER_SIZE}-byte header"
        )
    if data[0:4] != MAGIC:
        raise LoadError(f"bad magic {data[0:4]!r}: expected {MAGIC!r}")
    entry = int.from_bytes(data[4:6], "little")
    length = int.from_bytes(data[6:8], "little")
    if len(data) - HEADER_SIZE != length:
        raise LoadError(
            f"header declares {length} code bytes but the image "
            f"holds {len(data) - HEADER_SIZE}"
        )
    if entry + length > MEMORY_SIZE:
        raise LoadError(
            f"code of {length} bytes at entry {entry:#06x} "
            "does not fit in memory"
        )
    return entry, data[HEADER_SIZE:]


def load_image(cpu, data):
    """Load an image into a CPU: validate, copy code, reset state.

    Returns ``{"entry": ..., "length": ...}``. On any validation
    failure the CPU is untouched.
    """
    entry, code = parse_image(data)
    cpu.memory.load(code, entry)
    cpu.reset(entry)
    return {"entry": entry, "length": len(code)}
