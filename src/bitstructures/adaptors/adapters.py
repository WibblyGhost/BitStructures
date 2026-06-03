from ipaddress import IPv4Address
from typing import Any, override

from bitstructures.base.bitstream import BitStream
from bitstructures.base.codec import Bits, Codec, StackC
from bitstructures.base.objects import Container
from bitstructures.exceptions import CodecError, DecodeError, EncodeError, add_codec_to_traceback
from bitstructures.typing import AdapterProtocol, ExpType

# ---------------- Base Adapter ----------------


class Adapter(Codec, AdapterProtocol):
    """
    Used for creating basic encoding/decoding functions that work on the
    stream during the parsing/building process. This allows us to perform
    small tweaks and value manipulation.

    This class isn't used directly and is subclassed to create custom functions.
    The following two functions must be defined in the subclass:

    def decode(self, parent: "Container", codecs: "StackC", value: Any) -> Any: ...
    def encode(self, parent: "Container", codecs: "StackC", value: Any) -> Any: ...
    """

    @override
    def __init__(self, subcodec: Codec) -> None:
        super().__init__(subcodec)

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        self.subcodec.io_parse(io, context, codecs)
        c_value = context[self.subcodec.name]
        try:
            decoded = self.decode(context, c_value)
        except CodecError:
            raise  # These errors already have our traceback
        except Exception as err:
            raise DecodeError(io, context, codecs) from err
        context.set(self.subcodec.name, decoded)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        c_value = context[self.name]
        try:
            encoded = self.encode(context, c_value)
        except CodecError:
            raise  # These errors already have our traceback
        except Exception as err:
            raise EncodeError(io, context, codecs) from err
        context.set(self.name, encoded)
        self.subcodec.io_build(io, context, codecs)


# ---------------- Adapters ----------------


class IpAddress(Adapter, AdapterProtocol):
    """
    Converts an integer into an IP Address and vice versa, this is usually a 32 bit field.

    >>> "source_ip" / IpAddress(Bits(32))
    """

    @override
    def decode(self, context: Container, value: int) -> str:
        return str(IPv4Address(value))

    @override
    def encode(self, context: Container, value: str) -> int:
        return int(IPv4Address(value))


class Scaler(Adapter, AdapterProtocol):
    """
    Simple adapter which multiplies the encoded/decoded value by an integer factor.

    >>> "timer" / Scaler(Bits(16), factor=0.1)
    """

    @override
    def __init__(self, subcodec: Codec, /, factor: float) -> None:
        if not isinstance(subcodec, Bits):
            raise TypeError(
                f"{self.__class__.__name__} adapter only support integer {Codec.__name__}'s, "
                f"got {type(subcodec)}"
            )
        super().__init__(subcodec)
        self._factor = factor

    @override
    def decode(self, context: Container, value: float) -> float:
        return value * self._factor

    @override
    def encode(self, context: Container, value: float) -> float:
        return int(value / self._factor)


class ExprAdapter(Adapter, AdapterProtocol):
    """
    Simple adapter that takes lambda's as the encoders and decoders.

    >>> "header_length" / ExprAdapter(
        Bits(4),
        encoder=lambda value: ceil(value / 4),
        decoder=lambda value: value * 4,
    )
    """

    @override
    def __init__(self, subcodec: Codec, encoder: ExpType, decoder: ExpType) -> None:
        super().__init__(subcodec)
        self._encode = encoder
        self._decode = decoder

    @override
    def decode(self, context: Container, value: Any) -> Any:
        return self._decode(value)

    @override
    def encode(self, context: Container, value: Any) -> Any:
        return self._encode(value)
