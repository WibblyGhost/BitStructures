from collections.abc import (
    Buffer,
    Callable,
    Collection,
    Generator,
    ItemsView,
    Iterable,
    Iterator,
    KeysView,
    MutableMapping,
    ValuesView,
)
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum as Enum_
from typing import Any, ClassVar, NoReturn, Protocol, Self, SupportsIndex, override

from bitstring import ConstBitStream, CreationError, ReadError

from bitstructures.constants import PP_DETENT, PP_INDENT, PP_TAB
from bitstructures.exceptions import (
    BitsIoError,
    BuildError,
    CodecError,
    ConstantError,
    FrozenError,
    InitError,
    ParseError,
    SizeError,
    SizeOfError,
    StackError,
    TriggeredError,
    add_codec_to_traceback,
)
from bitstructures.typing import (
    CodecProtocol,
    DefaultType,
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


class FrozenSlots:
    """
    Used to create a frozen class which cannot be modified after
    setting it as frozen.
    """

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


# ---------------- Containers ----------------


@dataclass(slots=True, frozen=True)
class Value:
    """
    Dataclass which stores all the information about the current encoded/decoded value,
    this will get passed around all the build/parse functions and contains name, size and values.
    """

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
        if isinstance(self.v_item, StackV):
            bitstream = ConstBitStream()
            for value in self.v_item:
                bitstream += value.bitstream
            return bitstream

        if not isinstance(self.v_item, ConstBitStream):
            raise TypeError(
                f"Expected item to be of type ConstBitStream but got "
                f"{type(self.v_item)}: {self.v_item!s}"
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


class Container[T: Any = Any](MutableMapping[str, T]):  # Can't use FrozenSlots here
    """
    Wrapper for a dictionary-like object, we use this to add extra functionality to
    the container indexing, and adding frozen attributes to the setters.

    You can access container attributes like normal `container["id"]` or via
    direct access `container.id`.
    """

    __slots__ = ("_data", "_frozen")

    def __init__(self, dictionary: dict[str, T] | None = None, **kwargs: T) -> None:
        self._data: dict[str, T] = {}
        self._frozen: bool = False
        if dictionary is not None:
            self._data.update(dictionary)
        if kwargs:
            self._data.update(kwargs)
        for key, value in self._data.items():
            if isinstance(value, dict):
                self[key] = Container(self[key])  # type: ignore[assignment]

    def _check_frozen(self) -> None:
        if self._frozen:
            raise FrozenError("Class is now frozen, cannot change attributes")

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __setitem__(self, key: str, value: T, /) -> None:
        self._check_frozen()
        self._data[key] = value

    def __getitem__(self, key: str) -> T:
        return self._data.get(key)  # type: ignore[return-value]

    def __delitem__(self, key: str, /) -> None:
        self._check_frozen()
        del self._data[key]

    def clear(self) -> None:
        self._check_frozen()
        self._data.clear()

    def pop(self, key: str, /, default: Any | None = None) -> T:
        self._check_frozen()
        return self._data.pop(key, default)  # type: ignore[return-value]

    def popitem(self) -> tuple[str, T]:
        self._check_frozen()
        return self._data.popitem()

    def update(self, data: dict[str, T]) -> None:  # type: ignore[override]
        self._check_frozen()
        self._data.update(data)

    def items(self) -> ItemsView[str, T]:
        return self._data.items()

    def keys(self) -> KeysView[str]:
        return self._data.keys()

    def values(self) -> ValuesView[T]:
        return self._data.values()

    def set_frozen(self) -> None:
        self._frozen = True

    def copy(self) -> Self:
        container = self.__class__(**self._data.copy())
        if self._frozen:
            container.set_frozen()
        return container

    def get(self, key: str, default: Any = None, /) -> T:
        return self._data.get(key, default)  # type: ignore[return-value]

    def set(self, key: str, value: T, *, ignore_frozen: bool = False) -> None:
        if not ignore_frozen:
            self._check_frozen()
        self._data[key] = value

    def _rec_str(self, value: T | dict[str, T]) -> Any:
        """Formats any nested Container's."""
        # RECURSIVE
        if isinstance(value, ConstBitStream):
            if len(value) % 8 == 0:
                return value.bytes
            return f"0b{value.bin}"
        if isinstance(value, list):
            return [self._rec_str(v) for v in value]
        if isinstance(value, Container | dict):
            return {
                key: self._rec_str(value)
                for key, value in value.items()
                if not key.startswith("__")
            }
        return value

    def __str__(self) -> str:
        return f"{self._rec_str(self._data)!s}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._data!r})"

    # CUSTOM GETATTR

    def __getattr__(self, attr: str) -> T:
        """Custom getattr method that also searches the dictionary for the attribute."""
        if attr in self._data and (value := self._data.get(attr)) is not None:
            return value
        raise AttributeError(
            f"Attribute {attr!r} not found in current {self!r}", name=attr, obj=self
        )

    def pprint(self, *, padding: str = "\t{t}{v:-^38}{t}\n", depth: int = 1) -> str:
        # RECURSIVE
        stack = ""
        for key, value in self._data.items():
            container_str = f"{key}: {value}"
            if isinstance(value, Container):
                # Contains nested values, e.g. a Container
                stack += padding.format(t=PP_INDENT * depth, v=key)
                stack += value.pprint(padding=padding, depth=depth + 1)
                stack += padding.format(t=PP_DETENT, v="")
            elif isinstance(value, list):
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
    """
    Custom data storage object which acts like a stack with push and pop methods,
    we use this for both pushing encoded/decoded values onto, or to push
    codec paths onto for parsing.
    """

    __slots__ = ("_items", "_parent")

    def __init__(self) -> None:
        self._items: list[T] = []
        self._parent: Stack[T] | None = None
        super().__init__()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._items})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._items})"

    def __len__(self) -> int:
        return len(self._items)

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


class StackV(Stack[Value]):
    """Version of the stack which contains methods for holding Value's."""

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
        for value in self:
            if value.name.startswith("__"):
                continue

            if isinstance(value.v_item, StackV):
                container.set(value.name, value.v_item.to_container(), ignore_frozen=True)
            elif isinstance(value.v_item, list):
                array = []
                for item in value.v_item:
                    if isinstance(item, StackV):
                        array.append(item.to_container())
                        continue
                    array.append(item)
                container.set(value.name, array, ignore_frozen=True)
            else:
                container.set(value.name, value.v_item, ignore_frozen=True)
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
        self._subcodec: Codec | None = subcodec
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
        self._name = name
        self._initialized = True
        if hasattr(self, "_subcodec") and self._subcodec:
            # Uses private subcodec, as this can be None
            self._subcodec.rename(name)

    def sizeof(self, parent: StackV | Container, codecs: StackC, io: IoType = None) -> int:  # noqa: ARG002
        self._check_initialized()
        size: int = self._size(parent) if callable(self._size) else self._size
        if size < 0:  # If size is negative
            raise SizeOfError(
                parent,
                codecs,
                (
                    f"Cannot perform a size method on {self.__class__.__name__}, "
                    f"or ran into an issue when calculating the size"
                ),
            )
        return size

    def _parse_io(self, raw: bytes | ConstBitStream) -> ConstBitStream:
        """Converts raw bytes into a ConstBitStream to work with."""
        self._check_initialized()
        return ConstBitStream(raw)  # If it's a ConstBitStream, this should reset it's `.pos`

    def _read_io(
        self, parent: StackV, codecs: StackC, io: ReadIoType
    ) -> tuple[ConstBitStream, int]:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.
        """
        peek: ConstBitStream | None = None
        self._check_initialized()
        size = self.sizeof(parent, codecs, io)
        try:
            peek = io.peek(size)
            return ConstBitStream(io.read(size)), size
        except ReadError as err:
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
        container: Container,
        name: str,
        value: WriteIoType,
    ) -> None:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.
        """
        if not isinstance(value, int | EnumBase | ConstBitStream):
            raise TypeError(
                f"Cannot build a value of type {type(value)}, "
                f"must be one of int | EnumBase | ConstBitStream"
            ) from CodecError(parent, codecs)

        if isinstance(value, EnumBase):
            value = value.value

        if isinstance(value, ConstBitStream):
            length = self.sizeof(container, codecs, value)
        else:
            length = self.sizeof(container, codecs, None)

        if length == 0:
            return
        if isinstance(value, ConstBitStream):
            if length > value.length:
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
        else:
            try:
                io = ConstBitStream(uint=value, length=length)
                parent.push(Value(name, io, len(io)))
            except (CreationError, CodecError) as err:
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

    @override
    @property
    def size(self) -> int:
        """
        Attempts to calculate the size of this Codec
        NOTE: This will not always work, or be accurate, please double check the
              output size is what you expect.
        """
        try:
            return sum(codec.size for codec in self.subcodecs)
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

    def parse(self, raw: bytes | ConstBitStream, *, readall: bool = True) -> StackV:
        """
        Handles parsing an IO stream into a Container by
        passing the IO into io_parse for custom parsing.
        - Not modified in subclasses
        - Called externally via users.
        """
        if not isinstance(raw, bytes | ConstBitStream):
            raise TypeError(
                f"Parse only accepts a argument with type "
                f"{bytes.__name__} | {ConstBitStream.__name__}, got {type(raw)}"
            )
        parent = StackV()
        codecs = StackC()
        add_codec_to_traceback(self, codecs)

        try:
            io = self._parse_io(raw)
            self.io_parse(parent, codecs, io)
            parent.set_frozen()
            if parent.empty():
                raise StackError(parent, codecs, io, "Parsed stack is empty")
            if readall and io.bitpos != len(io):
                raise BitsIoError(
                    parent, codecs, io, f"IO hasn't reached a terminator but {readall=}"
                )
            if parent.sizeof() % 8 != 0:
                raise SizeOfError(
                    parent,
                    codecs,
                    f"Parsed bits must be divisible by 8 (byte), {io!r} {io.len=}",
                )
            return parent
        except CodecError:
            # CodecError - These error subtypes already have all the trace
            #              information required.
            raise
        except Exception as err:
            raise ParseError(parent, codecs, io, repr(err), raw=ConstBitStream(raw)) from err

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name == self.__PRIVATE_NAME:
            # Force this class to be embedded if it hasn't been assigned a descriptor
            # E.g. When assigning a Struct to a variable
            self.embedded = True

        # Embedding structs
        if not self.embedded:
            stack = StackV()
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
        add_codec_to_traceback(self, codecs)

        if self.name == self.__PRIVATE_NAME:
            # Force this class to be embedded if it hasn't been assigned a descriptor
            # E.g. When assigning a Struct to a variable
            self.embedded = True
        container = container if self.embedded else container[self.name]

        # Embedding structs
        if not self.embedded:
            stack = StackV()
            stack.attach_parent(parent)
            codec_stack = StackC()
            codec_stack.name = self.name
        else:
            stack = parent
            codec_stack = codecs
        post_build = None

        # Checksums
        try:
            for subcodec in self.subcodecs:
                if isinstance(subcodec, Checksum):
                    post_build = subcodec.post_build
                subcodec.io_build(stack, codec_stack, container)
        finally:
            # Always add the codec stack to the traceback
            if not self.embedded:
                codecs.push(codec_stack)
        if post_build:  # For use in checksums
            post_build(stack, codecs)

        if not self.embedded:
            parent.push(Value(self.name, stack, size=stack.sizeof()))

    def build(self, container: Container) -> ConstBitStream:
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
        parent = StackV()
        codecs = StackC()
        add_codec_to_traceback(self, codecs)

        container_ = container.copy()  # Don't modify the current Container
        try:
            self.io_build(parent, codecs, container_)
            io = parent.get_io()
            if len(io) % 8 != 0:
                raise SizeOfError(
                    parent,
                    codecs,
                    f"Built bits must be divisible by 8 (byte), {io!r} {io.len=}",
                )
            return io
        except CodecError:
            # CodecError - These error subtypes already have all the trace
            #              information required.
            raise
        except Exception as err:
            raise BuildError(parent, codecs, container_, repr(err)) from err

    def sizeof(
        self,
        parent: StackV | Container,
        codecs: StackC,
        io: ConstBitStream | None = None,
    ) -> int:
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
    def sizeof(self, parent: StackV | Container, codecs: StackC, io: IoType = None) -> int:
        return self._end

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        """IO parse method doesn't consume the IO stream, instead just *peeks* at the stream."""
        add_codec_to_traceback(self, codecs)

        try:
            start = io.read(self._start)
            end = io.read(self._end - self._start)
            # Swap the order of the start and end IO, then parse normally
            swapped_io = ConstBitStream(end + start)
        except ReadError as err:
            raise ParseError(
                parent,
                codecs,
                io,
                "Ran into an error reading ConstBitStream",
            ) from err
        super().io_parse(parent, codecs, swapped_io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        for codec in (*self._end_codec, *self._start_codec):
            codec.io_build(parent, codecs, container)


# ---------------- Error Handlers ----------------


class _Pass(Codec, metaclass=SingletonMeta):
    """
    Declarer that this Codec *shouldn't* error when it fails to map,
    this class will encode into a null terminated bitarray and
    decode into an empty container.
    """

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
    def rename(self, name: str) -> None:
        return

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)
        parent.push(Value(self.name, ConstBitStream(), 0))

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)
        parent.push(Value(self.name, ConstBitStream(), 0))


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
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        self.raise_error(parent, codecs, container=container)

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

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
        add_codec_to_traceback(self, codecs)

        _, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, ConstBitStream(length=size), size))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        size = self.sizeof(container, codecs)
        pattern = bin(self._pattern)
        binary = ConstBitStream(pattern)
        while len(binary) < size:
            binary += pattern
            if len(binary) > size:
                raise SizeOfError(
                    parent,
                    codecs,
                    f"Defined pattern {binary.bin!s} ({len(binary.bin)} bits) "
                    f"couldn't be repeated within {size} bits",
                )
        self._write_io(parent, codecs, container, self.name, binary)


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
        add_codec_to_traceback(self, codecs)

        value, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, value.uint, size))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name not in container:
            raise AttributeError(
                f"Name {self.name!r} wasn't found in the container"
            ) from BuildError(parent, codecs, container)
        self._write_io(parent, codecs, container, self.name, container[self.name])


class EnumBase(Enum_):
    """Basic override for the Enum object to change string representations."""

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
    Defines a BitsInt Codec which will encode into a Enum value, by default
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
        self._default = default

    @property
    def enum(self) -> EnumBase:
        return self._enum

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

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
            Error.raise_error(parent, codecs, key=enum_value)
        raise ParseError(
            parent,
            codecs,
            peek,
            f"Value {value} wasn't a valid enum, {self._enum!r}",
        )

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

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
                        Error.raise_error(parent, codecs, container=container)
                    # It's just an integer/value, this is a _Pass condition
                    container.set(self.name, enum, ignore_frozen=True)
        super().io_build(parent, codecs, container)


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

    def sizeof(
        self,
        parent: StackV | Container,
        codecs: StackC,
        io: ConstBitStream | None = None,
    ) -> int:
        return super().sizeof(parent, codecs, io)


class Flag(BitsInt):
    """
    Defines a boolean or a 'flag' which represents one bit.

    >>> "inbound" / Flag()
    """

    @override
    def __init__(self) -> None:
        super().__init__(size=1)

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        value, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, value.uint == 1, size))


class Const(Codec):
    """
    Asserts that the parsed/built value always equals the constant,
    and adds the value to the build if not presented.

    >>> "version" / Const(BitsInt(24), const=0x2)
    """

    @override
    def __init__(self, subcodec: Codec, /, const: int | str) -> None:
        super().__init__(subcodec)
        self.constant = const

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        self.subcodec.io_parse(parent, codecs, io)
        _sn, value = parent.get(self.name)
        if value.v_item != self.constant:
            raise ConstantError(
                parent, codecs, f"Was expecting the value {self.constant} but got {value}"
            )

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name in container and (value := container[self.name]) != self.constant:
            raise ConstantError(
                parent, codecs, f"Was expecting the value {self.constant} but got {value}"
            )
        if self.name not in container:
            container.set(self.name, self.constant)
        self.subcodec.io_build(parent, codecs, container)


class Default(Codec):
    """
    If a value wasn't provided in the build container, this Codec
    will add the value to the container set to it's default value.

    >>> "version" / Default(BitsInt(24), default=0x2)
    """

    @override
    def __init__(self, subcodec: Codec, /, default: Any) -> None:
        super().__init__(subcodec)
        self.default = default

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        self.subcodec.io_parse(parent, codecs, io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name not in container:
            container.set(self.name, self.default, ignore_frozen=True)
        self.subcodec.io_build(parent, codecs, container)


class Array(Codec):
    """
    Used to parse/build a collection of codecs, can be used with concretely
    defined counts, or via a lambda expression.

    *Count*
    >>>  "signs" / Array(BitsInt(4), count=8)

    *Functional*
    >>>  "signs" / Array(BitsInt(4), count=lambda packet: packet.array_count)
    """

    @override
    def __init__(self, subcodec: Codec, /, count: int | FunctType[int]) -> None:
        super().__init__(subcodec)
        self._count = count

    @override
    @property
    def size(self) -> int:
        return super().size * self._count  # type: ignore[operator]

    def _get_count(self, parent: StackV) -> int:
        if callable(self._count):
            return self._count(parent)
        return self._count

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        size = 0
        list_v: list[ValueType] = []
        for _ in range(0, self._get_count(parent)):
            stack_v = StackV()
            stack_v.attach_parent(parent)
            self.subcodec.io_parse(stack_v, StackC(), io)
            item = stack_v.pop()
            size += item.sizeof()
            list_v.append(item.v_item)
        parent.push(Value(self.name, list_v, size))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        values = container[self.name]
        if not isinstance(values, Collection):
            raise TypeError(
                f"{self.__class__.__name__} expected an iterable object, got {type(values)}"
            ) from BuildError(parent, codecs, container)
        count: int | ConstBitStream = self._get_count(parent)
        if isinstance(count, ConstBitStream):
            count = count.uint
        if len(values) != count:
            raise SizeOfError(
                parent,
                codecs,
                f"Expected collection to be size of exactly {count}, got {len(values)}",
            )
        raw = ConstBitStream()
        for value in values:
            stack_v = StackV()
            stack_v.attach_parent(parent)
            self.subcodec.io_build(stack_v, codecs, Container({self.name: value}))
            item = stack_v.pop()
            raw += item.bitstream
        parent.push(Value(self.name, raw, len(raw)))


# ---------------- Conditional Mappings ----------------


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
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def sizeof(self, parent: StackV | Container, codecs: StackC, io: IoType = None) -> int:
        if self.condition(parent):
            return self._then.sizeof(parent, codecs, io)
        return self._else.sizeof(parent, codecs, io)

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        if self.condition(parent):
            self._then.io_parse(parent, codecs, io)
        elif self._else is not Pass:
            self._else.io_parse(parent, codecs, io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        if self.condition(container):
            self._then.io_build(parent, codecs, container)
        else:
            self._else.io_build(parent, codecs, container)


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
            self._default.embedded = embedded
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
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        mapping_key: MKey | None = None
        subcodec: DefaultType | MValue | None = None
        try:
            mapping_key = self._funct(parent)
            subcodec = self._mapping[mapping_key]
        except (ValueError, KeyError):
            if self._default.__class__ is _Error:
                Error.raise_error(
                    parent, codecs, io=io, key=mapping_key, mapping=list(self._mapping)
                )
            if self._default.__class__ is _Pass:
                return
            subcodec = self._default
        subcodec.io_parse(parent, codecs, io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        mapping_key = self._funct(container)
        if mapping_key not in self._mapping:
            if self._default.__class__ is _Pass:
                return
            if self._default.__class__ is _Error:
                Error.raise_error(
                    parent,
                    codecs,
                    container=container,
                    key=mapping_key,
                    mapping=list(self._mapping),
                )
            self._default.io_build(parent, codecs, container)
            return
        subcodec = self._mapping[mapping_key]
        subcodec.io_build(parent, codecs, container)


class Optional(Codec):
    """
    Will attempt to parse/build this Codec, but upon failure, will ignore the
    errors and parse an empty value.

    >>> "options" / Optional(BitsInt(8))
    """

    @override
    @property
    def size(self) -> int:
        raise SizeError(f"Cannot calculate size of {self!r}")

    @override
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        try:
            size = self.subcodec.sizeof(parent, codecs)
        except (SizeOfError, SizeError):
            return

        if size <= 0:
            return
        with suppress(ParseError):
            self.subcodec.io_parse(parent, codecs, io)

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        try:
            size = self.subcodec.sizeof(container, codecs)
        except (SizeOfError, SizeError):
            return

        if size <= 0:
            return
        if self.name in container:
            self.subcodec.io_build(parent, codecs, container)


# ---------------- Greedy ----------------


class GreedyArray(Array):
    """
    Used to parse/build a collection of codecs, can be used with concretely
    defined counts, or via a lambda expression. Except with this one we can
    define an infinite or bounded amount of collections.

    If defined as infinite, it will consume the collection until there are no
    more to consume and add them to the stream.

    *Count until EOS*
    >>>  "signs" / GreedyArray(BitsInt(4))

    *Consume until count*
    >>>  "signs" / Array(BitsInt(4), max_count=4)

    *Functionally consume until count*
    >>>  "signs" / Array(BitsInt(4), max_count=lambda packet: packet.array_count)
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
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        values: list[Value] = []
        max_count = self._get_count(parent)
        i = 0
        if max_count > 0:
            i = max_count
        else:
            while io.pos < len(io):
                stack_v = StackV()
                stack_v.attach_parent(parent)
                self.subcodec.io_parse(stack_v, codecs, io)
                values.append(stack_v.pop())
                i += 1
                if max_count > 0 and i >= max_count:
                    break
        parent.push(Value(self.name, values, sum(item.sizeof() for item in values)))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        values = container[self.name]
        if not isinstance(values, Collection):
            raise TypeError(
                f"{self.__class__.__name__} expected an iterable object, got {type(values)}"
            ) from BuildError(parent, codecs, container)

        max_count = self._get_count(parent)
        if max_count > 0 and len(values) != self._count:
            raise ValueError(
                f"Expected collection to be size of exactly {max_count}, got {len(values)}",
            ) from BuildError(parent, codecs, container)
        raw = ConstBitStream()
        for value in values:
            stack_v = StackV()
            stack_v.attach_parent(parent)
            self.subcodec.io_build(stack_v, codecs, Container({self.name: value}))
            raw += stack_v.pop().bitstream
        parent.push(Value(self.name, raw, len(raw)))


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
    def sizeof(self, parent: StackV | Container, codecs: StackC, io: IoType = None) -> int:
        if callable(self._max_size):
            size = self._max_size(parent)
        elif self._max_size > 0:
            size = self._max_size
        # Requires IO
        elif io is None:
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
        add_codec_to_traceback(self, codecs)

        value, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, value, size))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name not in container:
            raise AttributeError(
                f"Name {self.name!r} wasn't found in the container",
            ) from BuildError(parent, codecs, container)
        value = container[self.name]
        if isinstance(value, bytes):
            value = ConstBitStream(value)
        self._write_io(parent, codecs, container, self.name, value)


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
    def io_parse(self, parent: StackV, codecs: StackC, io: ConstBitStream) -> None:
        add_codec_to_traceback(self, codecs)

        value, size = self._read_io(parent, codecs, io)
        parent.push(Value(self.name, value, size))

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        if self.name not in container:
            raise AttributeError(
                f"Name {self.name!r} wasn't found in the container",
            ) from BuildError(parent, codecs, container)
        value = container[self.name]
        if isinstance(value, bytes):
            container.set(self.name, ConstBitStream(value), ignore_frozen=True)
        self._write_io(parent, codecs, container, self.name, container[self.name])


# ---------------- Checksum ----------------


class Checksum(BitsInt):
    """
    Used to add a calculated checksum value upon building a Codec.
    This Codec will just parse as a BitsInt.

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
    def __init__(
        self, size: int, /, crc: Callable[[Buffer], int], field_names: set[str]
    ) -> None:
        self.size: int
        super().__init__(size)
        self.crc = crc
        self.field_names = field_names

    @override
    def io_build(self, parent: StackV, codecs: StackC, container: Container) -> None:
        add_codec_to_traceback(self, codecs)

        # The checksum field itself is set to zero during checksum calculation.
        self._write_io(parent, codecs, container, self.name, 0)

    def _post_build(self, parent: StackV, data: ConstBitStream) -> None:
        for item in parent:
            if isinstance(item.v_item, StackV):
                self._post_build(item.v_item, data)
                continue
            if item.name not in self.field_names:
                continue
            self.field_names.remove(item.name)
            data += item.bitstream

    def post_build(self, parent: StackV, codecs: StackC) -> None:
        data = ConstBitStream()
        self._post_build(parent, data)
        if len(data) % 8 != 0:
            raise SizeOfError(
                parent,
                codecs,
                f"{self.__class__.__name__} expected the contents "
                f"to be divisible by 8 (byte), got {len(data)}",
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
