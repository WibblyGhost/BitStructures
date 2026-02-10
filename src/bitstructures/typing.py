from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol, Self, runtime_checkable

from bitstring import ConstBitStream

if TYPE_CHECKING:
    from bitstructures.base.codec import (
        Codec,
        Container,
        EnumBase,
        Stack,
        StackC,
        StackV,
        Value,
        _Error,
        _Pass,
    )


# ---- TYPING ----

type _Value = Any | EnumBase | ConstBitStream | StackV | Value
type ValueType = _Value | Sequence[ValueType]
type ContainerType = StackV | Container
type DefaultType = _Pass | _Error
type FunctType[T] = Callable[[ContainerType], T]
type ExpType = Callable[[int], int]
type IoType = ConstBitStream | None
# Can only take in ints, enumeration objects and raw bit streams
type WriteIoType = int | EnumBase | ConstBitStream
type ReadIoType = ConstBitStream


# ---- PROTOCOLS ----


class SupportsSeek(Protocol):
    """Shadows the ConstBitStream type classes."""

    @property
    def pos(self) -> int: ...
    def __len__(self) -> int: ...
    @property
    def bin(self) -> str: ...


class SupportsName(Protocol):
    @property
    def name(self) -> str: ...


@runtime_checkable
class SupportsPPrint(Protocol):
    def pprint(self) -> str: ...


class CodecProtocol(SupportsName, Protocol):
    def __init__(self, subcodec: "Codec | None" = None) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def size(self) -> int | FunctType[int]: ...
    def __repr__(self) -> str: ...
    def __hash__(self) -> int: ...
    def __rtruediv__(self, other: Any) -> Self: ...
    def _check_initialized(self) -> None: ...
    def _parse_io(self, raw: bytes | ConstBitStream) -> ConstBitStream: ...
    def _read_io(
        self, parent: "StackV", codecs: "StackC", io: ReadIoType
    ) -> tuple[ConstBitStream, int]: ...
    def _write_io(
        self,
        parent: "StackV",
        codecs: "StackC",
        container: "Container",
        name: str,
        value: WriteIoType,
    ) -> None: ...
    def sizeof(self, parent: "StackV | Container", codecs: "StackC", io: IoType = None) -> int: ...
    def io_parse(self, parent: "StackV", codecs: "StackC", io: ConstBitStream) -> None: ...
    def io_build(self, parent: "StackV", codecs: "StackC", container: "Container") -> None: ...


class StructProtocol(CodecProtocol, Protocol):
    @property
    def subcodecs(self) -> "Stack[Codec]": ...
    def build(self, container: "Container") -> ConstBitStream: ...
    def parse(self, raw: ConstBitStream, *, readall: bool = True) -> "StackV": ...


class AdapterProtocol(Protocol):
    def __init__(self, subcodec: "Codec") -> None: ...
    def io_parse(self, parent: "StackV", codecs: "StackC", io: ConstBitStream) -> None: ...
    def io_build(self, parent: "StackV", codecs: "StackC", container: "Container") -> None: ...
    def decode(self, parent: "StackV", codecs: "StackC", value: Any) -> Any: ...
    def encode(self, parent: "StackV", codecs: "StackC", value: Any) -> Any: ...
