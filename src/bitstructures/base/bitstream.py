from typing import Any, Self

from bitarray import bitarray
from bitarray.util import ba2int, int2ba

from bitstructures.exceptions import ReadError, SizeError, WriteError


class BitStream:
    """
    Custom IO class which converts a bytestream into a bitstream with read and write methods.

    Makes use of a string as it's buffer to keep object access fast and efficient.
    Noting that some of the methods must read the whole buffer object.

    `peek`, `read`, `write` and `length` are all functions which work on the active buffer
    instead of reading the memory object.
    """

    def __init__(self, buffer: bitarray | bytes | str = b"", /) -> None:
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
                f"Cannot convert a BitStream of length {len(self)} to bytes, must be divisable by 8"
            )
        return self.stream.tobytes()

    def __hash__(self) -> int:
        """Provide hashing functionality to our bitstream."""
        return hash(self.stream)

    def __eq__(self, other: object) -> bool:
        """
        Checks if the string buffer is the same as the other object,
        if the other object is bytes | str, convert it to a buffer first.
        """
        if isinstance(other, BitStream):
            return self.stream == other.stream
        if isinstance(other, bytes | str):
            # Recurse into the above statement
            return self == BitStream(other)
        raise TypeError(f"Cannot compare a {self.__class__.__name__} with a {type(other)}")

    def __add__(self, other: Any) -> Self:
        """
        Append another string buffer into this buffer by writing the
        contents of the other buffer into our StringIO instance.
        """
        if isinstance(other, BitStream):
            self.stream += other.stream
        elif isinstance(other, bitarray | bytes | str):
            # Recurse into the above statement
            self += BitStream(other)
            return self
        else:
            raise TypeError(f"Cannot add {type(other)} to a {BitStream.__name__}")
        return self

    def __getitem__(self, s: slice) -> "BitStream":
        """Allow string slicing methods upon this class."""
        return BitStream(self.stream[s])

    def peek(self, size: int) -> "BitStream":
        """Looks through the string buffer without modifying the stream."""
        return BitStream(self.stream[:size])

    def read(self, size: int | None = -1) -> "BitStream":
        """Reads a specified amount of bits through the string buffer modifying the stream."""
        if size is None or size < 0:
            return self
        if size > len(self):
            raise ReadError(
                f"Cannot read {size} bits, reached the EOS or "
                f"the current stream is shorter that specified size. stream={len(self)}"
            )
        try:
            # Modify the stream buffer
            out, self.stream = self.stream[:size], self.stream[size:]
            return BitStream(out)
        except Exception as err:
            raise ReadError from err

    def write(self, value: "int | BitStream", size: int) -> None:
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
                self += value
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
