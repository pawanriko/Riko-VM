"""Status flags for the RikoVM CPU (spec section 3.2).

Four flags: Z (zero), C (carry), N (negative), V (overflow). The CPU
sets them according to the flag table in the spec; this class only
stores them and offers the one shared helper every arithmetic/logic
operation needs: ``update_zn``.
"""

MASK_16 = 0xFFFF
SIGN_BIT = 0x8000


class Flags:
    """The four status flags, all clear after reset."""

    def __init__(self):
        self.z = False
        self.c = False
        self.n = False
        self.v = False

    def reset(self):
        """Clear all flags."""
        self.z = False
        self.c = False
        self.n = False
        self.v = False

    def update_zn(self, value):
        """Set Z and N from a 16-bit result value.

        Z is set when the value is zero; N is set when bit 15 is set.
        C and V are untouched -- each operation sets them itself.
        """
        value &= MASK_16
        self.z = value == 0
        self.n = bool(value & SIGN_BIT)

    def as_dict(self):
        """Flags as a plain dict, for the debugger and tests."""
        return {"Z": self.z, "C": self.c, "N": self.n, "V": self.v}

    def __eq__(self, other):
        if not isinstance(other, Flags):
            return NotImplemented
        return self.as_dict() == other.as_dict()

    def __repr__(self):
        bits = "".join(
            name if getattr(self, name.lower()) else "-"
            for name in ("Z", "C", "N", "V")
        )
        return f"Flags({bits})"
