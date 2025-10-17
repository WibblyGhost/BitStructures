from typing import TYPE_CHECKING

from bitstring import ConstBitStream

if TYPE_CHECKING:
    from bitstructures.base.codec import Codec, Container


class CodecError(Exception): ...


class CTypeError(CodecError): ...


class InitError(CodecError): ...


class SizeError(CodecError): ...


class ParseError(CodecError):
    def __init__(
        self, parent: "Container", subcodec: "Codec", peek: ConstBitStream, *args: object
    ) -> None:
        self.io = peek
        super().__init__(*args)
        self.add_note(f"Parent Container: {parent}")
        self.add_note(f"Subcodec: {subcodec}")
        self.add_note(f"Peek: 0b{peek.bin}")


class BuildError(CodecError):
    def __init__(self, subcodec: "Codec", *args: object) -> None:
        super().__init__(*args)
        self.add_note(f"Subcodec: {subcodec}")


class LengthError(CodecError): ...


class TriggeredError(CodecError): ...


class ConstantError(CodecError): ...


class RDivError(CodecError): ...
