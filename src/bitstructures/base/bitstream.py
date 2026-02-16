from typing import Any, Self

from bitarray import bitarray

from bitstructures.exceptions import InitError, ReadError, SizeError, WriteError
from bitstructures.typing import SupportsBitArray


class BitStream:
    """Custom IO class which converts a bytestream into a bitstream with read and write methods."""

    def __init__(self, buffer: bytes | bitarray | str = b"", *, size: int = -1) -> None:
        if isinstance(buffer, str) and buffer.startswith("0b"):
            buffer = buffer.removeprefix("0b")

        if not isinstance(buffer, bytes | bitarray | str):
            raise InitError(
                f"Cannot initialize a {self.__class__.__name__} "
                f"with a buffer type of {type(buffer)}, expected {bytes | bitarray | str}"
            )

        if size > 0:
            self.bitarray = bitarray(size)
            self += buffer
            return
        self.bitarray = bitarray(buffer)

    def peek(self, size: int) -> "BitStream":
        return BitStream(self.bitarray[:size])

    def read(self, size: int | None = -1) -> "BitStream":
        if size is None or size < 0:
            return self
        if size > len(self):
            raise ReadError(
                f"Cannot read {size} bits, reached the EOS or "
                f"the current stream is shorter that specified size. stream={len(self)}"
            )
        try:
            raw, self.bitarray = self.bitarray[:size], self.bitarray[size:]
            return BitStream(raw)
        except Exception as err:
            raise ReadError from err

    def write(self, value: "int | BitStream", size: int) -> None:
        try:
            if isinstance(value, BitStream):
                self.bitarray += value.bitarray
                return
            self.bitarray += bitarray(bin(value)[2:].rjust(size, "0"))
        except Exception as err:
            raise WriteError from err

    def copy(self) -> Self:
        return self.__class__(self.bitarray.copy())

    @property
    def bin(self) -> str:
        return self.bitarray.to01()

    def __str__(self) -> str:
        if len(self) % 8 == 0:
            return repr(bytes(self))
        return f"0b{self.bin}"

    def __repr__(self) -> str:
        if len(self) % 8 == 0:
            return f"{self.__class__.__name__}({bytes(self)!r})"
        return f"{self.__class__.__name__}(0b{self.bin})"

    def __len__(self) -> int:
        return len(self.bitarray)

    def __int__(self) -> int:
        return int(self.bin, 2)

    def __getitem__(self, s: slice) -> "BitStream":
        return BitStream(self.bitarray[s])

    def __hash__(self) -> int:
        return hash(self.bin)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SupportsBitArray):
            return self.bitarray == other.bitarray
        if isinstance(other, bitarray):
            return self.bitarray == other
        if isinstance(other, bytes):
            return self.bitarray == bitarray(other)
        raise TypeError(f"Cannot compare a {self.__class__.__name__} with a {type(other)}")

    def __add__(self, other: Any) -> Self:
        if isinstance(other, SupportsBitArray):
            self.bitarray += other.bitarray
        elif isinstance(other, bitarray):
            self.bitarray += other
        elif isinstance(other, bytes):
            self.bitarray += bitarray(other)
        elif isinstance(other, str) and other.startswith("0b"):
            self.bitarray += bitarray(other.removeprefix("0b"))
        else:
            raise TypeError(f"Cannot add {type(other)} to a {BitStream.__name__}")
        return self

    def __bytes__(self) -> bytes:
        if len(self) % 8 != 0:
            raise SizeError(
                f"Cannot convert a BitStream of length {len(self)} to bytes, must be divisable by 8"
            )
        return self.bitarray.tobytes()


if __name__ == "__main__":
    bits = BitStream(b"\xff\xdd")
    stream = bits.read(7)
    bits.write(24, 8)
    int(stream)
    str(bits)
    repr(bits)
