from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bitstring import Bits, ConstBitStream

if TYPE_CHECKING:
    from bitstructures.base.codec import Container, EnumBase, StackV, _Error, _Pass

type _ContainerType = Any  # str | int | float | ConstBitStream | EnumBase | Container
type ContainerType = StackV | Container
type DefaultType = _Pass | _Error
type FunctType[T] = Callable[[ContainerType], T]
type ExpType = Callable[[int], int]
type IoType = Bits | ConstBitStream | None
# Can only take in ints, enumeration objects and raw bit streams
type WriteIoType = int | EnumBase | ConstBitStream
type ReadIoType = ConstBitStream | Bits


class SupportsSeek(Protocol):
    """Shadows the ConstBitStream type classes"""

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
