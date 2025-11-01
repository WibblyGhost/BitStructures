from collections import UserDict
from collections.abc import Collection, Generator
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NoReturn, Self, SupportsIndex, override

from bitstring import BitStream, ConstBitStream, CreationError, ReadError

from bitstructures.exceptions import (
    BuildError,
    CodecError,
    ConstantError,
    FrozenError,
    InitError,
    IoError,
    ParseError,
    SizeError,
    StackError,
    TriggeredError,
)
from bitstructures.typing import (
    ContainerType,
    DefaultType,
    ExpType,
    FunctType,
    IoType,
    ReadIoType,
    WriteIoType,
)

# ---------------- Wrappers ----------------


class Singleton(type):
    """
    METACLASS
    Defines a class that only ever needs to be initialised once,
    and is used globally without new classes being created.
    *This class must be the used as a metaclass when subclassing*

    - Not Thread Safe
    """

    _instances: dict["Singleton", type] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> type:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


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
    v_item: "str | int | EnumBase | ConstBitStream | StackV | list[Value]"
    size: int = field(default=0, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("Value's name is not of type str")
        if not isinstance(self.size, int):
            raise TypeError("Value's name is not of type int")

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
        return f"<{self.name!r}: {self.v_item!s}, size={self.size}>"

    def pprint(self) -> str:
        return f"{self.name!r:<30} | size={self.size:<2} | {self.v_item!s}"

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


class Container[T: ContainerType = ContainerType](Frozen, UserDict[str, T]):
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


class Stack[T: ("Codec", Value)](Frozen):
    def __init__(self) -> None:
        self._items: list[T] = []
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
            key_error.add_note(f"Value: {item!r}")
            key_error.add_note(f"Items: {self._items!r}")
            raise key_error

    def push(self, item: T) -> None:
        self._check_frozen()
        self._validate_item(item)
        self._items.append(item)

    def __contains__(self, key: str) -> bool:
        return key in {item.name for item in self._items}

    def __iter__(self) -> Generator[T]:
        yield from self._items

    def enumerate(self) -> Generator[tuple[int, T]]:
        yield from enumerate(self._items)


class StackC(Stack["Codec"]):
    """For use in the Structs"""


class StackV(Stack[Value]):
    """For use in the parsing and building"""

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.to_container()})"

    def get(self, key: str) -> tuple[int, Value]:
        for sn, item in self.enumerate():
            if item.name == key:
                return sn, item
        raise KeyError(f"Key name {key!r} doesn't exist in the container")

    def __getattr__(self, attr: str) -> Any:
        _sn, item = self.get(attr)
        return item.v_item

    def sizeof(self) -> int:
        return sum(item.size for item in self._items)

    def to_container(self) -> Container:
        # RECURSIVE
        container = Container()
        for item in self:
            if isinstance(item.v_item, StackV):
                container.set(item.name, item.v_item.to_container(), ignore_frozen=True)
            elif isinstance(item.v_item, list):
                array = []
                for i in item.v_item:
                    # TODO: Handle structs inside the arrays
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
                stack += padding.format(t=">" * depth, v=f"{item.name} {item.size}")
                stack += item.v_item.pprint(depth=depth + 1)
                stack += padding.format(t="<" * depth, v="")
            else:
                stack += f"\t{item.pprint()}\n"
            size += item.size
        return stack

    def get_io(self) -> ConstBitStream:
        # RECURSIVE
        io = BitStream()
        for item in self:
            if isinstance(item.v_item, StackV):
                io += item.v_item.get_io()
            else:
                io += ConstBitStream(item.bitstream)
        return ConstBitStream(io)


# ---------------- Bits ----------------


class Codec:
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
        # For use in structs
        self._subcodec_stack: StackC = StackC()
        self.initialized: bool = False
        self.name: str = ""
        self.size: int | FunctType[int] = subcodec.size if subcodec else 0

    @property
    def subcodecs(self) -> StackC:
        return self._subcodec_stack

    def pprint(self, *, depth: int = 1) -> str:
        # RECURSIVE
        padding = "\t{t}{v:-^38}{t}\n"
        stack = f"\t{self!s}\n"
        if self._subcodec:
            stack += self._subcodec.pprint(depth=depth + 1)
        for subcodec in self.subcodecs:
            if isinstance(subcodec, Struct):
                stack += padding.format(t=">" * depth, v=f"{subcodec.name}")
                stack += subcodec.pprint(depth=depth + 1)
                stack += padding.format(t="<" * depth, v="")
            else:
                stack += subcodec.pprint(depth=depth + 1)
        return stack

    def _check_initialized(self) -> None:
        """
        Checks if the codec har been given a description/name
        Structs/Padding do not need names so ignore this.
        """
        if self.initialized and self.name:
            return
        raise InitError(f"{self!s} needs to be initialized with a '|' or '/'")

    @property
    def subcodec(self) -> "Codec":
        return self._subcodec or self

    def __repr__(self) -> str:
        if isinstance(self.size, int):
            return f"{self.name!r} / {self.__class__.__name__}({self.size})"
        return f"{self.name!r} / {self.__class__.__name__}"

    def __hash__(self) -> int:
        return hash(self.name)

    def rename(self, name: str) -> None:
        self.name = name
        self.initialized = True
        if self._subcodec:  # Uses private subcodec, as this can be None
            self._subcodec.rename(name)

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

    def sizeof(self, parent: StackV, io: IoType = None) -> int:  # noqa: ARG002
        self._check_initialized()
        size: int = self.size(parent) if callable(self.size) else self.size
        if size < 0:  # If size is negative
            raise SizeError(f"Cannot perform a size method on {self.__class__.__name__}, {parent=}")
        return size

    def _parse_io(self, raw: bytes) -> ConstBitStream:
        """Converts raw bytes into a ConstBitStream to work with"""
        self._check_initialized()
        return ConstBitStream(raw)

    def _read_io(self, parent: StackV, io: ReadIoType) -> tuple[ConstBitStream, int]:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.

        - Must be used in the subclass
        """
        peek: ConstBitStream | None = None
        self._check_initialized()
        size = self.sizeof(parent, io)
        try:
            peek = io.peek(size)
            return ConstBitStream(io.read(size)), size
        except ReadError as err:
            raise ParseError(
                parent,
                self.subcodec,
                peek or io,
                "Ran into an error reading ConstBitStream",
            ) from err

    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        """
        Not called externally, only via this module.

        Handles the implementation of the parsing from an IO ConstBitStream to a Container.
        - Must be modified in the subclasses
        """
        raise NotImplementedError(
            f"Method io_parse must be created via subclass {self.__class__.__name__}"
        )

    def _write_io(
        self,
        parent: StackV,
        name: str,
        value: WriteIoType,
    ) -> None:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.

        - Must be used in the subclass
        """
        if not isinstance(value, int | EnumBase | ConstBitStream):
            raise TypeError(
                f"Cannot build a value of type {type(value)}, "
                f"must be one of int | EnumBase | ConstBitStream"
            )

        if isinstance(value, EnumBase):
            value = value.value

        if isinstance(value, ConstBitStream):
            length = self.sizeof(parent, value)
        else:
            length = self.sizeof(parent, None)

        if length == 0:
            return
        if isinstance(value, ConstBitStream):
            if length > value.length:
                raise BuildError(
                    parent,
                    self,
                    Container({"value": value}),
                    "Ran into an error writing ConstBitStream",
                ) from SizeError(
                    f"Cannot pack a BitStream of length {value.length} into {length} bits"
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
                    self,
                    Container({"value": value}),
                    "Ran into an error writing ConstBitStream",
                ) from err

    def io_build(self, parent: StackV, container: Container) -> None:
        """
        Not called externally, only via this module.

        Handles the implementation of the build from Container to bytes.
        - Must be modified in the subclasses
        """
        raise NotImplementedError(f"Method io_build must be created via subclass {self.__class__}")


# ---------------- Structures ----------------


class Struct(Codec):
    """
    Parent codec which is used to group Codecs together, this class must
    handle recursive Codecs when parsing and building.

    >>> codec = Struct(
        "int1" / BitInts(4),
        "int2" / BitInts(4),
    )
    """

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
        if isinstance(self.size, int):
            return f"{self.name} / {self.__class__.__name__}({self.size}, {self.embedded=})"
        return f"{self.name} / {self.__class__.__name__}({self.embedded=})"

    @override
    def __init__(self, *args: Any, embedded: bool = True) -> None:
        super().__init__()
        self._check_subcodec_type(*args)
        self.name = "__struct"
        self.embedded = embedded

    @override
    def _check_initialized(self) -> None:
        """
        Checks if the codec har been given a description/name
        Structs/Padding do not need names so ignore this.
        """
        return

    def parse(self, raw: bytes, *, readall: bool = True) -> StackV:
        """
        Called externally via users.

        Handles the core parsing of the raw bytes into a ConstBitStream object,
        then passes the IO stream into the io_parse for custom parsing.
        - Generally not modified in subclasses
        """
        if not isinstance(raw, bytes):
            raise TypeError(
                f"Parse only accepts a argument with type {bytes.__name__}, got {type(raw)}"
            )
        parent = StackV()
        try:
            io = self._parse_io(raw)
            self.io_parse(parent, io)
            parent.set_frozen()
            if parent.empty():
                raise StackError(parent, self, io, "Parsed stack is empty")
            if readall and io.bitpos != len(io):
                raise IoError(parent, self, io, f"IO hasn't reached a terminator but {readall=}")
            if parent.sizeof() % 8 != 0:
                raise SizeError(
                    f"Parsed bits must be divisible by 8 (1 byte), {io!r} {io.len=}",
                )
            return parent
        except Exception as err:  # noqa: BLE001
            if not issubclass(err.__class__, CodecError):
                err = CodecError(err)
            errors: list[Exception] = [err]
            if not isinstance(err, ParseError):
                errors.append(ParseError(parent, self, io, repr(err), raw=raw))
            raise ExceptionGroup(
                f"{self!s}: Unknown parse error occured",
                errors,
            )

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        stack = parent if self.embedded else StackV()
        for subcodec in self.subcodecs:
            subcodec.io_parse(stack, io)

        if not self.embedded:
            parent.push(Value(self.name, stack, size=stack.sizeof()))

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        container = container if self.embedded else container[self.name]
        stack = parent if self.embedded else StackV()
        post_build = None
        for subcodec in self.subcodecs:
            if isinstance(subcodec, Checksum):
                post_build = subcodec.post_build
            subcodec.io_build(stack, container)
        if post_build:  # For use in checksums
            post_build(stack)

        if not self.embedded:
            parent.push(Value(self.name, stack, size=stack.sizeof()))

    def build(self, container: Container) -> bytes:
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
        container_ = container.copy()  # Don't modify the current Container
        try:
            self.io_build(parent, container_)
            io = parent.get_io()
            if len(io) % 8 != 0:
                raise SizeError(
                    f"Built bits must be divisible by 8 (1 byte), {io!r} {io.len=}",
                )
            return bytes(io)
        except Exception as err:  # noqa: BLE001
            if not issubclass(err.__class__, CodecError):
                err = CodecError(err)
            errors: list[Exception] = [err]
            if not isinstance(err, BuildError):
                errors.append(BuildError(parent, self, container_, repr(err)))
            raise ExceptionGroup(
                f"{self!s}: Unknown build error occured",
                errors,
            )


# ---------------- Error Handlers ----------------


class _Pass(Codec, metaclass=Singleton):
    """Declarer that this Codec *shouldn't* error when it fails to map"""

    @override
    def __init__(self) -> None:
        self.name = "__pass"

    @override
    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        pass

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        pass


Pass = _Pass()


class _Error(Codec, metaclass=Singleton):
    """Declarer that this Codec *should* error when it fails to map"""

    @override
    def __init__(self) -> None:
        self.name = "__error"

    @override
    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        self.raise_error()

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        self.raise_error()

    @classmethod
    def raise_error(cls) -> NoReturn:
        raise TriggeredError("This error was triggered via a default set to Error")


Error = _Error()
NotImplementedCodec = Error

# ---------------- Core Codecs ----------------


class RawBits(Codec):
    """
    Base class for some Bit Codecs, can be used externally.
    Defines a raw representation of the ConstBitStream,
    will return a ConstBitStream object when parsing and takes a ConstBitStream object on building.

    >>> raw_bits = "raw1" / RawBits(8)
    """

    @override
    def __init__(self, size: int) -> None:
        super().__init__()
        self.size = size

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        raise NotImplementedError(self.__class__.__name__)

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        raise NotImplementedError(self.__class__.__name__)


class Padding(Codec):
    """
    Used when we don't want any value to represent the allocated data,
    can be used as a *pad or fill* in a structure and will not be returned
    during building.

    >>> Padding(4, padding=0b0101)
    """

    @override
    def __init__(self, size: int, /, pattern: int = 0b1) -> None:
        super().__init__()
        self.name = "__padding"
        self.size = size
        self._pattern = pattern

    @override
    def _check_initialized(self) -> None:
        """
        Checks if the codec har been given a description/name
        Structs/Padding do not need names so ignore this.
        """
        return

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        _, size = self._read_io(parent, io)
        parent.push(Value(self.name, ConstBitStream(length=size), size))

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        size = self.sizeof(parent)
        binary = ConstBitStream(bin(self._pattern))
        while len(binary) < size:
            binary += binary
            if len(binary) > size:
                raise SizeError(
                    f"Defined pattern {binary.bin:b} couldn't be repeated to fit size {size}"
                )
        self._write_io(parent, self.name, binary)


class BitsInt(Codec):
    """
    Defines a integer representation from the ConstBitStream,
    will return an integer when parsing and takes ant int on building.

    >>> "int1" / BitInts(8)
    """

    @override
    def __init__(self, size: int | FunctType[int]) -> None:
        super().__init__()
        self.size = size

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        value, size = self._read_io(parent, io)
        parent.push(Value(self.name, value.uint, size))

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        if self.name not in container:
            raise BuildError(
                parent,
                self,
                container,
                f"Name {self.name} wasn't found in the container",
            )
        self._write_io(parent, self.name, container[self.name])


class EnumBase(Enum):
    """Basic override for the Enum object to change string representations"""

    @override
    def __str__(self) -> str:
        return self.name

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


class Enumerate(BitsInt):
    """
    >>> "protocol" / Enumerate(
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
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        peek = io.peek(self.sizeof(parent, io))
        super().io_parse(parent, io)

        sn, value = parent.get(self.name)
        enum_value = value.v_item
        if enum_value in self.enum:  # type: ignore[operator]
            parent.set(sn, Value(value.name, self.enum(enum_value), value.size))  # type: ignore[operator]
            return
        if enum_value in self.enum._value2member_map_:  # type: ignore[attr-defined]
            parent.set(sn, Value(value.name, self.enum[enum_value], value.size))  # type: ignore[index]
        if self._default.__class__ is _Pass:
            return
        if self._default.__class__ is _Error:
            Error.raise_error()
        raise ParseError(
            parent,
            self,
            peek,
            f"Value {value} wasn't a valid enum, {self._enum!r}",
        )

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
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
                        Error.raise_error()
                    # It's just an integer/value, this is a _Pass condition
                    container.set(self.name, enum, ignore_frozen=True)
        super().io_build(parent, container)


class Flag(BitsInt):
    """
    >>> "inbound" / Flag()
    """

    @override
    def __init__(self) -> None:
        super().__init__(size=1)

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        value, size = self._read_io(parent, io)
        parent.push(Value(self.name, value.uint == 1, size))


class Const(Codec):
    """
    >>> "version" / Const(BitsInt(24), const=0x2)
    """

    @override
    def __init__(self, subcodec: Codec, /, const: int | str) -> None:
        super().__init__(subcodec)
        self.constant = const

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        self.subcodec.io_parse(parent, io)
        _sn, value = parent.get(self.name)
        if value.v_item != self.constant:
            raise ConstantError(f"Was expecting the value {self.constant} but got {value}")

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        if self.name in container and (value := container[self.name]) != self.constant:
            raise ConstantError(f"Was expecting the value {self.constant} but got {value}")
        self.subcodec.io_build(parent, container)


class Default(Codec):
    """
    >>> "version" / Default(BitsInt(24), default=0x2)
    """

    @override
    def __init__(self, subcodec: Codec, /, default: Any) -> None:
        super().__init__(subcodec)
        self.default = default

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        self.subcodec.io_parse(parent, io)

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        if self.name not in container:
            container.set(self.name, self.default, ignore_frozen=True)
        super().io_build(parent, container)


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
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        values: list[Value] = []
        for _ in range(0, self._get_count(parent)):
            stack = StackV()
            self.subcodec.io_parse(stack, io)
            values.append(stack.pop())
        parent.push(Value(self.name, values, sum(item.size for item in values)))

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        values = container[self.name]
        if not isinstance(values, Collection):
            raise TypeError(
                f"{self.__class__.__name__} expected an iterable object, got {type(values)}"
            )
        count = self._get_count(parent)
        if len(values) != count:
            raise ValueError(
                f"Expected collection to be size of exactly {count}, got {len(values)}"
            )
        raw = BitStream()
        for value in values:
            stack = StackV()
            self.subcodec.io_build(stack, Container({self.name: value}))
            raw += stack.pop().bitstream
        parent.push(Value(self.name, raw, len(raw)))


class Peek(Codec):
    """
    Allows you to look ahead of the current position and
    >>> Struct(
        # Move the stream ahead 8 bits then parse the id, then revert
        "id" / Peek(MANUFACTURER_ID, offset=8),
        "opcode" / Switch(
            lambda packet: packet.id,
            ...
        ),
        Padding(8),  # id (Handled via the peek already)
    )
    """

    @override
    def __init__(self, subcodec: Codec, /, offset: int) -> None:
        super().__init__(subcodec)
        self.size = 0
        self._offset = offset

    @override
    def sizeof(self, parent: StackV, io: IoType = None) -> int:
        return 0

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        """This IO parse method doesn't consume the IO stream, we just *peek* at the stream"""
        try:
            codec_size = self.subcodec.sizeof(parent, io)
            peek = io[self._offset : self._offset + codec_size]
        except ReadError as err:
            raise ParseError(
                parent,
                self.subcodec,
                io,
                "Ran into an error reading ConstBitStream",
            ) from err
        self.subcodec.io_parse(parent, peek)
        sn, value = parent.get(self.subcodec.name)
        parent.set(sn, Value(value.name, value.v_item, 0))

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        pass


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
    def io_build(self, parent: StackV, container: Container) -> None:
        # The checksum field itself is set to zero during checksum calculation.
        self._write_io(parent, self.name, 0)

    def _post_build(self, parent: StackV, data: BitStream) -> None:
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

    def post_build(self, parent: StackV) -> None:
        data = BitStream()
        self._post_build(parent, data)
        if len(data) % 8 != 0:
            raise SizeError(
                f"{self.__class__.__name__} expected the contents "
                f"to be divisible by 8 (1 byte), got {len(data)}"
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


class Switch[MKey: Any, MValue: Codec](Codec):
    """
    >>> "header" / Switch[str, Codec](
        lambda packet: packet.protocol,
        {"UDP": UDP_HEADER, "TCP": TCP_HEADER}
    )
    """

    @override
    def __init__(
        self,
        funct: FunctType[Any],
        mapping: dict[MKey, MValue],
        *,
        default: DefaultType | MValue = Error,
        embedded: bool | None = None,
    ) -> None:
        super().__init__()
        self.function = funct
        self.mapping = mapping
        for codec in self.mapping.values():
            codec.name = self.name
            if embedded is not None and isinstance(codec, Struct):
                codec.embedded = embedded
        self._default = default
        self.embedded = embedded

    @override
    def __repr__(self) -> str:
        if isinstance(self.size, int):
            return f"{self.name!r} / {self.__class__.__name__}({self.size}, {self.embedded=})"
        return f"{self.name!r} / {self.__class__.__name__}"

    @override
    def __rtruediv__(self, other: Any) -> Self:
        for key, codec in self.mapping.items():
            self.mapping[key] = other / codec
        return super().__rtruediv__(other)

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        mapping_key: MKey
        subcodec: DefaultType | MValue
        try:
            mapping_key = self.function(parent)
            subcodec = self.mapping[mapping_key]
        except (ValueError, KeyError):
            if self._default.__class__ is _Error:
                Error.raise_error()
            if self._default.__class__ is _Pass:
                return
            subcodec = self._default
        subcodec.io_parse(parent, io)

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        mapping_key = self.function(container)
        if mapping_key not in self.mapping:
            if self._default.__class__ is _Pass:
                return
            if self._default.__class__ is _Error:
                Error.raise_error()
            raise BuildError(
                parent,
                self,
                container,
                f"Value {mapping_key} wasn't found in the mapping {self.mapping}",
            )

        subcodec = self.mapping[mapping_key]
        subcodec.io_build(parent, container)


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
            raise ValueError("Count cannot be 0")
        super().__init__(subcodec, max_count)

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        values: list[Value] = []
        max_count = self._get_count(parent)
        i = 0
        if max_count > 0:
            i = max_count
        else:
            while io.pos < len(io):
                stack = StackV()
                self.subcodec.io_parse(stack, io)
                values.append(stack.pop())
                i += 1
                if max_count > 0 and i >= max_count:
                    break
        parent.push(Value(self.name, values, sum(item.size for item in values)))

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        values = container[self.name]
        if not isinstance(values, Collection):
            raise TypeError(
                f"{self.__class__.__name__} expected an iterable object, got {type(values)}"
            )

        max_count = self._get_count(parent)
        if max_count > 0 and len(values) != self._count:
            raise ValueError(
                f"Expected collection to be size of exactly {max_count}, got {len(values)}"
            )
        raw = BitStream()
        for value in values:
            stack = StackV()
            self.subcodec.io_build(stack, Container({self.name: value}))
            raw += stack.pop().bitstream
        parent.push(Value(self.name, raw, len(raw)))


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

    @override
    def sizeof(self, parent: StackV, io: IoType = None) -> int:
        if callable(self._max_size):
            size = self._max_size(parent)
        elif self._max_size > 0:
            size = self._max_size
        # Requires IO
        elif io is None:
            raise ValueError(f"Cannot get size of a {self.__class__.__name__} without an IO stream")
        elif self._max_size == 0:
            size = len(io) - io.pos
        else:
            size = len(io) - io.pos + self._max_size  # Offset
        return size

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        value, size = self._read_io(parent, io)
        parent.push(Value(self.name, value, size))

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        if self.name not in container:
            raise BuildError(
                parent,
                self,
                container,
                f"Name {self.name} wasn't found in the container",
            )
        value = container[self.name]
        if isinstance(value, bytes):
            container.set(self.name, ConstBitStream(value), ignore_frozen=True)
        self._write_io(parent, self.name, container[self.name])


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
        embedded: bool | None = None,
    ) -> None:
        super().__init__()
        self.condition = condition
        if embedded is not None:
            if isinstance(then_, Struct):
                then_.embedded = embedded
            if isinstance(else_, Struct):
                else_.embedded = embedded
        self.embedded = embedded
        self.then_ = self.name / then_
        self.else_ = self.name / else_

    @override
    def __repr__(self) -> str:
        if isinstance(self.size, int):
            return f"{self.name!r} / {self.__class__.__name__}({self.size}, {self.embedded=})"
        return f"{self.name!r} / {self.__class__.__name__}"

    @override
    def __rtruediv__(self, other: Any) -> Self:
        new = super().__rtruediv__(other)
        # Give the sub-codecs the same name as this divisor
        new.then_ = new.name / new.then_
        new.else_ = new.name / new.else_
        return new

    @override
    def sizeof(self, parent: StackV, io: IoType = None) -> int:
        if self.condition(parent):
            return self.then_.sizeof(parent, io)
        return self.else_.sizeof(parent, io)

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        if self.condition(parent):
            self.then_.io_parse(parent, io)
        elif self.else_ is not Pass:
            self.else_.io_parse(parent, io)

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        if self.condition(container):
            self.then_.io_build(parent, container)
        else:
            self.else_.io_build(parent, container)


class Optional(Codec):
    """
    >>> "options" / Optional(BitsInt(8))
    """

    @override
    def io_parse(self, parent: StackV, io: ConstBitStream) -> None:
        if self.sizeof(parent, io) == 0:
            return
        with suppress(ParseError):
            self.subcodec.io_parse(parent, io)

    @override
    def io_build(self, parent: StackV, container: Container) -> None:
        if self.name in container:
            self.subcodec.io_build(parent, container)


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
