from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from bitstring import Bits, ConstBitStream

if TYPE_CHECKING:
    from bitstructures.base.codec import Container, EnumBase, StackV, _Error, _Pass

type ContainerType = Any  # str | int | float | ConstBitStream | EnumBase | Container
type DefaultType = _Pass | _Error
type FunctType[T] = Callable[[StackV | Container], T]
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
