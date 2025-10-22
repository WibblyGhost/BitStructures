from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bitstructures.base.codec import Stack, _Error, _Pass

type DefaultType = "_Pass | _Error"
type FunctType = "Callable[[Stack], int]"
