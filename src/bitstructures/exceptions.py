from typing import TYPE_CHECKING, Any

from bitstructures.typing import SupportsPPrint, SupportsSeek

if TYPE_CHECKING:
    from bitstructures.base.codec import Container, StackC, StackV


class CodecError(Exception): ...


class ParseError(CodecError):
    def __init__(
        self,
        parent: "StackV",
        codecs: "StackC",
        peek: SupportsSeek,
        *args: object,
        raw: bytes | None = None,
    ) -> None:
        self.io = peek
        super().__init__(*args)
        self.add_note(f"Packet Stack:\n{parent.pprint()}")
        self.add_note(f"Codec Stack:\n{codecs.pprint()}")
        self.add_note(f"Peek(pos={peek.pos}, len={len(peek)}): 0b{peek.bin}")
        if raw is not None:
            self.add_note(f"Raw: {raw!r}")


class BuildError(CodecError):
    def __init__(
        self, parent: "StackV", codecs: "StackC", container: "Container", *args: object
    ) -> None:
        super().__init__(*args)
        self.add_note(f"Packet Stack:\n{parent.pprint()}")
        self.add_note(f"Codec Stack:\n{codecs.pprint()}")
        self.add_note(f"Container:\n{container.pprint()}")


class InitError(CodecError): ...


class SizeError(CodecError): ...


class StackError(CodecError): ...


class IoError(CodecError): ...


class ChecksumError(CodecError): ...


class BlacklistError(CodecError): ...


class WhitelistError(CodecError): ...


class TriggeredError(CodecError):
    def __init__(
        self, msg: str, parent: "StackV", codecs: "StackC", *args: object, **kwargs: Any
    ) -> None:
        super().__init__(msg, *args)
        self.add_note(f"Packet Stack:\n{parent.pprint()}")
        self.add_note(f"Codec Stack:\n{codecs.pprint()}")
        for key, value in kwargs.items():
            key_ = key.replace("_", " ").capitalize()
            if isinstance(value, SupportsPPrint):
                self.add_note(f"{key_}:\n{value.pprint()}")
            else:
                self.add_note(f"{key_}: {value}")


class ConstantError(CodecError): ...


class FrozenError(CodecError): ...
