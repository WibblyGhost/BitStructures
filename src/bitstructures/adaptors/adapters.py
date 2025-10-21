from collections.abc import Callable
from ipaddress import IPv4Address
from types import LambdaType
from typing import Any

from bitstring import BitStream, ConstBitStream

from bitstructures.base.codec import BitsInt, Codec, Container
from bitstructures.exceptions import CTypeError, InitError
from bitstructures.helpers import bitshift
from bitstructures.typing import ParseReturn

# ---------------- Base Adapter ----------------


class Adapter(Codec):
    def __init__(self, subcodec: Codec) -> None:
        super().__init__(subcodec)

    def io_parse(self, io: ConstBitStream, parent: Container) -> Container:
        _name, value = self.subcodec.io_parse(io, parent).popitem()
        return Container({self.name: self.decode(value, parent)})

    def io_build(self, io: BitStream, parent: Container) -> None:
        encoded = self.encode(parent[self.name])
        parent[self.name] = encoded
        return self.subcodec.io_build(io, parent)

    # ---- OVERRIDE ----

    def decode(self, value: Any, parent: Container) -> Any:
        """Override these method in the subclasses"""
        raise NotImplementedError("Must be derived in a subclass")

    def encode(self, value: Any) -> Any:
        """Override these method in the subclasses"""
        raise NotImplementedError("Must be derived in a subclass")


# ---------------- Adapters ----------------


class IpAddress(Adapter):
    def decode(self, value: int, parent: Container) -> str:  # noqa: ARG002
        return str(IPv4Address(value))

    def encode(self, value: str) -> int:
        return int(IPv4Address(value))


class Scaler(Adapter):
    def __init__(self, subcodec: Codec, /, factor: float) -> None:
        if not isinstance(subcodec, BitsInt):
            raise CTypeError(
                f"{self.__class__.__name__} adapter only support integer {Codec.__name__}'s, "
                f"got {type(subcodec)}"
            )
        super().__init__(subcodec)
        self._factor = factor

    def decode(self, value: float, parent: Container) -> float:  # noqa: ARG002
        return value * self._factor

    def encode(self, value: float) -> float:
        return int(value / self._factor)


class ExprAdapter(Adapter):
    def __init__(self, subcodec: Codec, encoder: LambdaType, decoder: LambdaType) -> None:
        super().__init__(subcodec)
        if not callable(encoder):
            raise InitError(
                "Encoder must be a callable function: def x(value: float, parent: Container)"
            )
        if not callable(decoder):
            raise InitError("Decoder must be a callable function: def x(value: float)")
        self._encode = encoder
        self._decode = decoder

    def decode(self, value: float, parent: Container) -> float:
        return self._encode(value, parent)

    def encode(self, value: float) -> float:
        return self._decode(value)


# ---------------- Computed ----------------


class Computed(Codec):
    def __init__(
        self, function: Callable[[Container], Container], *args: Any, **kwargs: Any
    ) -> None:
        self._size = 0
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        container = super().io_parse(io, parent)
        return self.function(container, *self.args, **self.kwargs)

    def io_build(self, io: BitStream, parent: Container) -> None:  # noqa: ARG002
        return


class Bitshift(Codec):
    """
    Codec which deals with splitting addresses into multiple
    bit fields, done by checking the size of the packet and
    applying a bitshift to combine the two packets
    """

    def __init__(
        self,
        funct: Callable[[Container, Any], int] = bitshift,
        *args,
        **kwargs,
    ) -> None:
        self._size = 0
        super().__init__()
        self._funct = funct
        self._args = args
        self._kwargs = kwargs

    def io_build(self, io: BitStream, parent: Container) -> None:
        """The bitshift doesn't get built through this Codes and must be done beforehand"""

    def io_parse(self, io: ConstBitStream, parent: Container) -> Container:  # noqa: ARG002
        bitshifted = self._funct(parent, *self._args, **self._kwargs)
        parent[self.name] = bitshifted
        return parent
