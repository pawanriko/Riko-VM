"""Virtual memory for RikoVM (spec section 3.3).

64 KiB, byte-addressed, little-endian. Every access is bounds-checked:
there is no wraparound, and a word access starting at 0xFFFF faults
because its second byte would fall outside memory.
"""

from .errors import MemoryFault

SIZE = 65536
MAX_ADDRESS = SIZE - 1
BYTE_MASK = 0xFF
WORD_MASK = 0xFFFF


class Memory:
    """Flat 64 KiB of bytes."""

    SIZE = SIZE

    def __init__(self):
        self._data = bytearray(SIZE)

    def _check_address(self, address):
        if not isinstance(address, int) or isinstance(address, bool):
            raise MemoryFault(f"address must be an int, got {address!r}")
        if not 0 <= address <= MAX_ADDRESS:
            raise MemoryFault(f"address out of range: {address:#x}")

    def _check_word_address(self, address):
        self._check_address(address)
        if address == MAX_ADDRESS:
            raise MemoryFault(
                f"word access at {address:#06x} would read past end of memory"
            )

    def read_byte(self, address):
        """Read one byte at ``address``."""
        self._check_address(address)
        return self._data[address]

    def write_byte(self, address, value):
        """Write the low 8 bits of ``value`` at ``address``."""
        self._check_address(address)
        self._data[address] = value & BYTE_MASK

    def read_word(self, address):
        """Read a 16-bit little-endian word at ``address``."""
        self._check_word_address(address)
        return self._data[address] | (self._data[address + 1] << 8)

    def write_word(self, address, value):
        """Write a 16-bit little-endian word at ``address``."""
        self._check_word_address(address)
        value &= WORD_MASK
        self._data[address] = value & BYTE_MASK
        self._data[address + 1] = (value >> 8) & BYTE_MASK

    def read_bytes(self, address, length):
        """Read ``length`` bytes starting at ``address`` (bounds-checked)."""
        if length < 0:
            raise MemoryFault(f"negative read length: {length}")
        if length == 0:
            return b""
        self._check_address(address)
        if address + length > SIZE:
            raise MemoryFault(
                f"read of {length} bytes at {address:#06x} runs past memory"
            )
        return bytes(self._data[address : address + length])

    def load(self, data, address):
        """Copy ``data`` into memory starting at ``address``.

        Bounds-checked before anything is written: a load that does not
        fit faults without changing memory.
        """
        self._check_address(address)
        if address + len(data) > SIZE:
            raise MemoryFault(
                f"load of {len(data)} bytes at {address:#06x} "
                "does not fit in memory"
            )
        self._data[address : address + len(data)] = data

    def __len__(self):
        return SIZE
