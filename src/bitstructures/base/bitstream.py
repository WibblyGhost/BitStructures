from collections.abc import Generator
from typing import Self, overload

from bitarray import bitarray
from bitarray.util import ba2int, int2ba

from bitstructures.exceptions import ReadError, SizeError, WriteError
from bitstructures.typing import Buffer, BufferCmp


class BitStream:
    """
    Custom IO class which converts a bytestream into a bitstream with read and write methods.

    Makes use of a string as it's buffer to keep object access fast and efficient.
    Noting that some of the methods must read the whole buffer object.

    `peek`, `read`, `write` and `length` are all functions which work on the active buffer
    instead of reading the memory object.
    """

    def __init__(self, buffer: Buffer = b"", /) -> None:
        self.stream: bitarray
        assert isinstance(buffer, bitarray | bytes | str)
        if isinstance(buffer, bitarray):
            self.stream = buffer
            return

        self.stream = bitarray()
        if isinstance(buffer, str):
            # Strings, '0b1001' or '1001'
            buffer = self._validate_string(buffer)
        self.stream += bitarray(buffer)

    @staticmethod
    def _validate_string(string: str) -> str:
        string = string.removeprefix("0b")
        if not all(i in {"0", "1"} for i in string):
            raise TypeError("Buffer can only contain binary integers: 0's/1's")
        return string

    @property
    def bin(self) -> str:
        """Gets a binary representation by reading the string buffer."""
        return self.stream.to01()

    def __str__(self) -> str:
        """
        Returns a nicely formatted representation of the underlying buffer,
        if this object is divisable by 8 (a byte) then it will show bytes as it's
        string representation.
        """
        if len(self) % 8 == 0:
            return repr(bytes(self))
        return f"0b{self.bin}"

    def __repr__(self) -> str:
        """
        Returns a nicely formatted representation of the underlying buffer,
        if this object is divisable by 8 (a byte) then it will show bytes as it's
        string representation.
        """
        if len(self) % 8 == 0:
            return f"{self.__class__.__name__}({bytes(self)!r})"
        return f"{self.__class__.__name__}(0b{self.bin})"

    def __len__(self) -> int:
        """Returns the bit size of the current object."""
        return len(self.stream)

    def __int__(self) -> int:
        """
        Converts the buffer into an integer representation, this
        could lead to an integer overflow if you attempt to read
        a buffer that is larger than the size of an integer.
        """
        return ba2int(self.stream)

    def __bytes__(self) -> bytes:
        """
        Returns a bytestream from the string buffer by iterating through the buffer
        and applying integer conversions on the string to convert to bytes.
        """
        if len(self) % 8 != 0:
            raise SizeError(
                f"Cannot convert a {self.__class__.__name__} of length {len(self)} to bytes, "
                f"must be divisable by 8"
            )
        return self.stream.tobytes()

    def __hash__(self) -> int:
        """Provide hashing functionality to our bitstream."""
        return hash(self.stream.to01())

    def __and__(self, other: BufferCmp) -> Self:
        if isinstance(other, BitStream):
            return self.__class__(self.stream & other.stream)
        if isinstance(other, bitarray | bytes | str):
            # Recurse into the above statement
            return self & self.__class__(other)
        return NotImplemented

    def __or__(self, other: BufferCmp) -> Self:
        if isinstance(other, BitStream):
            return self.__class__(self.stream | other.stream)
        if isinstance(other, bitarray | bytes | str):
            # Recurse into the above statement
            return self | self.__class__(other)
        return NotImplemented

    def __xor__(self, other: BufferCmp) -> Self:
        if isinstance(other, BitStream):
            return self.__class__(self.stream ^ other.stream)
        if isinstance(other, bitarray | bytes | str):
            # Recurse into the above statement
            return self ^ self.__class__(other)
        return NotImplemented

    def __invert__(self) -> Self:
        return self.__class__(~self.stream)

    def __lshift__(self, n: int) -> Self:
        return self.__class__(self.stream << n)

    def __rshift__(self, n: int) -> Self:
        return self.__class__(self.stream >> n)

    def __eq__(self, other: object) -> bool:
        """
        Checks if the string buffer is the same as the other object,
        if the other object is bytes | str, convert it to a buffer first.
        """
        if isinstance(other, BitStream):
            return self.stream == other.stream
        if isinstance(other, bitarray | bytes | str):
            # Recurse into the above statement
            return self == self.__class__(other)
        return False

    def __add__(self, other: BufferCmp) -> Self:
        """
        Append another string buffer into this buffer by writing the
        contents of the other buffer into our StringIO instance.
        """
        if isinstance(other, BitStream):
            return self.__class__(self.stream + other.stream)
        if isinstance(other, bitarray | bytes | str):
            # Recurse into the above statement
            return self + self.__class__(other)
        return NotImplemented

    def __iadd__(self, other: BufferCmp) -> Self:
        """
        Append another string buffer into this buffer by writing the
        contents of the other buffer into our StringIO instance.
        """
        if isinstance(other, BitStream):
            self.stream += other.stream
            return self
        if isinstance(other, bitarray | bytes | str):
            # Recurse into the above statement
            self.stream += self.__class__(other).stream
            return self
        return NotImplemented

    def __iter__(self) -> Generator[int]:
        """Returns either a 1 or 0 for all bits in the stream."""
        yield from self.stream

    @overload
    def __getitem__(self, s: int) -> int: ...
    @overload
    def __getitem__(self, s: slice) -> Self: ...
    def __getitem__(self, s: slice | int) -> "Self | int":
        """Allow string slicing methods upon this class."""
        if isinstance(s, int):
            # The bitarray library returns an integer when getitem is int
            return self.stream[s]
        return self.__class__(self.stream[s])

    def peek(self, size: int) -> Self:
        """Looks through the string buffer without modifying the stream."""
        return self.__class__(self.stream[:size])

    def read(self, size: int | None = -1) -> Self:
        """Reads a specified amount of bits through the string buffer modifying the stream."""
        if size is None or size < 0:
            return self
        if size > len(self):
            raise ReadError(
                f"Cannot read {size} bits, reached the EOS or "
                f"the current stream is shorter than specified size. stream={len(self)}"
            )
        try:
            # Modify the stream buffer
            out, self.stream = self.stream[:size], self.stream[size:]
            return self.__class__(out)
        except Exception as err:
            raise ReadError from err

    def write(self, value: "int | Self", size: int) -> None:
        """
        Writes values or bit buffers of a specified bit size
        through the string buffer modifying the stream.
        """
        if value.bit_length() > size:
            raise WriteError(
                f"Cannot write value {value} of size {value.bit_length()} "
                f"into a stream of size {size}"
            )
        try:
            if isinstance(value, BitStream):
                if value.bit_length() > size:
                    raise WriteError(
                        f"Cannot write a stream {value} of size {value.bit_length()}, "
                        f"into a stream of size {size}"
                    )
                # Left pad the stream with bits
                self += value.ljust(size)
                return
            self += int2ba(value, size)
        except Exception as err:
            raise WriteError from err

    def copy(self) -> Self:
        """Returns a complete copy of the underlying bitstring and assigns it to a new object."""
        return self.__class__(self.stream.copy())

    def bit_length(self) -> int:
        """Just returns the len of this BitStream, meant to mirror int.bit_length()."""
        return len(self)

    def ljust(self, width: int, fillbit: int = 0) -> Self:
        """Returns a copy of the stream right-padded with the fill character."""
        if fillbit not in {0, 1}:
            raise ValueError("fillbit must be '0' or '1'")
        if len(self) >= width:
            return self.copy()
        padding = bitarray([fillbit]) * (width - len(self))
        return self + padding

    def rjust(self, width: int, fillbit: int = 0) -> Self:
        """Returns a copy of the stream left-padded with the fill character."""
        if fillbit not in {0, 1}:
            raise ValueError("fillbit must be '0' or '1'")
        if len(self) >= width:
            return self.copy()
        padding = bitarray([fillbit]) * (width - len(self))
        return self.__class__(padding + self.stream)
