from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bitstructures.base.codec import Codec, Container, _Error, _Pass

type ErrorType = "_Error"
type PassType = "_Pass"
type CodecType = "Codec"
type DefaultType = "PassType | ErrorType | CodecType"
type ParseReturn = "Container | PassType | ErrorType"
type LambdaType = Callable[[Container], Any]
