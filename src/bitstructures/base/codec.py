from collections.abc import Buffer, Callable, Collection, Iterable
from contextlib import suppress
from copy import deepcopy
from typing import Any, ClassVar, NoReturn, Protocol, Self, override

from bitstructures.base.bitstream import BitStream
from bitstructures.base.objects import Container, EnumBase, Stack
from bitstructures.constants import PP_DETENT, PP_INDENT, PP_TAB
from bitstructures.exceptions import (
    BitsIoError,
    BuildError,
    CodecError,
    ConstantError,
    InitError,
    ParseError,
    ReadError,
    SizeError,
    SizeOfError,
    StackError,
    TriggeredError,
    WriteError,
    add_codec_to_traceback,
)
from bitstructures.typing import (
    CodecProtocol,
    DefaultType,
    FunctType,
    StructProtocol,
    ValueType,
    WriteIoType,
)

# ---------------- Wrappers ----------------
__protocol_type = type(Protocol)


class SingletonMeta(__protocol_type):  # type: ignore[misc, valid-type]
    """
    Defines a class that only ever needs to be initialised once,
    and is used globally without new classes being created.

    # METACLASS
    - *This class must be the used as a metaclass when subclassing*
    - Not Thread Safe
    """

    _instances: ClassVar[dict["SingletonMeta", type]] = {}

    def __call__(self, *args: Any, **kwargs: Any) -> type:
        if self not in self._instances:
            self._instances[self] = super().__call__(*args, **kwargs)
        return self._instances[self]


# ---------------- Base Class ----------------


class StackC(Stack["Codec | StackC"]):
    """Version of the stack which contains methods for holding Codec's."""

    __slots__ = ("name",)

    def __init__(self) -> None:
        super().__init__()
        self.name = "StackC"  # Needed for MyPy

    @override
    def _validate_item(self, item: "Codec | StackC") -> None:
        return

    def pprint(self, *, depth: int = 1) -> str:
        # RECURSIVE
        padding = "\t{t}{v:-^38}{t}\n"
        stack = ""
        for item in self:
            if isinstance(item, StackC):
                stack += padding.format(t=PP_INDENT * depth, v=f"{StackC.__name__}")
                stack += item.pprint(depth=depth + 1)
                stack += padding.format(t=PP_DETENT, v="")
            else:
                stack += f"\t{PP_TAB * (depth - 1)} {item!s}\n"
        return stack


class Codec(CodecProtocol):
    """
    Base class for codecs and is ideally subclassed for ALL codecs, contains
    all the logic needed for representing sizes, hashes, strings, naming, parsing and building.

    Most codecs need to initialised with strings as a description, except for
    any Struct's or special types.

    The size of the Codec can be a concrete integer type, or calculated during
    parsing/building via a lambda.

    *Count*
    >>>  "codewords" / Codec(4)

    *Functional*
    >>>  "codewords" / Codec(lambda packet: packet.codeword_size)
    """

    def __init__(self, subcodec: "Codec | None" = None) -> None:
        """
        self._subcodec:     Codec to use when building, parsing or getting sizeof
        self.name:          Name of this codec, can use "name" / Codec to name this codec
        self.size:         Size in bits of this codec
        """  # noqa: D400, D415
        self._subcodec: Codec | None = deepcopy(subcodec)
        self._initialized: bool = False
        self._name: str = ""
        self._size: int | FunctType[int] = subcodec._size if subcodec else -1  # noqa: SLF001

    @property
    def name(self) -> str:
        return self._name

    @property
    def size(self) -> int:
        """
        Attempts to calculate the size of this Codec
        NOTE: This will not always work, or be accurate, please double check the
              output size is what you expect.
        """
        if callable(self._size):
            raise SizeError(
                f"Cannot calculate size of {self!r}, "
                f"size argument is a callable. Please use '.sizeof()'."
            )
        if isinstance(self.subcodec, Struct):
            return self.subcodec.size
        if self._size <= 0:
            raise SizeError(f"Cannot calculate size of {self!r}, codec has a zero/negative size")
        return self._size

    @property
    def subcodec(self) -> "Codec":
        return self._subcodec or self

    def _check_initialized(self) -> None:
        """
        Checks if the codec har been given a description/name
        Structs/Padding do not need names so ignore this.
        """
        if self._initialized and self.name:
            return
        raise InitError(f"{self!s} needs to be initialized with a '/'")

    def __repr__(self) -> str:
        if isinstance(self._size, int):
            return f"{self.name!r} / {self.__class__.__name__}({self._size})"
        return f"{self.name!r} / {self.__class__.__name__}"

    def __hash__(self) -> int:
        return hash(self.name)

    def __rtruediv__(self, other: Any) -> Self:
        """
        Method which defines the behaviour of right side '|' operator.
        When a string is divided, apply that string as the name/describer
        of this Codec.
        E.g.

        >>> codec = "name" / Codec
        >>> print(codec.name)
        >>>> "name"
        """
        if other is None:  # Do nothing
            return self
        if isinstance(other, str):  # Set description
            cls_ = deepcopy(self)
            cls_.rename(other)
            return cls_

        if isinstance(other, Codec):
            raise TypeError(
                f"This {Codec.__name__.lower()} {self.__class__.__name__} doesn't support "
                f"rdiv on other {Codec.__name__} structures"
            )
        raise TypeError(f"Unhandled type {type(other)} for division")

    def rename(self, name: str) -> None:
        """
        Internally renames a Codec's description and initializes the Codec.
        This doesn't deepcopy the Codec as that is done in __rdiv__.

        NOTE: Only used internally, please use __rdiv__ for any real renaming of Codec's
        """
        self._name = name
        self._initialized = True
        if hasattr(self, "_subcodec") and self._subcodec:
            # Uses private subcodec, as this can be None
            self._subcodec.rename(name)

    def sizeof(self, io: BitStream, context: Container, codecs: StackC) -> int:
        """Returns the size of the current Codec given a build container."""
        self._check_initialized()
        size: int = self._size(context) if callable(self._size) else self._size
        if size < 0:  # If size is negative
            raise SizeOfError(
                io,
                context,
                codecs,
                (
                    f"Cannot perform a size method on {self.__class__.__name__}, "
                    f"or ran into an issue when calculating the size"
                ),
            )
        return size

    def _parse_io(self, raw: bytes | BitStream) -> BitStream:
        """Converts raw bytes into a BitStream to work with."""
        self._check_initialized()
        if isinstance(raw, BitStream):
            return raw.copy()
        return BitStream(raw)

    def _read_io(self, io: BitStream, context: Container, codecs: StackC) -> BitStream:
        """
        Handles the reading of the BitStream's IO, raises a parsing error
        if it failed to read.
        """
        self._check_initialized()
        size = self.sizeof(io, context, codecs)
        try:
            return io.read(size)
        except ReadError as err:
            raise ParseError(
                io,
                context,
                codecs,
                "Ran into an error reading BitStream",
            ) from err

    def _write_io(
        self,
        io: BitStream,
        context: Container,
        codecs: StackC,
        value: WriteIoType,
        size: int,
    ) -> None:
        """
        Handles the reading of the BitStream's IO, raises a parsing error
        if it failed to read.
        """
        if not isinstance(value, int | EnumBase | BitStream):
            raise TypeError(
                f"Cannot build a value of type {type(value)}, "
                f"must be one of int | EnumBase | BitStream"
            ) from CodecError(io, context, codecs)

        if isinstance(value, EnumBase):
            value = value.value

        if size == 0:
            return

        try:
            io.write(value, size)
        except (WriteError, CodecError) as err:
            raise BuildError(
                io,
                context,
                codecs,
                Container({"value": value}),
                "Ran into an error writing BitStream",
            ) from err


# ---------------- Defaults ----------------


class _Pass(Codec, metaclass=SingletonMeta):
    """
    Declarer that this Codec *shouldn't* error when it fails to map,
    this class will encode into a null terminated bitstream and skip decoding.
    """

    __PRIVATE_NAME = "__pass"

    @override
    def __init__(self) -> None:
        self._name = self.__PRIVATE_NAME
        self._size = -1

    @override
    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    @override
    def rename(self, name: str) -> None:
        return

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)


Pass = _Pass()


class _Error(Codec, metaclass=SingletonMeta):
    """
    Declarer that this Codec *should* error when it fails to map,
    this class will raise an exception upon parsing or building upon.
    """

    __PRIVATE_NAME = "__error"

    @override
    def __init__(self) -> None:
        self._name = self.__PRIVATE_NAME
        self._size = -1

    @override
    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    @override
    def rename(self, name: str) -> None:
        return

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        self.raise_error(io, context, codecs)

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        self.raise_error(io, context, codecs)

    @classmethod
    def raise_error(
        cls, io: BitStream, context: Container, codecs: StackC, **kwargs: Any
    ) -> NoReturn:
        raise TriggeredError(
            "This error was triggered via a default set to Error",
            io,
            context,
            codecs,
            **kwargs,
        )


Error = _Error()
NotImplementedCodec = Error

# ---------------- Structures ----------------


class Struct(Codec, StructProtocol):
    """
    Parent codec which is used to group Codecs together, this class must
    handle recursive Codecs when parsing and building.

    >>> codec = Struct(
        "int1" / BitInts(4),
        "int2" / BitInts(4),
    )
    """

    __PRIVATE_NAME = "__struct"

    @property
    def subcodecs(self) -> StackC:
        return self._subcodec_stack

    @override
    @property
    def size(self) -> int:
        """
        Attempts to calculate the size of this Codec
        NOTE: This will not always work, or be accurate, please double check the
              output size is what you expect.
        """
        try:
            return sum(codec.size for codec in self.subcodecs)  # type: ignore[union-attr, misc]
        except Exception as err:
            raise err from SizeError(f"Cannot calculate size of current struct {self.name}")

    def _check_subcodec_type(self, *args: Any) -> None:
        for arg in args:
            if not issubclass(arg.__class__, Codec):
                raise InitError(
                    f"{Struct.__name__} can only work with {Codec.__name__} objects, "
                    f"got {arg.__class__.__name__}"
                )
            self._subcodec_stack.push(arg)

    @override
    def __repr__(self) -> str:
        if isinstance(self._size, int):
            return f"{self.name} / {self.__class__.__name__}({self._size}, {self.embedded=})"
        return f"{self.name} / {self.__class__.__name__}({self.embedded=})"

    @override
    def __init__(self, *args: Any, embedded: bool = False) -> None:
        self._subcodec_stack: StackC = StackC()
        super().__init__()
        self._check_subcodec_type(*args)
        self._name = self.__PRIVATE_NAME  # Default name for a struct without a describer
        self.embedded = embedded
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    def _check_initialized(self) -> None:
        """
        Checks if the codec has been given a description/name
        Structs/Padding do not need names so ignore this.
        """
        return

    def parse(self, raw: bytes | BitStream, *, readall: bool = True) -> Container:
        """
        Handles parsing an IO stream into a Container by
        passing the IO into io_parse for custom parsing.
        - Not modified in subclasses
        - Called externally via users.
        """
        if not isinstance(raw, bytes | BitStream):
            raise TypeError(
                f"Parse only accepts a argument with type "
                f"{bytes.__name__} | {BitStream.__name__}, got {type(raw)}"
            )
        context = Container()
        codecs = StackC()
        add_codec_to_traceback(self, codecs)

        io: BitStream = self._parse_io(raw)
        try:
            self.io_parse(io, context, codecs)
            if not context:
                raise StackError(io, context, codecs, "Parsed stack is empty")
            if readall and len(io) != 0:
                raise BitsIoError(
                    io,
                    context,
                    codecs,
                    f"IO hasn't reached a terminator but {readall=}",
                )
            return context
        except CodecError:
            # CodecError - These error subtypes already have all the trace
            #              information required.
            raise
        except Exception as err:
            raise ParseError(io, context, codecs, repr(err), raw=raw) from err

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name == self.__PRIVATE_NAME:
            # Force this class to be embedded if it hasn't been assigned a descriptor
            # E.g. When assigning a Struct to a variable
            self.embedded = True

        # Embedding structs
        if not self.embedded:
            nested = Container()
            nested.set_parent(context)
            codec_stack = StackC()
            codec_stack.name = self.name
        else:
            nested = context
            codec_stack = codecs

        for subcodec in self.subcodecs:
            assert isinstance(subcodec, Codec)  # For MyPy's sake
            subcodec.io_parse(io, nested, codec_stack)

        if not self.embedded:
            context[self.name] = nested
            codecs.push(codec_stack)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name == self.__PRIVATE_NAME:
            # Force this class to be embedded if it hasn't been assigned a descriptor
            # E.g. When assigning a Struct to a variable
            self.embedded = True

        # Embedding structs
        nested: Container
        if self.embedded:
            nested = context
            codec_stack = codecs
        else:
            ctx = context.copy()
            nested = ctx.pop(self.name)
            nested.set_parent(ctx)
            codec_stack = StackC()
            codec_stack.name = self.name

        for subcodec in self.subcodecs:
            assert isinstance(subcodec, Codec)  # For MyPy's sake
            subcodec.io_build(io, nested, codec_stack)

    def build(self, container: Container) -> BitStream:
        """
        Handles building a Container into a bytes object by
        passing the Container into the io_build for custom parsing.
        - Not modified in subclasses
        - Called externally via users.
        """
        if not isinstance(container, Container):
            raise TypeError(
                f"Build only accepts a argument with type {Container.__name__}, "
                f"got {type(container)}"
            )
        codecs = StackC()
        add_codec_to_traceback(self, codecs)

        io = BitStream()
        # Copy container, and unfreeze this one (needed for IO setting operations)
        context = container.copy()
        try:
            self.io_build(io, context, codecs)
            if len(io) % 8 != 0:
                raise SizeOfError(
                    io,
                    context,
                    codecs,
                    f"Built bits must be divisible by 8 (byte), {context!r} {len(context)=}",
                )
            return io
        except CodecError:
            # CodecError - These error subtypes already have all the trace
            #              information required.
            raise
        except Exception as err:
            raise BuildError(io, context, codecs, repr(err)) from err

    def sizeof(self, io: BitStream, context: Container, codecs: StackC) -> int:
        if isinstance(self.size, int) and self.size > 0:
            return self.size
        return super().sizeof(io, context, codecs)


class Pointer(Struct):
    """
    Allows you to look ahead of the current position and parse content later on.
    This is very useful if you have a field that relies on data later in the packet.

    # Move the stream ahead 8 bits then parse the id, then revert
    >>> Pointer(
        --> Pointer starts reading at 8 bits
        ("source_id" / SOURCE_ID,),  # Start Codec
        <-- Pointer resumes stream here at 16 bits -> pos at 0 bits
        ("mfid" / MANUFACTURER_ID,),  # End Codec
        NOTE: Must consume all remaining bits that were skipped
        start=8,
        end=16
    )
    """

    @override
    def __init__(
        self,
        start_codec: Iterable[Codec],
        end_codec: Iterable[Codec],
        /,
        *,
        start: int,
        end: int,
        embedded: bool = False,
    ) -> None:
        self._start = start
        self._end = end
        self._start_codec = start_codec
        self._end_codec = end_codec
        super().__init__(*start_codec, *end_codec, embedded=embedded)

    @override
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def sizeof(self, io: BitStream, context: Container, codecs: StackC) -> int:
        return self._end

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        """IO parse method doesn't consume the IO stream, instead just *peeks* at the stream."""
        add_codec_to_traceback(self, codecs)

        try:
            start = io.read(self._start)
            end = io.read(self._end - self._start)
            # Swap the order of the start and end IO, then parse normally
            swapped_io = end + start
        except ReadError as err:
            raise ParseError(
                io,
                context,
                codecs,
                "Ran into an error reading BitStream",
            ) from err
        super().io_parse(swapped_io, context, codecs)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        for codec in (*self._end_codec, *self._start_codec):
            ctx = context.copy()
            nested: Container = ctx.pop(self.name)
            nested.set_parent(ctx)
            codec.io_build(io, nested, codecs)


# ---------------- Conditional Structures ----------------


class Conditional(Codec):
    """
    Used to switch between two Codec's given a lambda expression.
    It takes a lambda type function and either one or two conditional Codec's
    to switch on.

    *If*
    >>> "payload" / Conditional(lambda packet: packet.protocol, UDP),

    *If/Else*
    >>> "payload" / Conditional(lambda packet: packet.protocol, UDP, TCP),

    *If/Else(Ignore)*
    >>> "payload" / Conditional(lambda packet: packet.protocol, UDP, Pass),

    *If/Else(Error)*
    >>> "payload" / Conditional(lambda packet: packet.protocol, UDP, Error),
    """

    @override
    def __init__(
        self,
        condition: FunctType[bool],
        then_: Codec,
        else_: Codec = Pass,
        *,
        embedded: bool = False,
    ) -> None:
        super().__init__()
        self.condition = condition
        if embedded is True:
            if isinstance(then_, Struct):
                then_.embedded = embedded
            if isinstance(else_, Struct):
                else_.embedded = embedded
        self.embedded = embedded
        # Make sure to use the __rdiv__ here not rename to
        # return a deepcopy of the Codec
        self._then = self.name / then_
        self._else = self.name / else_
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    def __repr__(self) -> str:
        if isinstance(self._size, int):
            return f"{self.name!r} / {self.__class__.__name__}({self._size}, {self.embedded=})"
        return f"{self.name!r} / {self.__class__.__name__}"

    @override
    def __rtruediv__(self, other: Any) -> Self:
        new = super().__rtruediv__(other)
        # Give the sub-codecs the same name as this divisor
        new._then = new.name / new._then
        new._else = new.name / new._else
        return new

    @override
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def sizeof(self, io: BitStream, context: Container, codecs: StackC) -> int:
        if self.condition(context):
            return self._then.sizeof(io, context, codecs)
        return self._else.sizeof(io, context, codecs)

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        condition = self.condition(context)
        if not isinstance(condition, bool):
            raise ParseError(
                io,
                context,
                codecs,
                f"Condition returned a non-bool value {condition!r}",
            )
        if condition:
            self._then.io_parse(io, context, codecs)
        elif self._else is not Pass:
            self._else.io_parse(io, context, codecs)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        condition = self.condition(context)
        if not isinstance(condition, bool):
            raise ParseError(
                io,
                context,
                codecs,
                f"Condition returned a non-bool value {condition!r}",
            )
        if condition:
            self._then.io_build(io, context, codecs)
        else:
            self._else.io_build(io, context, codecs)


class Switch[MKey: Any, MValue: Codec | Struct = Codec](Codec):
    """
    Works much like the Conditional Codec except this Codec allows mapping multiple
    Codec's to a dictionary and switches via a lambda.

    Can be toggled between erroring or ignoring upon failing to match with the Mapping.

    >>> "header" / Switch[str](
        lambda packet: packet.protocol,
        {"UDP": UDP_HEADER, "TCP": TCP_HEADER}
        default=Error|Pass
    )
    """

    @override
    def __init__(
        self,
        funct: FunctType[MKey],
        mapping: dict[MKey, MValue],
        *,
        default: DefaultType | MValue = Error,
        embedded: bool = False,
    ) -> None:
        super().__init__()
        self._funct = funct
        self._mapping = mapping
        self._default = default
        self.embedded = embedded
        for codec in self._mapping.values():
            codec.rename(self.name)
            if embedded is True and isinstance(codec, Struct):
                codec.embedded = embedded
        if embedded is True and isinstance(self._default, Struct):
            self._default.rename(self.name)
            self._default.embedded = embedded
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    def rename(self, name: str) -> None:
        super().rename(name)
        for codec in self._mapping.values():
            codec.rename(self.name)
        self._default.rename(self.name)

    @override
    def __repr__(self) -> str:
        if isinstance(self._size, int):
            return f"{self.name!r} / {self.__class__.__name__}({self._size}, {self.embedded=})"
        return f"{self.name!r} / {self.__class__.__name__}"

    @override
    def __rtruediv__(self, other: Any) -> Self:
        for key, codec in self._mapping.items():
            self._mapping[key] = other / codec
        return super().__rtruediv__(other)

    @override
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        mapping_key: MKey | None = None
        subcodec: DefaultType | MValue | None = None
        try:
            mapping_key = self._funct(context)
            subcodec = self._mapping[mapping_key]
        except (ValueError, KeyError):
            if self._default.__class__ is _Error:
                Error.raise_error(io, context, codecs, key=mapping_key, mapping=list(self._mapping))
            if self._default.__class__ is _Pass:
                return
            subcodec = self._default
        subcodec.io_parse(io, context, codecs)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        mapping_key = self._funct(context)
        if mapping_key not in self._mapping:
            if self._default.__class__ is _Pass:
                return
            if self._default.__class__ is _Error:
                Error.raise_error(
                    io,
                    context,
                    codecs,
                    key=mapping_key,
                    mapping=list(self._mapping),
                )
            self._default.io_build(io, context, codecs)
            return
        subcodec = self._mapping[mapping_key]
        subcodec.io_build(io, context, codecs)


class Optional(Codec):
    """
    Will attempt to parse/build this Codec, but upon failure, will ignore the
    errors and parse an empty value.

    >>> "options" / Optional(Bits(8))
    """

    @override
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        try:
            size = self.subcodec.sizeof(io, context, codecs)
        except (SizeOfError, SizeError):
            return

        if size <= 0:
            return
        with suppress(ParseError):
            self.subcodec.io_parse(io, context, codecs)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        try:
            size = self.subcodec.sizeof(io, context, codecs)
        except (SizeOfError, SizeError):
            return

        if size <= 0:
            return
        if self.name in context:
            self.subcodec.io_build(io, context, codecs)


# ---------------- Core Codecs ----------------


class Padding(Codec):
    """
    Used when we don't want any value to represent the allocated data,
    can be used as a *pad or fill* in a structure and will not be returned
    during building.

    >>> Padding(4, padding=0b0101)
    """

    __PRIVATE_NAME = "__padding"

    @override
    def __init__(self, size: int, /, *, pattern: int = 0b0) -> None:
        super().__init__()
        self._name = self.__PRIVATE_NAME
        self._size = size
        self._pattern = pattern

    @override
    def _check_initialized(self) -> None:
        """
        Checks if the codec har been given a description/name
        Structs/Padding do not need names so ignore this.
        """
        return

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)
        _io = self._read_io(io, context, codecs)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        size = self.sizeof(io, context, codecs)
        pattern = bin(self._pattern)
        binary = BitStream(pattern)
        while len(binary) < size:
            binary += pattern
            if len(binary) > size:
                raise SizeOfError(
                    io,
                    context,
                    codecs,
                    f"Defined pattern {binary.bin!s} ({len(binary.bin)} bits) "
                    f"couldn't be repeated within {size} bits",
                )
        self._write_io(io, context, codecs, binary, self.sizeof(io, context, codecs))


class Bits(Codec):
    """
    Defines a integer representation from the BitStream,
    will return an integer when parsing and takes any int on building.

    >>> "int1" / BitInts(8)
    """

    @override
    def __init__(self, size: int | FunctType[int]) -> None:
        super().__init__()
        self._size = size

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        stream = self._read_io(io, context, codecs)
        context[self.name] = int(stream)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name not in context:
            attr_error = AttributeError(
                f"Attempted to access {self.name!r} from the object {context!r}"
            )
            attr_error.add_note(f"Parent={context._ if hasattr(context, '_') else None}")
            raise attr_error from BuildError(io, context, codecs)

        self._write_io(io, context, codecs, context[self.name], self.sizeof(io, context, codecs))


class Enum(Bits):
    """
    Defines a Bits Codec which will encode into a Enum value, by default
    the parsing/building will fail if the value isn't in the defined enum's,
    but this can be modified to default to the integer via the `Pass`.

    >>> "protocol" / Enum(
        8,
        ICMP=1,
        TCP=6,
        UDP=17,
        default=Error|Pass
    )
    """

    @override
    def __init__(
        self,
        size: int | FunctType[int],
        *,
        default: DefaultType = Error,
        **kwargs: int | str,
    ) -> None:
        super().__init__(size)
        self._enum: EnumBase = EnumBase("enum", kwargs)  # type: ignore[call-arg]
        # Make sure to use the __rdiv__ here not rename to
        # return a deepcopy of the Codec
        self._default = self.name / default

    @property
    def enum(self) -> EnumBase:
        return self._enum

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        super().io_parse(io, context, codecs)

        value = context[self.name]
        if value in self.enum:  # type: ignore[operator]
            context[self.name] = self.enum(value)  # type: ignore[operator]
            return
        if value in self.enum._value2member_map_:  # type: ignore[attr-defined]
            context[self.name] = self.enum[value]  # type: ignore[index]
        if self._default.__class__ is _Pass:
            return
        if self._default.__class__ is _Error:
            Error.raise_error(io, context, codecs, key=value)
        raise ParseError(
            io,
            context,
            codecs,
            f"Value {value} wasn't a valid enum, {self._enum!r}",
        )

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        enum = context[self.name]
        if not isinstance(enum, EnumBase):
            # Just checking if the value is a valid enum
            if enum in self._enum:  # type: ignore[operator]
                context.set(self.name, self._enum(enum))  # type: ignore[operator]
            else:
                try:
                    context.set(self.name, self._enum[enum])  # type: ignore[index]
                except KeyError:
                    if self._default.__class__ is _Error:
                        Error.raise_error(io, context, codecs)
                    # It's just an integer/value, this is a _Pass condition
                    context.set(self.name, enum)
        super().io_build(io, context, codecs)


class Mapping(Enum):
    """
    Essentially the same as an Enum Codec, except that it takes a dictionary
    as a list of enum values instead of building them out of the kwargs.

    >>>  "protocol" / Mapping(
        8,
        {
            ICMP: 1,
            TCP: 6,
            UDP: 17,
        }
        default=Error|Pass
    )
    """

    @override
    def __init__(
        self,
        size: int | FunctType[int],
        map: dict[str, int | str],
        *,
        default: DefaultType = Error,
    ) -> None:
        super().__init__(size, default=default, **map)


class Flag(Bits):
    """
    Defines a boolean or a 'flag' which represents one bit.

    >>> "inbound" / Flag()
    """

    @override
    def __init__(self) -> None:
        super().__init__(size=1)

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        stream = self._read_io(io, context, codecs)
        context[self.name] = int(stream) == 1


class Const(Codec):
    """
    Asserts that the parsed/built value always equals the constant,
    and adds the value to the build if not presented.

    >>> "version" / Const(Bits(24), const=0x2)
    """

    @override
    def __init__(self, subcodec: Codec, /, const: int | str) -> None:
        super().__init__(subcodec)
        self.constant = const

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        self.subcodec.io_parse(io, context, codecs)
        if (value := context[self.name]) != self.constant:
            raise ConstantError(
                io,
                context,
                codecs,
                f"Was expecting the value {self.constant} but got {value}",
            )

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name in context and (value := context[self.name]) != self.constant:
            raise ConstantError(
                io,
                context,
                codecs,
                f"Was expecting the value {self.constant} but got {value}",
            )
        if self.name not in context:
            context.set(self.name, self.constant)
        self.subcodec.io_build(io, context, codecs)


class Default(Codec):
    """
    If a value wasn't provided in the build container, this Codec
    will add the value to the container set to it's default value.

    >>> "version" / Default(Bits(24), default=0x2)
    """

    @override
    def __init__(self, subcodec: Codec, /, default: Any) -> None:
        super().__init__(subcodec)
        self.default = default

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        self.subcodec.io_parse(io, context, codecs)

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name not in context:
            context.set(self.name, self.default)
        self.subcodec.io_build(io, context, codecs)


class Array(Codec):
    """
    Used to parse/build a collection of codecs, can be used with concretely
    defined counts, or via a lambda expression.

    *Count*
    >>>  "signs" / Array(Bits(4), count=8)

    *Functional*
    >>>  "signs" / Array(Bits(4), count=lambda packet: packet.array_count)
    """

    @override
    def __init__(self, subcodec: Codec, /, count: int | FunctType[int]) -> None:
        super().__init__(subcodec)
        self._count = count

    @override
    @property
    def size(self) -> int:
        return super().size * self._count  # type: ignore[operator]

    def _get_count(self, container: Container) -> int:
        if callable(self._count):
            return self._count(container)
        return self._count

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        list_v: list[ValueType] = []
        for _ in range(0, self._get_count(context)):
            nested = Container()
            nested.set_parent(context)
            self.subcodec.io_parse(io, nested, StackC())
            list_v.extend(nested.values())
        context[self.name] = list_v

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        values = context[self.name]
        if not isinstance(values, Collection):
            raise TypeError(
                f"{self.__class__.__name__} expected an iterable object, got {type(values)}"
            ) from BuildError(io, context, codecs)
        count = self._get_count(context)
        if len(values) != count:
            raise SizeOfError(
                io,
                context,
                codecs,
                f"Expected collection to be size of exactly {count}, got {len(values)}",
            )
        for value in values:
            nested = Container()
            nested.set_parent(context)
            nested[self.name] = value
            self.subcodec.io_build(io, nested, codecs)


class RawBits(Codec):
    """
    When parsing or building this Codec, it will just copy over the raw
    IO stream into the container/stream.

    >>> "raw" / RawBits(8)
    """

    def __init__(self, size: FunctType[int] | int) -> None:
        super().__init__()
        self._size: FunctType[int] | int = size

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        value = self._read_io(io, context, codecs)
        context[self.name] = value

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name not in context:
            attr_error = AttributeError(
                f"Attempted to access {self.name!r} from the object {context!r}"
            )
            attr_error.add_note(f"Parent={context._ if hasattr(context, '_') else None}")
            raise attr_error from BuildError(io, context, codecs)
        value = context[self.name]
        if isinstance(value, bytes):
            context.set(self.name, BitStream(value))
        self._write_io(io, context, codecs, context[self.name], self.sizeof(io, context, codecs))


# ---------------- Computed ----------------


class Computed[T: ValueType](Codec):
    """
    Calculates the field upon parsing but doesn't build into the stream.
    Useful for performing calculations that don't affect the stream.

    >>> Computed(lambda packet: packet.length * 8)
    """

    @override
    def __init__(self, function: FunctType[T], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        # NOTE: The Computed class doesn't consume the bitstream
        computed = self.function(context)
        context[self.name] = computed

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        # NOTE: Same as the Pass() class
        add_codec_to_traceback(self, codecs)


class Bitshift[T: Any = int](Codec):
    """
    Codec which deals with splitting addresses into multiple
    bit fields, done by checking the size of the packet and
    applying a bitshift to combine the two packets.

    >>> Struct(
        "id_p1" / Bits(2),
        "random" / Bits(6),
        "id_p2" / Bits(8),
        "id" / Bitshift[int]("id", bitshift),
    )
    """

    @override
    def __init__(
        self,
        field_name: str,
        funct: Callable[..., T],
        *args: Any,
        msb: bool,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._field_name = field_name
        self._msb = msb
        self._funct = funct
        self._args = args
        self._kwargs = kwargs

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        # NOTE: The Bitshift class doesn't consume the bitstream
        if f"{self._field_name}_p1" in context:
            value = self._funct(context, self._field_name, self._msb, *self._args, **self._kwargs)
        elif f"{self._field_name}_p1" in context._:
            # Also look inside the context container
            value = self._funct(context._, self._field_name, self._msb, *self._args, **self._kwargs)
        else:
            raise KeyError from ParseError(io, context, codecs)
        context[self.name] = value

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        """The bitshift doesn't get built through this Codes and must be done beforehand."""
        # NOTE: Same as the Pass() class
        add_codec_to_traceback(self, codecs)


class Checksum(Bits):
    """
    Used to add a calculated checksum value upon building a Codec.

    >>> Checksum(
            16,
            crc=lambda value: crc_hqx(value, 16),
            field_names={
                "version",
                "header_length",
                "precedence",
                "minimize_delay",
                "high_throuput",
                "high_reliability",
                "minimize_cost",
                "total_length",
                "identification",
                "dont_fragment",
                "more_fragments",
                "fragment_offset",
                "ttl",
                "protocol",
                "checksum",
                "source_ip",
                "destination_ip",
                "options",
            }
        )
    """

    @override
    def __init__(self, size: int, /, crc: Callable[[Buffer], int], field_names: set[str]) -> None:
        self.size: int
        super().__init__(size)
        self.crc = crc
        self.field_names = field_names

    def _post_build(self, context: Container) -> BitStream:
        io = BitStream()
        for name, value in context.items():
            if isinstance(value, Container):
                self._post_build(value)
                continue
            if name not in self.field_names:
                continue

            if isinstance(value, BitStream):
                io += value
            else:
                io += BitStream(value)
        return io

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        data: BitStream = self._post_build(context)
        checksum = self.crc(bytes(data))
        super().io_build(io, Container({self.name: checksum}), codecs)


# ---------------- Greedy ----------------


class GreedyArray(Array):
    """
    Used to parse/build a collection of codecs, can be used with concretely
    defined counts, or via a lambda expression. Except with this one we can
    define an infinite or bounded amount of collections.

    If defined as infinite, it will consume the collection until there are no
    more to consume and add them to the stream.

    *Count until EOS*
    >>>  "signs" / GreedyArray(Bits(4))

    *Consume until count*
    >>>  "signs" / Array(Bits(4), max_count=4)

    *Functionally consume until count*
    >>>  "signs" / Array(Bits(4), max_count=lambda packet: packet.array_count)
    """

    @override
    def __init__(self, subcodec: Codec, /, max_count: int | FunctType[int] = -1) -> None:
        if max_count == 0:
            raise InitError("Count cannot be 0")
        super().__init__(subcodec, max_count)
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        values: list[ValueType] = []
        max_count = self._get_count(context)
        i = 0
        if max_count > 0:
            i = max_count
        else:
            while len(io):
                nested = Container()
                nested.set_parent(context)
                self.subcodec.io_parse(io, nested, codecs)
                values.append(nested[self.name])
                i += 1
                if max_count > 0 and i >= max_count:
                    break
        context[self.name] = values

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        values = context[self.name]
        if not isinstance(values, Collection):
            raise TypeError(
                f"{self.__class__.__name__} expected an iterable object, got {type(values)}"
            ) from BuildError(io, context, codecs)

        max_count = self._get_count(context)
        if max_count > 0 and len(values) != self._count:
            raise ValueError(
                f"Expected collection to be size of exactly {max_count}, got {len(values)}",
            ) from BuildError(io, context, codecs)
        for value in values:
            self.subcodec.io_build(io, Container({self.name: value}), codecs)


class GreedyBits(Codec):
    """
    Used to parse/build an arbitrarily sized Codec, can be used with concretely
    defined max size or via a lambda expression. This Codec will consume the IO
    stream until it reaches a EOS or when it is at it's max size.

    If defined as infinite, it will consume the collection until there are no
    more to consume and add them to the stream.

    If size is defined as a negative value, the stream will continue
    consuming until an offset amount of bits (-x) from the EOS.

    *Consume until EOS*
    >>>  "payload" / GreedyBits()

    *Consume until max size*
    >>>  "payload" / GreedyBits(max_size=4)

    *Functionally consume until max size*
    >>>  "payload" / GreedyBits(max_size=lambda packet: packet.size)

    *Consume until an offset (-x) from EOS*
    >>>  "payload" / GreedyBits(max_size=-4)
    """

    @override
    def __init__(self, *, max_size: FunctType[int] | int = 0) -> None:
        super().__init__()
        self._max_size: FunctType[int] | int = max_size
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def sizeof(self, io: BitStream, context: Container, codecs: StackC) -> int:
        if callable(self._max_size):
            size = self._max_size(context)
        elif self._max_size > 0:
            size = self._max_size
        # Requires IO
        elif io is None:
            raise SizeOfError(
                context,
                codecs,
                f"Cannot get size of a {self.__class__.__name__} without an IO stream",
            )
        elif self._max_size == 0:
            size = len(io)
        else:
            size = len(io) + self._max_size  # Offset
        return size

    @override
    def io_parse(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        value = self._read_io(io, context, codecs)
        context[self.name] = value

    @override
    def io_build(self, io: BitStream, context: Container, codecs: StackC) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name not in context:
            attr_error = AttributeError(
                f"Attempted to access {self.name!r} from the object {context!r}"
            )
            attr_error.add_note(f"Parent={context._ if hasattr(context, '_') else None}")
            raise attr_error from BuildError(io, context, codecs)

        value = context[self.name]
        if isinstance(value, bytes):
            value = BitStream(value)

        size = self.sizeof(BitStream(), context, codecs)
        if size < 0:
            # Due to the max size subtracting from the length of the IO,
            # just send in the full length of the current IO stream.
            self._write_io(io, context, codecs, value, len(value))
            return
        self._write_io(io, context, codecs, value, self.sizeof(value, context, codecs))
