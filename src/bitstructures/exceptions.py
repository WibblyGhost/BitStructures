from typing import TYPE_CHECKING

from bitstructures.typing import SupportsSeek

if TYPE_CHECKING:
    from bitstructures.base.codec import Codec, Container, StackV


class CodecError(Exception): ...


class ParseError(CodecError):
    def __init__(
        self,
        parent: "StackV",
        subcodec: "Codec",
        peek: SupportsSeek,
        *args: object,
        raw: bytes | None = None,
    ) -> None:
        self.io = peek
        super().__init__(*args)
        self.add_note(f"Parent Stack:\n{parent.pprint()}")
        self.add_note(f"Subcodec:\n{subcodec.pprint()}")
        self.add_note(f"Peek(pos={peek.pos}, len={len(peek)}): 0b{peek.bin}")
        if raw is not None:
            self.add_note(f"Raw: {raw!r}")


class BuildError(CodecError):
    def __init__(
        self, parent: "StackV", codec: "Codec", container: "Container", *args: object
    ) -> None:
        super().__init__(*args)
        self.add_note(f"Parent Stack:\n{parent.pprint()}")
        self.add_note(f"Subcodec:\n{codec.pprint()}")
        self.add_note(f"Container: {container!r}")


class InitError(CodecError): ...


class SizeError(CodecError): ...


class StackError(CodecError): ...


class IoError(CodecError): ...


class ChecksumError(CodecError): ...


class BlacklistError(CodecError): ...


class WhitelistError(CodecError): ...


class TriggeredError(CodecError): ...


class ConstantError(CodecError): ...


class FrozenError(CodecError): ...
