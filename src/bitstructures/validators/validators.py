from collections.abc import Iterable

from bitstring import ConstBitStream

from bitstructures.base.codec import BitsInt, Container, StackV, Value
from bitstructures.exceptions import BlacklistError, WhitelistError


class Blacklisted(BitsInt):
    def __init__(self, size: int, array: Iterable[int]) -> None:
        super().__init__(size)
        self._array = array

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        value, size = self._read_io(io, parent)
        if value.uint in self._array:
            raise BlacklistError(
                f"Cannot parse value {value} as it's listed in the blacklisted values {self._array}"
            )
        parent.push(Value(self.name, value.uint, size))

    def io_build(self, parent: StackV, container: Container) -> None:
        if (value := container[self.name]) in self._array:
            raise BlacklistError(
                f"Cannot build value {value} as it's listed in the blacklisted values {self._array}"
            )
        super().io_build(parent, container)


class Whitelisted(BitsInt):
    def __init__(self, size: int, array: Iterable[int]) -> None:
        super().__init__(size)
        self._array = array

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        value, size = self._read_io(io, parent)
        if value.uint not in self._array:
            raise WhitelistError(
                f"Cannot parse value {value} as it's not "
                f"listed as a whitelisted value {self._array}"
            )

        parent.push(Value(self.name, value.uint, size))

    def io_build(self, parent: StackV, container: Container) -> None:
        if (value := container[self.name]) not in self._array:
            raise WhitelistError(
                f"Cannot build value {value} as it's not listed "
                f"as a whitelisted value {self._array}"
            )
        super().io_build(parent, container)
