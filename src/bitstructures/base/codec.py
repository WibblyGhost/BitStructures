from collections import UserDict
from collections.abc import Collection, Generator
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum as Enum_
from typing import Any, NoReturn, Protocol, Self, SupportsIndex, override

from bitstring import ConstBitStream, CreationError, ReadError

from bitstructures.constants import PP_DETENT, PP_INDENT, PP_TAB
from bitstructures.exceptions import (
    BuildError,
    CodecAttributeError,
    CodecError,
    CodecTypeError,
    CodecValueError,
    ConstantError,
    FrozenError,
    InitError,
    IoError,
    ParseError,
    SizeError,
    SizeOfError,
    StackError,
    TriggeredError,
    add_codec_traceback,
)
from bitstructures.typing import (
    CodecProtocol,
    DefaultType,
    ExpType,
    FunctType,
    IoType,
    ReadIoType,
    StructProtocol,
    SupportsName,
    ValueType,
    WriteIoType,
)

# ---------------- Wrappers ----------------
__protocol_type = type(Protocol)


class SingletonMeta(__protocol_type):  # type: ignore[misc, valid-type]
    """
    METACLASS
    Defines a class that only ever needs to be initialised once,
    and is used globally without new classes being created.
    *This class must be the used as a metaclass when subclassing*

    - Not Thread Safe
    """

    _instances: dict["SingletonMeta", type] = {}

    def __call__(self, *args: Any, **kwargs: Any) -> type:
        if self not in self._instances:
            self._instances[self] = super().__call__(*args, **kwargs)
        return self._instances[self]


class FrozenSlots:
    __slots__ = ("_frozen",)

    def __init__(self) -> None:
        self._frozen: bool = False

    def set_frozen(self) -> None:
        self._frozen = True

    def _check_frozen(self) -> None:
        if self._frozen:
            raise FrozenError("Class is now frozen, cannot change attributes")

    def __setattr__(self, attr: str, value: Any) -> None:
        frozen = False
        if "_frozen" in self.__slots__:
            frozen = getattr(self, "_frozen", False)
        if not attr.startswith("__") and frozen is True:
            raise FrozenError("Trying to set attribute on a frozen instance")
        return super().__setattr__(attr, value)


class Frozen:
    _frozen: bool = False

    def __init__(self) -> None:
        self._frozen: bool = False

    def set_frozen(self) -> None:
        self._frozen = True

    def _check_frozen(self) -> None:
        if self._frozen:
            raise FrozenError("Class is now frozen, cannot change attributes")

    def __setattr__(self, attr: str, value: Any) -> None:
        if not attr.startswith("__") and getattr(self, "_frozen", False) is True:
            raise FrozenError("Trying to set attribute on a frozen instance")
        return super().__setattr__(attr, value)


# ---------------- Containers ----------------


@dataclass(slots=True, frozen=True)
class Value:
    name: str
    v_item: ValueType
    size: int = field(default=-1, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("Value's name is not of type str")
        if not isinstance(self.size, int):
            raise TypeError("Value's size is not of type int")
        if self.size < 0:
            raise SizeError("Value's size cannot be negative")

    @property
    def bitstream(self) -> ConstBitStream:
        if not isinstance(self.v_item, ConstBitStream):
            raise TypeError(
                f"Expected item to be of type ConstBitStream but got {type(self.v_item)}"
            )
        return self.v_item

    def __str__(self) -> str:
        return f"<{self.name!r}: {self.v_item!s}>"

    def __repr__(self) -> str:
        return f"<{self.name!r}: {self.v_item!s}, size={self.sizeof()}>"

    def pprint(self) -> str:
        return f"{self.name!r:<30} | size={self.sizeof():<2} | {self.v_item!s}"

    def __hash__(self) -> int:
        return hash(self.v_item)

    def __eq__(self, value: object) -> bool:
        return self.v_item == value

    def __float__(self) -> float:
        if not isinstance(self.v_item, str | float | int):
            raise TypeError(f"Cannot perform a float conversion on a {type(self.v_item)}")
        return float(self.v_item)

    def __int__(self) -> int:
        if not isinstance(self.v_item, str | int):
            raise TypeError(f"Cannot perform a int conversion on a {type(self.v_item)}")
        return int(self.v_item)

    def sizeof(self) -> int:
        if self.size < 0:
            raise SizeError(f"Value {self.name} doesn't have a size")
        return self.size


class Container[T: Any = Any](Frozen, UserDict[str, T]):
    def __init__(self, data: dict[str, T] | None = None, **kwargs: T) -> None:
        Frozen.__init__(self)
        UserDict.__init__(self, **kwargs)
        if data:
            self.data.update(data)
            self._convert_dict(self.data)

    @classmethod
    def _convert_dict(cls, data: "Container[T] | dict[str, T] | T") -> "Container[T]":
        # RECURSIVE
        if isinstance(data, dict) and not isinstance(data, Container):
            return Container(**data)
        for key, value in data.items():
            if isinstance(value, dict):
                data[key] = cls._convert_dict(value)  # type: ignore[assignment]
        return data

    def __getattr__(self, attr: str) -> T:
        """Custom getattr method that also searches the dictionary for the attribute"""
        if attr in self.data and (value := self.data.get(attr)) is not None:
            return value
        raise AttributeError(
            f"Attribute {attr!r} not found in current {self!r}", name=attr, obj=self
        )

    @override
    def __setitem__(self, name: str, item: T) -> None:
        self._check_frozen()
        super().__setitem__(name, item)

    @override
    def __delitem__(self, name: str) -> None:
        self._check_frozen()
        super().__delitem__(name)

    @override
    def __ior__(self, other: Any) -> Self:  # type: ignore[override]
        self._check_frozen()
        return super().__ior__(other)

    @override
    def update(self, data: dict[str, T]) -> None:  # type: ignore[override]
        self._check_frozen()
        super().update(data)

    @override
    def copy(self) -> "Container[T]":
        return Container[T](**self.data)

    def set(self, name: str, item: T, *, ignore_frozen: bool = False) -> None:
        if not ignore_frozen:
            self._check_frozen()
        self.data[name] = item

    def __str__(self) -> str:
        return f"{self.data!s}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data!r})"

    def pprint(self, *, padding: str = "\t{t}{v:-^38}{t}\n", depth: int = 1) -> str:
        # RECURSIVE
        stack = ""
        for key, value in self.data.items():
            container_str = f"{key}: {value}"
            if isinstance(value, Container):
                # Contains nested values, e.g. a Container
                stack += padding.format(t=PP_INDENT * depth, v=key)
                stack += value.pprint(padding=padding, depth=depth + 1)
                stack += padding.format(t=PP_DETENT, v="")
            elif isinstance(value, Collection) and not isinstance(value, str):
                # List of values or Containers
                list_padding = "\t{t} {v}{f}\n"
                stack += padding.format(t=PP_INDENT * depth, v=f"{key} (Collection: {len(value)})")
                list_stack = []
                container_stack = ""
                for sn, item in enumerate(value):
                    if isinstance(item, Container):
                        f = item.pprint(padding="", depth=depth).rstrip()
                        container_stack += list_padding.format(t=f"*{sn}", v="\n", f=f)
                        list_stack.append(f"*{sn}")
                    else:
                        list_stack.append(str(item))
                list_ = f"[{', '.join(list_stack)}]"
                stack += list_padding.format(t="." * depth, v=list_, f="")
                stack += container_stack

            else:
                stack += f"\t{PP_TAB * (depth - 1)} {container_str}\n"
        return stack


class Stack[T: SupportsName](FrozenSlots):
    __slots__ = ("_items", "_parent")

    def __init__(self) -> None:
        self._items: list[T] = []
        self._parent: Stack[T] | None = None
        super().__init__()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._items})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._items})"

    def pop(self, index: SupportsIndex = -1) -> T:
        self._check_frozen()
        return self._items.pop(index)

    def set(self, index: SupportsIndex, value: T) -> None:
        self._check_frozen()
        self._items[index] = value

    def empty(self) -> bool:
        return not self._items

    def _validate_item(self, item: T) -> None:
        # Don't allow duplicate names in the codec
        # unless it's a special privately defined field
        name = item.name
        if not name.startswith("__") and name in self:
            key_error = KeyError(f"Key name {name!r} already exists in the stack")
            key_error.add_note(f"Items: {self._items!r}")
            key_error.add_note(f"Names: {[item.name for item in self._items]}")
            key_error.add_note(f"Value: {item.name}::{item!r}")
            raise key_error

    def push(self, item: T) -> None:
        self._check_frozen()
        self._validate_item(item)
        self._items.append(item)

    def attach_parent(self, parent: "Stack[T]") -> None:
        self._parent = parent

    @property
    def _(self) -> "Stack[T]":
        """
        Used to retrieve the parent stack if the structure isn't embedded.
        | opcode
        | --|
            | Switch(lambda packet: packet._.opcode, ...)
        """
        if self._parent is None:
            raise AttributeError("Parent stack was never set, cannot retrieve value")
        return self._parent

    def __contains__(self, key: str) -> bool:
        return key in {item.name for item in self._items}

    def __iter__(self) -> Generator[T]:
        yield from self._items

    def enumerate(self) -> Generator[tuple[int, T]]:
        yield from enumerate(self._items)


class StackC(Stack["Codec|StackC"]):
    """For use in the Structs"""

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


class StackV(Stack[Value]):
    """For use in the parsing and building"""

    __slots__ = ()

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.to_container()})"

    def get(self, key: str) -> tuple[int, Value]:
        for sn, item in self.enumerate():
            if item.name == key:
                return sn, item
        raise KeyError(f"Key name {key!r} doesn't exist in the container")

    def __getattr__(self, attr: str) -> Any:
        """
        Called when an attribute is not found in the class,
        in our case, we use this to index the stack for the item.
        """
        _sn, item = self.get(attr)
        return item.v_item

    def sizeof(self) -> int:
        return sum(item.sizeof() for item in self._items)

    def to_container(self) -> Container:
        # RECURSIVE
        container = Container()
        for item in self:
            if isinstance(item.v_item, StackV):
                container.set(item.name, item.v_item.to_container(), ignore_frozen=True)
            elif isinstance(item.v_item, list):
                array = []
                for i in item.v_item:
                    if isinstance(i, Value):
                        array.append(i.v_item)
                    else:
                        raise ValueError(f"Unhandled list type {type(i)} in to_container")
                container.set(item.name, array, ignore_frozen=True)
            elif item.name.startswith("__"):
                continue  # Not a public attribute
            elif item.name in container:
                raise KeyError(f"Key name {item.name} already exists in the container")
            else:
                container.set(item.name, item.v_item, ignore_frozen=True)
        container.set_frozen()
        return container

    def pprint(self, *, depth: int = 1) -> str:
        # RECURSIVE
        padding = "\t{t}{v:-^38}{t}\n"
        stack = ""
        size = 0
        for item in self:
            if isinstance(item.v_item, StackV):
                stack += padding.format(t=PP_INDENT * depth, v=f"{item.name} {item.sizeof()}")
                stack += item.v_item.pprint(depth=depth + 1)
                stack += padding.format(t=PP_DETENT, v="")
            else:
                stack += f"\t{PP_TAB * (depth - 1)} {item.pprint()}\n"
            size += item.sizeof()
        return stack

    def get_io(self) -> ConstBitStream:
        # RECURSIVE
        io = ConstBitStream()
        for item in self:
            if isinstance(item.v_item, StackV):
                io += item.v_item.get_io()
            else:
                io += ConstBitStream(item.bitstream)
        return ConstBitStream(io)


# ---------------- Base Class ----------------


class Codec(CodecProtocol):
    def __init__(self, subcodec: "Codec | None" = None) -> None:
        """
        Base class for codecs and is ideally subclassed for ALL codecs, contains
        all the logic needed for representing sizes, hashes,
        strings, naming, parsing and building.

        self._subcodec:     Codec to use when building, parsing or getting sizeof
        self.name:          Name of this codec, can use "name" / Codec to name this codec
        self.size:         Size in bits of this codec
        """
        self._subcodec: Codec | None = subcodec
        self._initialized: bool = False
        self._name: str = ""
        self._size: int | FunctType[int] = subcodec.size if subcodec else -1

    @property
    def name(self) -> str:
        return self._name

    @property
    def size(self) -> int | FunctType[int]:
        if isinstance(self._size, int):
            if self._size < 0:
                raise SizeError(f"{self!r} has a negative size")
            return self._size
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
        self._name = name
        self._initialized = True
        if hasattr(self, "_subcodec") and self._subcodec:
            # Uses private subcodec, as this can be None
            self._subcodec.rename(name)

    def sizeof(self, parent: StackV, codecs: StackC, io: IoType = None) -> int:  # noqa: ARG002
        self._check_initialized()
        size: int = self._size(parent) if callable(self._size) else self._size
        if size < 0:  # If size is negative
            add_codec_traceback(self, codecs)
            raise SizeOfError(
                parent, codecs, f"Cannot perform a size method on {self.__class__.__name__}"
            )
        return size

    def _parse_io(self, raw: bytes | ConstBitStream) -> ConstBitStream:
        """Converts raw bytes into a ConstBitStream to work with"""
        self._check_initialized()
        if isinstance(raw, ConstBitStream):
            return raw
        return ConstBitStream(raw)

    def _read_io(
        self, parent: StackV, codecs: StackC, io: ReadIoType
    ) -> tuple[ConstBitStream, int]:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.

        - Must be used in the subclass
        """
        peek: ConstBitStream | None = None
        self._check_initialized()
        size = self.sizeof(parent, codecs, io)
        try:
            peek = io.peek(size)
            return ConstBitStream(io.read(size)), size
        except ReadError as err:
            add_codec_traceback(self, codecs)
            raise ParseError(
                parent,
                codecs,
                peek or io,
                "Ran into an error reading ConstBitStream",
            ) from err

    def _write_io(
        self,
        parent: StackV,
        codecs: StackC,
        name: str,
        value: WriteIoType,
    ) -> None:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.

        - Must be used in the subclass
        """
        if not isinstance(value, int | EnumBase | ConstBitStream):
            raise CodecTypeError(
                parent,
                codecs,
                f"Cannot build a value of type {type(value)}, "
                f"must be one of int | EnumBase | ConstBitStream",
            )

        if isinstance(value, EnumBase):
            value = value.value

        if isinstance(value, ConstBitStream):
            length = self.sizeof(parent, codecs, value)
        else:
            length = self.sizeof(parent, codecs, None)

        if length == 0:
            return
        if isinstance(value, ConstBitStream):
            if length > value.length:
                add_codec_traceback(self, codecs)
                raise BuildError(
                    parent,
                    codecs,
                    Container({"value": value}),
                    "Ran into an error writing ConstBitStream",
                ) from SizeOfError(
                    parent,
                    codecs,
                    f"Cannot pack a ConstBitStream of length {value.length} into {length} bits",
                )
            io = value
            parent.push(Value(name, io, len(io)))
            codecs.push(self)
        else:
            try:
                io = ConstBitStream(uint=value, length=length)
                parent.push(Value(name, io, len(io)))
                codecs.push(self)
            except (CreationError, CodecError) as err:
                add_codec_traceback(self, codecs)
                raise BuildError(
                    parent,
                    codecs,
                    Container({"value": value}),
                    "Ran into an error writing ConstBitStream",
                ) from err


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
    def subcodecs(self) -> Stack[Codec]:
        return self._subcodec_stack

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
        self._subcodec_stack: Stack[Codec] = Stack[Codec]()
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

    def parse(self, raw: ConstBitStream, *, readall: bool = True) -> StackV:
        """
        Called externally via users.

        Handles the core parsing of the raw bytes into a ConstBitStream object,
        then passes the IO stream into the io_parse for custom parsing.
        - Generally not modified in subclasses
        """
        if not isinstance(raw, bytes | ConstBitStream):
            raise TypeError(
                f"Parse only accepts a argument with type "
                f"{bytes.__name__} | {ConstBitStream.__name__}, got {type(raw)}"
            )
        parent = StackV()
        codecs = StackC()
        try:
            io = self._parse_io(raw)
            self.io_parse(parent, codecs, io)
            parent.set_frozen()
            if parent.empty():
                add_codec_traceback(self, codecs)
                raise StackError(parent, codecs, io, "Parsed stack is empty")
            if readall and io.bitpos != len(io):
                add_codec_traceback(self, codecs)
                raise IoError(parent, codecs, io, f"IO hasn't reached a terminator but {readall=}")
            if parent.sizeof() % 8 != 0:
                add_codec_traceback(self, codecs)
                raise SizeOfError(
                    parent,
                    codecs,
                    f"Parsed bits must be divisible by 8 (1 byte), {io!r} {io.len=}",
                )
            return parent
        except CodecError:
            # CodecError - These error subtypes already have all the trace
            #              information required.
            raise
        except Exception as err:
            add_codec_traceback(self, codecs)
            raise ParseError(parent, codecs, io, repr(err), raw=raw) from err

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        if self.name == self.__PRIVATE_NAME:
            # Force this class to be embedded if it hasn't been assigned a descriptor
            # E.g. When assigning a Struct to a variable
            self.embedded = True

        # Embedding structs
        if not self.embedded:
            stack = StackV()
            if parent:
                # Used for indexing parent packets in lambdas
                stack.attach_parent(parent)
            codec_stack = StackC()
            codec_stack.name = self.name
        else:
            stack = parent
            codec_stack = codecs

        for subcodec in self.subcodecs:
            subcodec.io_parse(stack, codec_stack, io)

        if not self.embedded:
            parent.push(Value(self.name, stack, size=stack.sizeof()))
            codecs.push(codec_stack)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if self.name == self.__PRIVATE_NAME:
            # Force this class to be embedded if it hasn't been assigned a descriptor
            # E.g. When assigning a Struct to a variable
            self.embedded = True
        container = container if self.embedded else container[self.name]

        # Embedding structs
        if not self.embedded:
            stack = StackV()
            if parent:
                # Used for indexing parent packets in lambdas
                stack.attach_parent(parent)
            codec_stack = StackC()
            codec_stack.name = self.name
        else:
            stack = parent
            codec_stack = codecs
        post_build = None

        # Checksums
        for subcodec in self.subcodecs:
            if isinstance(subcodec, Checksum):
                post_build = subcodec.post_build
            subcodec.io_build(stack, codec_stack, container)
        if post_build:  # For use in checksums
            post_build(stack, codecs)

        if not self.embedded:
            parent.push(Value(self.name, stack, size=stack.sizeof()))
            codecs.push(codec_stack)

    def build(self, container: Container) -> ConstBitStream:
        """
        Called externally via users.

        Handles the core building of a Container into a bytes object,
        by passing the Container into the io_build for custom parsing.
        - Generally not modified in subclasses
        """
        if not isinstance(container, Container):
            raise TypeError(
                f"Build only accepts a argument with type {Container.__name__}, "
                f"got {type(container)}"
            )
        parent = StackV()
        codecs = StackC()
        container_ = container.copy()  # Don't modify the current Container
        try:
            self.io_build(parent, codecs, container_)
            io = parent.get_io()
            if len(io) % 8 != 0:
                add_codec_traceback(self, codecs)
                raise SizeOfError(
                    parent,
                    codecs,
                    f"Built bits must be divisible by 8 (1 byte), {io!r} {io.len=}",
                )
            return io
        except CodecError:
            # CodecError - These error subtypes already have all the trace
            #              information required.
            raise
        except Exception as err:
            add_codec_traceback(self, codecs)
            raise BuildError(parent, codecs, container_, repr(err)) from err

    def sizeof(self, parent: StackV, codecs: StackC, io: ConstBitStream | None = None) -> int:
        if isinstance(self.size, int) and self.size > 0:
            return self.size
        return super().sizeof(parent, codecs, io)


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
        start_codec: tuple[Codec],
        end_codec: tuple[Codec],
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
    def sizeof(self, parent: StackV, codecs: StackC, io: IoType = None) -> int:
        return self._end

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        """This IO parse method doesn't consume the IO stream, we just *peek* at the stream"""
        try:
            start = io.read(self._start)
            end = io.read(self._end - self._start)
            # Swap the order of the start and end IO, then parse normally
            swapped_io = ConstBitStream(end + start)
        except ReadError as err:
            add_codec_traceback(self, codecs)
            raise ParseError(
                parent,
                codecs,
                io,
                "Ran into an error reading ConstBitStream",
            ) from err
        super().io_parse(parent, codecs, swapped_io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        for codec in (*self._end_codec, *self._start_codec):
            codec.io_build(parent, codecs, container)


# ---------------- Error Handlers ----------------


class _Pass(Codec, metaclass=SingletonMeta):
    """Declarer that this Codec *shouldn't* error when it fails to map"""

    __PRIVATE_NAME = "__pass"

    @override
    def __init__(self) -> None:
        self._name = self.__PRIVATE_NAME

    @override
    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        pass

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        pass


Pass = _Pass()


class _Error(Codec, metaclass=SingletonMeta):
    """Declarer that this Codec *should* error when it fails to map"""

    __PRIVATE_NAME = "__error"

    @override
    def __init__(self) -> None:
        self._name = self.__PRIVATE_NAME

    @override
    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_traceback(self, codecs)
        self.raise_error(parent, codecs, container=container)

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_traceback(self, codecs)
        self.raise_error(parent, codecs, io=io)

    @classmethod
    def raise_error(cls, parent: StackV, codecs: StackC, **kwargs: Any) -> NoReturn:
        raise TriggeredError(
            "This error was triggered via a default set to Error",
            parent,
            codecs,
            **kwargs,
        )


Error = _Error()
NotImplementedCodec = Error

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
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        _, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, ConstBitStream(length=size), size))
        codecs.push(self)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        size = self.sizeof(parent, codecs)
        pattern = bin(self._pattern)
        binary = ConstBitStream(pattern)
        while len(binary) < size:
            binary += pattern
            if len(binary) > size:
                add_codec_traceback(self, codecs)
                raise SizeOfError(
                    parent,
                    codecs,
                    f"Defined pattern {binary.bin!s} ({len(binary.bin)} bits) "
                    f"couldn't be repeated within {size} bits",
                )
        self._write_io(parent, codecs, self.name, binary)


class BitsInt(Codec):
    """
    Defines a integer representation from the ConstBitStream,
    will return an integer when parsing and takes ant int on building.

    >>> "int1" / BitInts(8)
    """

    @override
    def __init__(self, size: int | FunctType[int]) -> None:
        super().__init__()
        self._size = size

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        value, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, value.uint, size))
        codecs.push(self)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if self.name not in container:
            add_codec_traceback(self, codecs)
            raise CodecAttributeError(
                parent,
                codecs,
                container,
                f"Name {self.name} wasn't found in the container",
            )
        self._write_io(parent, codecs, self.name, container[self.name])


class EnumBase(Enum_):
    """Basic override for the Enum object to change string representations"""

    name: str
    value: int

    @override
    def __str__(self) -> str:
        return self.name

    # Not an override
    def __int__(self) -> int:
        return self.value

    @override
    def __repr__(self) -> str:
        return f"<{self.name}: {self.value}>"

    @override
    def __eq__(self, other: object) -> bool:
        if other in (self.name, self.value):
            return True
        return super().__eq__(other)

    @override
    def __hash__(self) -> int:
        return hash(self.name)


class Enum(BitsInt):
    """
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
        self._default = default

    @property
    def enum(self) -> EnumBase:
        return self._enum

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        peek = io.peek(self.sizeof(parent, codecs, io))
        super().io_parse(parent, codecs, io)

        sn, value = parent.get(self.name)
        enum_value = value.v_item
        if enum_value in self.enum:  # type: ignore[operator]
            parent.set(sn, Value(value.name, self.enum(enum_value), value.sizeof()))  # type: ignore[operator]
            return
        if enum_value in self.enum._value2member_map_:  # type: ignore[attr-defined]
            parent.set(sn, Value(value.name, self.enum[enum_value], value.sizeof()))  # type: ignore[index]
        if self._default.__class__ is _Pass:
            return
        if self._default.__class__ is _Error:
            add_codec_traceback(self, codecs)
            Error.raise_error(parent, codecs, key=enum_value)
        add_codec_traceback(self, codecs)
        raise ParseError(
            parent,
            codecs,
            peek,
            f"Value {value} wasn't a valid enum, {self._enum!r}",
        )

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        enum = container[self.name]
        if not isinstance(enum, EnumBase):
            # Just checking if the value is a valid enum
            if enum in self._enum:  # type: ignore[operator]
                container.set(self.name, self._enum(enum), ignore_frozen=True)  # type: ignore[operator]
            else:
                try:
                    container.set(self.name, self._enum[enum], ignore_frozen=True)  # type: ignore[index]
                except KeyError:
                    if self._default.__class__ is _Error:
                        add_codec_traceback(self, codecs)
                        Error.raise_error(parent, codecs, container=container)
                    # It's just an integer/value, this is a _Pass condition
                    container.set(self.name, enum, ignore_frozen=True)
        super().io_build(parent, codecs, container)


class Mapping(Enum):
    @override
    def __init__(
        self,
        size: int | FunctType[int],
        map: dict[str, int | str],
        *,
        default: DefaultType = Error,
    ) -> None:
        super().__init__(size, default=default, **map)

    def sizeof(self, parent: StackV, codecs: StackC, io: ConstBitStream | None = None) -> int:
        return super().sizeof(parent, codecs, io)


class Flag(BitsInt):
    """
    >>> "inbound" / Flag()
    """

    @override
    def __init__(self) -> None:
        super().__init__(size=1)

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        value, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, value.uint == 1, size))
        codecs.push(self)


class Const(Codec):
    """
    >>> "version" / Const(BitsInt(24), const=0x2)
    """

    @override
    def __init__(self, subcodec: Codec, /, const: int | str) -> None:
        super().__init__(subcodec)
        self.constant = const

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        self.subcodec.io_parse(parent, codecs, io)
        _sn, value = parent.get(self.name)
        if value.v_item != self.constant:
            add_codec_traceback(self, codecs)
            raise ConstantError(
                parent, codecs, f"Was expecting the value {self.constant} but got {value}"
            )

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if self.name in container and (value := container[self.name]) != self.constant:
            add_codec_traceback(self, codecs)
            raise ConstantError(
                parent, codecs, f"Was expecting the value {self.constant} but got {value}"
            )
        self.subcodec.io_build(parent, codecs, container)


class Default(Codec):
    """
    >>> "version" / Default(BitsInt(24), default=0x2)
    """

    @override
    def __init__(self, subcodec: Codec, /, default: Any) -> None:
        super().__init__(subcodec)
        self.default = default

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        self.subcodec.io_parse(parent, codecs, io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if self.name not in container:
            container.set(self.name, self.default, ignore_frozen=True)
        self.subcodec.io_build(parent, codecs, container)


class Array(Codec):
    """
    ## Count
    >>>  "signs" / Array(BitsInt(4), count=8)

    ## Functional
    >>>  "signs" / Array(BitsInt(4), count=lambda packet: packet.array_count)
    """

    @override
    def __init__(self, subcodec: Codec, /, count: int | FunctType[int]) -> None:
        super().__init__(subcodec)
        self._count = count

    def _get_count(self, parent: StackV) -> int:
        if callable(self._count):
            return self._count(parent)
        return self._count

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        list_v: list[Value] = []
        for _ in range(0, self._get_count(parent)):
            stack_v = StackV()
            self.subcodec.io_parse(stack_v, StackC(), io)
            list_v.append(stack_v.pop())
        parent.push(Value(self.name, list_v, sum(item.sizeof() for item in list_v)))
        codecs.push(self)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        values = container[self.name]
        if not isinstance(values, Collection):
            add_codec_traceback(self, codecs)
            raise CodecTypeError(
                parent,
                codecs,
                f"{self.__class__.__name__} expected an iterable object, got {type(values)}",
            )
        count: int | ConstBitStream = self._get_count(parent)
        if isinstance(count, ConstBitStream):
            count = count.int
        if len(values) != count:
            add_codec_traceback(self, codecs)
            raise SizeOfError(
                parent,
                codecs,
                f"Expected collection to be size of exactly {count}, got {len(values)}",
            )
        raw = ConstBitStream()
        for value in values:
            stack = StackV()
            self.subcodec.io_build(stack, codecs, Container({self.name: value}))
            raw += stack.pop().bitstream
        parent.push(Value(self.name, raw, len(raw)))
        codecs.push(self)


class Checksum(BitsInt):
    """
    >>> Checksum(
            16,
            crc=lambda value: crc_hqx(value, 0),
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
    def __init__(self, size: int, /, crc: ExpType, field_names: set[str]) -> None:
        self.size: int
        super().__init__(size)
        self.crc = crc
        self.field_names = field_names

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        # The checksum field itself is set to zero during checksum calculation.
        self._write_io(parent, codecs, self.name, 0)

    def _post_build(self, parent: StackV, data: ConstBitStream) -> None:
        for item in parent:
            if isinstance(item.v_item, StackV):
                self._post_build(item.v_item, data)
                continue
            if item.name.startswith("__"):
                data += item.bitstream
                continue
            if item.name not in self.field_names:
                continue
            self.field_names.remove(item.name)
            data += item.bitstream

    def post_build(self, parent: StackV, codecs: StackC) -> None:
        data = ConstBitStream()
        self._post_build(parent, data)
        if len(data) % 8 != 0:
            add_codec_traceback(self, codecs)
            raise SizeOfError(
                parent,
                codecs,
                f"{self.__class__.__name__} expected the contents "
                f"to be divisible by 8 (1 byte), got {len(data)}",
            )
        checksum = self.crc(data.bytes)
        sn, value = parent.get(self.name)
        parent.set(
            sn,
            Value(
                value.name,
                ConstBitStream(uint=checksum, length=self.size),
                size=self.size,
            ),
        )


# ---------------- Mappings ----------------


class Switch[MKey: Any, MValue: Codec | Struct = Codec](Codec):
    """
    >>> "header" / Switch[str, Codec](
        lambda packet: packet.protocol,
        {"UDP": UDP_HEADER, "TCP": TCP_HEADER}
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
        self.function = funct
        self._mapping = mapping
        self._default = default
        self.embedded = embedded
        for codec in self._mapping.values():
            codec.rename(self.name)
            if embedded is True and isinstance(codec, Struct):
                codec.embedded = embedded
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    def rename(self, name: str) -> None:
        super().rename(name)
        for codec in self._mapping.values():
            codec.rename(self.name)

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
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        mapping_key: MKey = None
        subcodec: DefaultType | MValue = None
        try:
            mapping_key = self.function(parent)
            subcodec = self._mapping[mapping_key]
        except (ValueError, KeyError):
            if self._default.__class__ is _Error:
                add_codec_traceback(self, codecs)
                Error.raise_error(
                    parent, codecs, io=io, key=mapping_key, mapping=list(self._mapping)
                )
            if self._default.__class__ is _Pass:
                return
            subcodec = self._default
        subcodec.io_parse(parent, codecs, io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        mapping_key = self.function(container)
        if mapping_key not in self._mapping:
            if self._default.__class__ is _Pass:
                return
            if self._default.__class__ is _Error:
                add_codec_traceback(self, codecs)
                Error.raise_error(
                    parent,
                    codecs,
                    container=container,
                    key=mapping_key,
                    mapping=list(self._mapping),
                )
            add_codec_traceback(self, codecs)
            raise BuildError(
                parent,
                codecs,
                container,
                f"Value {mapping_key} wasn't found in the mapping {self._mapping}",
            )

        subcodec = self._mapping[mapping_key]
        subcodec.io_build(parent, codecs, container)


# ---------------- Greedy ----------------


class GreedyArray(Array):
    """
    ## Greedy - Until EOF
    >>>  "signs" / GreedyArray(BitsInt(4))

    ## Count
    >>>  "signs" / GreedyArray(BitsInt(4), count=8)

    ## Functional
    >>>  "signs" / GreedyArray(BitsInt(4), count=lambda packet: packet.array_count)
    """

    @override
    def __init__(self, subcodec: Codec, /, max_count: int | FunctType[int] = -1) -> None:
        if max_count == 0:
            raise InitError("Count cannot be 0")
        super().__init__(subcodec, max_count)
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        values: list[Value] = []
        max_count = self._get_count(parent)
        i = 0
        if max_count > 0:
            i = max_count
        else:
            while io.pos < len(io):
                stack = StackV()
                self.subcodec.io_parse(stack, codecs, io)
                values.append(stack.pop())
                i += 1
                if max_count > 0 and i >= max_count:
                    break
        parent.push(Value(self.name, values, sum(item.sizeof() for item in values)))
        codecs.push(self)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        values = container[self.name]
        if not isinstance(values, Collection):
            add_codec_traceback(self, codecs)
            raise CodecTypeError(
                parent,
                codecs,
                container,
                f"{self.__class__.__name__} expected an iterable object, got {type(values)}",
            )

        max_count = self._get_count(parent)
        if max_count > 0 and len(values) != self._count:
            add_codec_traceback(self, codecs)
            raise CodecValueError(
                parent,
                codecs,
                container,
                f"Expected collection to be size of exactly {max_count}, got {len(values)}",
            )
        raw = ConstBitStream()
        for value in values:
            stack = StackV()
            self.subcodec.io_build(stack, codecs, Container({self.name: value}))
            raw += stack.pop().bitstream
        parent.push(Value(self.name, raw, len(raw)))
        codecs.push(self)


class GreedyBits(Codec):
    """
    ## No Max Size - Until EOF
    >>> "payload" / GreedyBits()

    ## Max Size
    >>> "payload" / GreedyBits(max_size=24)

    ## Functional
    >>> "payload" / GreedyBits(max_size=lambda packet: packet.payload_length * 8)

    ## Offset
    >>> "payload" / GreedyBits(max_size=-8)
    """

    @override
    def __init__(self, *, max_size: FunctType[int] | int = 0) -> None:
        super().__init__()
        self._max_size: FunctType[int] | int = max_size
        # NOTE: This is the one of the few class that is allowed a size of 0
        self._size = 0

    @override
    def sizeof(self, parent: StackV, codecs: StackC, io: IoType = None) -> int:
        if callable(self._max_size):
            size = self._max_size(parent)
        elif self._max_size > 0:
            size = self._max_size
        # Requires IO
        elif io is None:
            add_codec_traceback(self, codecs)
            raise SizeOfError(
                parent,
                codecs,
                f"Cannot get size of a {self.__class__.__name__} without an IO stream",
            )
        elif self._max_size == 0:
            size = len(io) - io.pos
        else:
            size = len(io) - io.pos + self._max_size  # Offset
        return size

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        value, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, value, size))
        codecs.push(self)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if self.name not in container:
            add_codec_traceback(self, codecs)
            raise BuildError(
                parent,
                codecs,
                container,
                f"Name {self.name} wasn't found in the container",
            )
        value = container[self.name]
        if isinstance(value, bytes):
            container.set(self.name, ConstBitStream(value), ignore_frozen=True)
        self._write_io(parent, codecs, self.name, container[self.name])


class RawBits(GreedyBits):
    def __init__(self, max_size: FunctType[int] | int) -> None:
        super().__init__(max_size=max_size)


# ---------------- Statements ----------------


class Conditional(Codec):
    """
    >>> UDP = Struct(...)
    >>> TCP = Struct(...)

    >>> "payload" / Conditional(lambda packet: packet.protocol, UDP, TCP),
    >>> "payload" / Conditional(lambda packet: packet.protocol, UDP, Pass),
    >>> "payload" / Conditional(lambda packet: packet.protocol, UDP, Error),
    """

    @override
    def __init__(
        self,
        condition: FunctType[int],
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
    def sizeof(self, parent: StackV, codecs: StackC, io: IoType = None) -> int:
        if self.condition(parent):
            return self._then.sizeof(parent, codecs, io)
        return self._else.sizeof(parent, codecs, io)

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        if self.condition(parent):
            self._then.io_parse(parent, codecs, io)
        elif self._else is not Pass:
            self._else.io_parse(parent, codecs, io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if self.condition(container):
            self._then.io_build(parent, codecs, container)
        else:
            self._else.io_build(parent, codecs, container)


class Optional(Codec):
    """
    >>> "options" / Optional(BitsInt(8))
    """

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        if self.sizeof(parent, codecs, io) == 0:
            return
        with suppress(ParseError):
            self.subcodec.io_parse(parent, codecs, io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        if self.name in container:
            self.subcodec.io_build(parent, codecs, container)


# ---------------- Helpers ----------------


def flatten(parent: StackV, *, stack: StackV | None = None) -> StackV:
    # RECURSIVE
    if stack is None:
        stack = StackV()
    # TODO: Handle duplicates and non-embedded stuctures
    for item in parent:
        if isinstance(item.v_item, StackV):
            _ = flatten(item.v_item, stack=stack)
        else:
            stack.push(item)
    return stack
