from collections.abc import Iterable
from typing import override

from bitstring import ConstBitStream

from bitstructures.base.codec import BitsInt, Container, StackC, StackV, Value
from bitstructures.exceptions import BlacklistError, WhitelistError


class Blacklisted(BitsInt):
    @override
    def __init__(self, size: int, array: Iterable[int]) -> None:
        super().__init__(size)
        self._array = array

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        value, size = self._read_io(parent, codecs, io)
        if value.uint in self._array:
            raise BlacklistError(
                f"Cannot parse value {value} as it's listed in the blacklisted values {self._array}"
            )
        parent.push(Value(self.name, value.uint, size))
        codecs.push(self)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if (value := container[self.name]) in self._array:
            raise BlacklistError(
                f"Cannot build value {value} as it's listed in the blacklisted values {self._array}"
            )
        super().io_build(parent, codecs, container)


class Whitelisted(BitsInt):
    @override
    def __init__(self, size: int, array: Iterable[int]) -> None:
        super().__init__(size)
        self._array = array

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        value, size = self._read_io(parent, codecs, io)
        if value.uint not in self._array:
            raise WhitelistError(
                f"Cannot parse value {value} as it's not "
                f"listed as a whitelisted value {self._array}"
            )
        parent.push(Value(self.name, value.uint, size))
        codecs.push(self)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if (value := container[self.name]) not in self._array:
            raise WhitelistError(
                f"Cannot build value {value} as it's not listed "
                f"as a whitelisted value {self._array}"
            )
        super().io_build(parent, codecs, container)
