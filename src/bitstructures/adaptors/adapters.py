from collections.abc import Callable
from ipaddress import IPv4Address
from typing import Any, override

from bitstring import ConstBitStream

from bitstructures.base.codec import BitsInt, Codec, Container, StackC, StackV, Value
from bitstructures.exceptions import (
    CodecError,
    DecodeError,
    EncodeError,
    ParseError,
    add_codec_to_traceback,
)
from bitstructures.helpers import bitshift
from bitstructures.typing import AdapterProtocol, ExpType, FunctType, ValueType

# ---------------- Base Adapter ----------------


class Adapter(Codec, AdapterProtocol):
    @override
    def __init__(self, subcodec: Codec) -> None:
        super().__init__(subcodec)

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        self.subcodec.io_parse(parent, codecs, io)
        sn, value = parent.get(self.subcodec.name)
        try:
            decoded = self.decode(parent, codecs, value.v_item)
        except CodecError:
            raise  # These errors already have our traceback
        except Exception as err:
            raise DecodeError(parent, codecs) from err
        parent.set(sn, Value(value.name, decoded, value.size))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        c_value = container[self.name]
        try:
            encoded = self.encode(parent, codecs, c_value)
        except CodecError:
            raise  # These errors already have our traceback
        except Exception as err:
            raise EncodeError(parent, codecs) from err
        container.set(self.name, encoded, ignore_frozen=True)
        self.subcodec.io_build(parent, codecs, container)


# ---------------- Adapters ----------------


class IpAddress(Adapter):
    @override
    def decode(self, parent: StackV, codecs: StackC, value: int) -> str:
        return str(IPv4Address(value))

    @override
    def encode(self, parent: StackV, codecs: StackC, value: str) -> int:
        return int(IPv4Address(value))


class Scaler(Adapter):
    @override
    def __init__(self, subcodec: Codec, /, factor: float) -> None:
        if not isinstance(subcodec, BitsInt):
            raise TypeError(
                f"{self.__class__.__name__} adapter only support integer {Codec.__name__}'s, "
                f"got {type(subcodec)}"
            )
        super().__init__(subcodec)
        self._factor = factor

    @override
    def decode(self, parent: StackV, codecs: StackC, value: float) -> float:
        return value * self._factor

    @override
    def encode(self, parent: StackV, codecs: StackC, value: float) -> float:
        return int(value / self._factor)


class ExprAdapter(Adapter):
    @override
    def __init__(self, subcodec: Codec, encoder: ExpType, decoder: ExpType) -> None:
        super().__init__(subcodec)
        self._encode = encoder
        self._decode = decoder

    @override
    def decode(self, parent: StackV, codecs: StackC, value: Any) -> Any:
        return self._decode(value)

    @override
    def encode(self, parent: StackV, codecs: StackC, value: Any) -> Any:
        return self._encode(value)


# ---------------- Computed ----------------


class Computed[T: ValueType](Codec):
    @override
    def __init__(self, function: FunctType[T], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        # NOTE: The Computed class doesn't consume the bitstream
        computed = self.function(parent)
        parent.push(Value(self.name, computed, 0))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container[Any]) -> None:
        # NOTE: Same as the Pass() class
        add_codec_to_traceback(self, codecs)

        parent.push(Value(self.name, ConstBitStream(), 0))


class Bitshift(Codec):
    """
    Codec which deals with splitting addresses into multiple
    bit fields, done by checking the size of the packet and
    applying a bitshift to combine the two packets
    """

    @override
    def __init__(
        self,
        field_name: str,
        funct: Callable[[StackV, str, bool], int] = bitshift,
        msb: bool = True,
    ) -> None:
        super().__init__()
        self._field_name = field_name
        self._msb = msb
        self._funct = funct

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        # NOTE: The Bitshift class doesn't consume the bitstream
        if getattr(parent, f"{self._field_name}_p1", None):
            value = self._funct(parent, self._field_name, self._msb)
        elif getattr(
            parent._, f"{self._field_name}_p1", None
        ):  # Check the parent also as a failsafe
            value = self._funct(parent._, self._field_name, self._msb)
        else:
            raise KeyError(
                f"Field {self._field_name!r} not found in the parent stack"
            ) from ParseError(parent, codecs, io)
        parent.push(Value(self.name, value, 0))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container[Any]) -> None:
        """The bitshift doesn't get built through this Codes and must be done beforehand"""
        # NOTE: Same as the Pass() class
        add_codec_to_traceback(self, codecs)

        parent.push(Value(self.name, ConstBitStream(), 0))
