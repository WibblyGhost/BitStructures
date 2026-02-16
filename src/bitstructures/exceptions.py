from typing import TYPE_CHECKING, Any

from bitstructures.typing import SupportsPPrint, SupportsSeek

if TYPE_CHECKING:
    from bitstructures.base.bitstream import BitStream
    from bitstructures.base.codec import Codec, StackC
    from bitstructures.base.objects import Container
    from bitstructures.typing import SupportsSeek


class BitstructuresError(Exception): ...


# ---- IO ERRORS ----


class ReadError(BitstructuresError): ...


class WriteError(BitstructuresError): ...


# ---- BASIC ERRORS ----


class FrozenError(BitstructuresError): ...


class SizeError(BitstructuresError): ...


class InitError(BitstructuresError): ...


# ---- CODEC ERRORS (Contain Tracebacks) ----


def add_codec_to_traceback(codec: "Codec", stack: "StackC") -> None:
    """
    Add the current codec to the stack traceback stack.
    Used before raising Codec errors to assure the current Codec gets added to the traceback.
    """
    stack.push(codec)


class CodecError(BitstructuresError):
    def __init__(
        self, io: SupportsSeek, context: "Container", codecs: "StackC", *args: object
    ) -> None:
        super().__init__(*args)
        self.parent = context
        self.codecs = codecs
        self.add_note(f"Peek(len={len(io)}): {io.bin}")
        self.add_note(f"Packet Stack:\n{context!s}")
        self.add_note(f"Codec Stack:\n{codecs.pprint()}")


class SizeOfError(CodecError):
    def __init__(
        self, io: "BitStream", context: "Container", codecs: "StackC", *args: object
    ) -> None:
        super().__init__(io, context, codecs, *args)


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
        io: SupportsSeek,
        context: "Container",
        codecs: "StackC",
        *args: object,
        raw: Any = None,
    ) -> None:
        super().__init__(io, context, codecs, *args)
        if raw is not None:
            self.add_note(f"Raw: {raw!r}")


class BuildError(CodecError): ...


class TriggeredError(CodecError):
    def __init__(
        self,
        msg: str,
        io: "SupportsSeek",
        context: "Container",
        codecs: "StackC",
        *args: object,
        **kwargs: Any,
    ) -> None:
        super().__init__(io, context, codecs, msg, *args)
        for key, value in kwargs.items():
            key_ = key.replace("_", " ").capitalize()
            if isinstance(value, SupportsPPrint):
                self.add_note(f"{key_}:\n{value.pprint()}")
            else:
                self.add_note(f"{key_}: {value}")
