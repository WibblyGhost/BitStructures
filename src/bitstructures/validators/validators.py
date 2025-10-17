from collections.abc import Iterable

from bitstring import BitStream

from bitstructures.base.codec import Codec, Container
from bitstructures.exceptions import CodecError


class Blacklisted(Codec):
    def __init__(self, subcodec: Codec, array: Iterable[int]) -> None:
        super().__init__(subcodec)
        self._array = array

    def io_build(self, io: BitStream, container: Container) -> None:
        if (value := container[self.name]) in self._array:
            raise CodecError(
                f"Cannot build value {value} as it's within the blacklisted values {self._array}"
            )
        self._subcodec.io_build(io, container)


class Whitelisted(Codec):
    def __init__(self, subcodec: Codec, array: Iterable[int]) -> None:
        super().__init__(subcodec)
        self._array = array

    def io_build(self, io: BitStream, container: Container) -> None:
        if (value := container[self.name]) in self._array:
            raise CodecError(
                f"Cannot build value {value} as "
                f"it's not within the whitelisted values {self._array}"
            )
        self._subcodec.io_build(io, container)
