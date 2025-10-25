from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bitstructures.base.codec import StackV, _Error, _Pass

type DefaultType = "_Pass | _Error"
type FunctType = "Callable[[StackV], int]"
type ExpType = Callable[[Any], Any]
