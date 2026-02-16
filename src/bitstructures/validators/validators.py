from collections.abc import Iterable
from typing import override

from bitstructures.base.bitstream import BitStream
from bitstructures.base.codec import BitsInt, StackC
from bitstructures.base.objects import Container
from bitstructures.exceptions import BlacklistError, WhitelistError, add_codec_to_traceback


class Blacklisted(BitsInt):
    """
    Prevents parsing/building a certain range of values, failing to do so
    will raise a BlacklistedError.

    >>> "digit" = Blacklisted(8, [0])
    """

    @override
    def __init__(self, size: int, array: Iterable[int]) -> None:
        super().__init__(size)
        self._array = array

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        stream = self._read_io(io, context, codecs)
        value = int(stream)
        if value in self._array:
            raise BlacklistError(
                io,
                context,
                codecs,
                f"Cannot parse value {value} as it's listed "
                f"in the blacklisted values {self._array}",
            )
        context[self.name] = value

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if (value := context[self.name]) in self._array:
            raise BlacklistError(
                io,
                context,
                codecs,
                f"Cannot build value {value} as it's listed "
                f"in the blacklisted values {self._array}",
            )
        super().io_build(io, context, codecs)


class Whitelisted(BitsInt):
    """
    Only allows parsing/building a certain range of values, failing to do so
    will raise a WhitelistedError.

    >>> "digit" = Whitelisted(8, list(range(34)))
    """

    @override
    def __init__(self, size: int, array: Iterable[int]) -> None:
        super().__init__(size)
        self._array = array

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        stream = self._read_io(io, context, codecs)
        value = int(stream)
        if value not in self._array:
            raise WhitelistError(
                io,
                context,
                codecs,
                f"Cannot parse value {value} as it's not "
                f"listed as a whitelisted value {self._array}",
            )
        context[self.name] = value

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if (value := context[self.name]) not in self._array:
            raise WhitelistError(
                io,
                context,
                codecs,
                f"Cannot build value {value} as it's not listed "
                f"as a whitelisted value {self._array}",
            )
        super().io_build(io, context, codecs)
