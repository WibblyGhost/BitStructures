from typing import TYPE_CHECKING, Any

from bitstring import ConstBitStream

from bitstructures.typing import SupportsPPrint, SupportsSeek

if TYPE_CHECKING:
    from bitstructures.base.codec import Codec, Container, StackC, StackV


class BitstructuresError(Exception): ...


# ---- BASIC ERRORS ----


class FrozenError(BitstructuresError): ...


class SizeError(BitstructuresError): ...


class InitError(BitstructuresError): ...


# ---- CODEC ERRORS (Contain Tracebacks) ----


def add_codec_to_traceback(codec: "Codec", stack: "StackC") -> None:
    """
    Adds the current codec to the stack traceback stack.
    Used before raising Codec errors to assure
    the current Codec gets added to the traceback.
    """
    stack.push(codec)


class CodecError(BitstructuresError):
    def __init__(self, parent: "StackV", codecs: "StackC", *args: object) -> None:
        super().__init__(*args)
        self.parent = parent
        self.codecs = codecs
        self.add_note(f"Packet Stack:\n{parent.pprint()}")
        self.add_note(f"Codec Stack:\n{codecs.pprint()}")


class SizeOfError(CodecError):
    def __init__(self, parent: "StackV | Container", codecs: "StackC", *args: object) -> None:
        super().__init__(parent, codecs, *args)  # type: ignore[arg-type]


class StackError(CodecError): ...


class BitsIoError(CodecError): ...


class ChecksumError(CodecError): ...


class BlacklistError(CodecError): ...


class WhitelistError(CodecError): ...


class ConstantError(CodecError): ...


class EncodeError(CodecError): ...


class DecodeError(CodecError): ...


class ParseError(CodecError):
    def __init__(
        self,
        parent: "StackV",
        codecs: "StackC",
        peek: SupportsSeek,
        *args: object,
        raw: ConstBitStream | None = None,
    ) -> None:
        self.io = peek
        super().__init__(parent, codecs, *args)
        self.add_note(f"Peek(pos={peek.pos}, len={len(peek)}): 0b{peek.bin}")
        if raw is not None:
            self.add_note(f"Raw: {raw!r}")


class BuildError(CodecError):
    def __init__(
        self, parent: "StackV", codecs: "StackC", container: "Container", *args: object
    ) -> None:
        super().__init__(parent, codecs, *args)
        self.add_note(f"Container:\n{container.pprint()}")


class TriggeredError(CodecError):
    def __init__(
        self, msg: str, parent: "StackV", codecs: "StackC", *args: object, **kwargs: Any
    ) -> None:
        super().__init__(parent, codecs, msg, *args)
        for key, value in kwargs.items():
            key_ = key.replace("_", " ").capitalize()
            if isinstance(value, SupportsPPrint):
                self.add_note(f"{key_}:\n{value.pprint()}")
            else:
                self.add_note(f"{key_}: {value}")
