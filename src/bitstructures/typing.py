from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bitstructures.base.codec import Container, Error, Pass

type DefaultType = "Pass | Error"
type ParseReturn = "Container | Pass | Error"
