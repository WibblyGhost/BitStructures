from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bitstring import Bits, ConstBitStream

if TYPE_CHECKING:
    from bitstructures.base.codec import Codec, Container, EnumBase, StackV, _Error, _Pass

type DefaultType = _Pass | _Error
type DefaultTypeExt = DefaultType | Codec
type FunctType = Callable[[StackV], int]
type FunctSwitchType = Callable[[StackV | Container], Any]
type ExpType = Callable[[int], int]
type IoType = Bits | ConstBitStream | None
# Can only take in ints, enumeration objects and raw bit streams
type WriteIoType = int | EnumBase | ConstBitStream
type ReadIoType = ConstBitStream | Bits
