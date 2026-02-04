from collections.abc import Callable
from ipaddress import IPv4Address
from typing import Any, override

from bitstring import ConstBitStream

from bitstructures.base.codec import BitsInt, Codec, Container, StackC, StackV, Value
from bitstructures.helpers import bitshift
from bitstructures.typing import AdapterProtocol, ExpType, FunctType, ValueType

# ---------------- Base Adapter ----------------


class Adapter(Codec, AdapterProtocol):
    @override
    def __init__(self, subcodec: Codec) -> None:
        super().__init__(subcodec)

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        self.subcodec.io_parse(parent, codecs, io)
        sn, value = parent.get(self.subcodec.name)
        parent.set(sn, Value(value.name, self.decode(parent, codecs, value.v_item), value.size))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        c_value = container[self.name]
        encoded = self.encode(parent, codecs, c_value)
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
        return self._encode(value)

    @override
    def encode(self, parent: StackV, codecs: StackC, value: Any) -> Any:
        return self._decode(value)


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
        # NOTE: The computed class doesn't consume the bitstream
        computed = self.function(parent)
        parent.push(Value(self.name, computed, 0))
        codecs.push(self)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container[Any]) -> None:
        return


# @override
# def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
#     container = super().io_parse(parent, io)
#     return self.function(container, *self.args, **self.kwargs)

# @override
# def io_build(self, parent: StackV, container: Container) -> None:
#     return


class Bitshift(Codec):
    """
    Codec which deals with splitting addresses into multiple
    bit fields, done by checking the size of the packet and
    applying a bitshift to combine the two packets
    """

    @override
    def __init__(
        self,
        funct: Callable[[Container[int], str, bool], int] = bitshift,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._funct = funct
        self._args = args
        self._kwargs = kwargs


# @override
# def io_build(self, parent: StackV, container: Container) -> None:
#     """The bitshift doesn't get built through this Codes and must be done beforehand"""

# @override
# def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
#     bitshifted = self._funct(parent, *self._args, **self._kwargs)
#     parent.set(self.name, bitshifted, ignore_frozen=True)
#     return parent
