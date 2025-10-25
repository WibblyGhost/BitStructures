from typing import TYPE_CHECKING

from bitstring import ConstBitStream

if TYPE_CHECKING:
    from bitstructures.base.codec import Codec, Container, StackV


class CodecError(Exception): ...


class CTypeError(CodecError): ...


class InitError(CodecError): ...


class SizeError(CodecError): ...


class ParseError(CodecError):
    def __init__(
        self, parent: "StackV", subcodec: "Codec", peek: ConstBitStream, *args: object
    ) -> None:
        self.io = peek
        super().__init__(*args)
        self.add_note(f"Parent Stack:\n{parent.pprint()}")
        self.add_note(f"Subcodec: {subcodec}")
        self.add_note(f"Peek(pos={peek.pos}, len={len(peek)}): 0b{peek.bin}")


class BuildError(CodecError):
    def __init__(
        self, parent: "StackV", subcodec: "Codec", container: "Container", *args: object
    ) -> None:
        super().__init__(*args)
        self.add_note(f"Parent Stack:\n{parent.pprint()}")
        self.add_note(f"Subcodec: {subcodec}")
        self.add_note(f"Container: {container}")


class LengthError(CodecError): ...


class TriggeredError(CodecError): ...


class ConstantError(CodecError): ...


class RDivError(CodecError): ...


class FrozenError(CodecError): ...
