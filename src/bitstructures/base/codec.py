from collections import UserDict
from collections.abc import Callable, Generator
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum as Enumerate
from typing import Any, NoReturn, Self, SupportsIndex, override

from bitstring import Bits, BitStream, ConstBitStream, CreationError, ReadError

from bitstructures.exceptions import (
    BuildError,
    ConstantError,
    CTypeError,
    InitError,
    LengthError,
    ParseError,
    RDivError,
    SizeError,
    FrozenError,
    TriggeredError,
)
from bitstructures.typing import DefaultType, FunctType

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


# ---------------- Containers ----------------


@dataclass(slots=True, frozen=True)
class Value[T: (str, int, float, ConstBitStream, "StackV")]:
    name: str
    v_item: T
    size: int = field(default=-1, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("Value's name is not of type str")
        if not isinstance(self.size, int):
            raise TypeError("Value's name is not of type int")

    def __str__(self) -> str:
        return f"V({self.name!r}: {self.v_item!s})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r}: {self.v_item!s}, size={self.size})"

    def pprint(self) -> str:
        return f"{self.name!r:<20} | size={self.size:<2} | {self.v_item!s}"

    def __hash__(self) -> int:
        return hash(self.v_item)

    def __eq__(self, value: object) -> bool:
        return self.v_item == value

    def __float__(self) -> float:
        return float(self.v_item)

    def __int__(self) -> int:
        return int(self.v_item)


class Container(UserDict[str, Value]):
    def __getattr__(self, attr: str) -> Value | None:
        return self.get(attr)


class Stack[T: (tuple[str, "Codec"], Value)]:
    def __init__(self) -> None:
        self.items: list[T] = []
        self._frozen: bool = False

    def set_frozen(self) -> None:
        self._frozen = True

    def _check_frozen(self) -> None:
        if self._frozen:
            raise FrozenError("Class is now frozen, cannot change attributes")

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.items})"

    def pop(self, index: SupportsIndex = -1) -> T:
        self._check_frozen()
        return self.items.pop(index)

    def set(self, index: SupportsIndex, value: T) -> None:
        self._check_frozen()
        self.items[index] = value

    def empty(self) -> bool:
        return not self.items

    def push(self, item: T) -> None:
        self._check_frozen()
        name = item.name
        # Don't allow duplicate names in the codec
        # unless it's a special privately defined field
        if not name.startswith("__") and name in self:            raise KeyError(f"Key name {name} already exists in the stack")
        self.items.append(item)

    def __contains__(self, key: str) -> bool:
        return key in {item.name for item in self.items}
    
    def __iter__(self) -> Generator[tuple[int, T], Any, None]:
        yield from enumerate(self.items)


class StackC(Stack["Codec"]):
    """For use in the Structs"""



class StackV(Stack[Value]):
    """For use in the parsing and building"""

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.to_container()})"

    def pprint(self) -> str:
        padding = f"\t{'-' * 40}\n"
        stack = ""
        size = 0

        for _sn, item in flatten(self):
            size += item.size
            size %= 8
            if size == 0:
                stack += padding
            stack += f"\t{item.pprint()}\n"
            # Divide the formats into segments of 8 bits
        return stack

    def get(self, key: str) -> tuple[int, Value]:
        for sn, item in self:
            if item.name == key:
                return sn, item
        raise KeyError

    def __getattr__(self, attr: str) -> Any:
        _sn, item = self.get(attr)
        return item.v_item

    def to_container(self) -> Container:
        container = Container()
        for _sn, item in flatten(self):
            if item.name.startswith("__"):
                continue
            container[item.name] = item.v_item
        return container

    def sizeof(self) -> int:
        return sum(item.size for item in self.items)

    def get_io(self):
        for _sn, item in self:
            if isinstance(item, StackV):
                yield from item.get_io()
            else:
                yield item.v_item

def flatten(parent: "StackV", *, stack: "StackV | None" = None) -> StackV:
    # RECURSIVE
    if stack is None:
        stack = StackV()
    # TODO: Handle duplicates and non-embedded stuctures
    for _sn, item in parent:
        if isinstance(item.v_item, StackV):
            _ = flatten(item.v_item, stack=stack)
        else:
            stack.push(item)
    return stack


# ---------------- Bits ----------------


class Codec:
    def __init__(self, subcodec: "Codec | None" = None) -> None:
        """
        Base class for codecs and is ideally subclassed for ALL codecs, contains
        all the logic needed for representing sizes, hashes,
        strings, naming, parsing and building.

        self.name:          Name of this codec, can use "name" / Codec to name this codec
        self._subcodec:     Codec to use when building, parsing or getting sizeof
        self._size:         Size in bits of this codec
        self._default:      Declarer on whether this Codec errors when no mapping is found
                            Only used in certain subclasses
        """
        self.name = self.__class__.__name__.lower()
        self.size: int | Callable[[Container], int] = subcodec.size if subcodec else -1
        self._subcodec = subcodec or self

    @property
    def subcodec(self) -> "Codec":
        return self._subcodec

    def __repr__(self) -> str:
        if isinstance(self.size, int):
            return f"{self.name} / {self.__class__.__name__}({self.size})"
        return f"{self.name} / {self.__class__.__name__}"

    def __hash__(self) -> int:
        return hash(self.name)

    def __rtruediv__(self, other: Any) -> Self:
        """
        Method which defines the behaviour of right side division.
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
            new = deepcopy(self)
            new.name = other
            if new.subcodec and new.subcodec.__class__ is not new:
                new.subcodec.name = other
            return new
        if isinstance(other, Codec):
            raise CTypeError(
                f"This {Codec.__name__.lower()} {self.__class__.__name__} doesn't support "
                f"rdiv on other {Codec.__name__} structures"
            )
        raise CTypeError(f"Unhandled type {type(other)} for division")

    def sizeof(self, parent: StackV, io: ConstBitStream = None) -> int:
        size: int = self.size(parent) if callable(self.size) else self.size
        if size < 0:  # If size is negative
            raise SizeError(f"Cannot perform a size method on {self.__class__.__name__}, {parent=}")
        return size

    @staticmethod
    def _parse_io(raw: bytes) -> ConstBitStream:
        """Converts raw bytes into a ConstBitStream to work with"""
        return ConstBitStream(raw)

    @staticmethod
    def _stack_to_bits(parent: StackV) -> ConstBitStream:
        io = BitStream()
        for io_ in parent.get_io():
            io += io_
        return ConstBitStream(io)

    def _read_io(self, io: ConstBitStream | Bits, parent: StackV) -> tuple[ConstBitStream, int]:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.

        - Must be used in the subclass
        """
        size = self.sizeof(parent, io)
        peek = io.peek(size)
        try:
            return ConstBitStream(io.read(size)), size
        except ReadError as err:
            raise ParseError(
                parent,
                self.subcodec,
                peek,
                "Ran into an error reading ConstBitStream",
            ) from err

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        """
        Not called externally, only via this module.

        Handles the implementation of the parsing from an IO ConstBitStream to a Container.
        - Must be modified in the subclasses
        """
        raise NotImplementedError(f"Method io_parse must be created via subclass {self.__class__}")

    def _write_io(
        self,
        name: str,
        parent: StackV,
        value: int | Enumerate,
    ) -> None:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.

        - Must be used in the subclass
        """
        if isinstance(value, Enumerate):
            value = value.value
        try:
            io = ConstBitStream(uint=value, length=self.sizeof(parent))
        except CreationError as err:
            raise BuildError(
                parent,
                self.subcodec,
                Container(value=value),
                "Ran into an error writing ConstBitStream",
            ) from err
        parent.push(Value(name, io, len(io)))

    def io_build(self, parent: StackV, container: Container) -> None:
        """
        Not called externally, only via this module.

        Handles the implementation of the build from Container to bytes.
        - Must be modified in the subclasses
        """
        raise NotImplementedError(f"Method io_build must be created via subclass {self.__class__}")

    # def parse(self, raw: bytes, readall: bool = True) -> StackV:
    #     """
    #     Called externally via users.

    #     Handles the core parsing of the raw bytes into a ConstBitStream object,
    #     then passes the IO stream into the io_parse for custom parsing.
    #     - Generally not modified in subclasses
    #     """
    #     io = self._parse_io(raw)
    #     stack = StackV()
    #     self.io_parse(io, stack)
    #     stack.set_frozen()
    #     if stack.empty():
    #         raise ParseError(stack, self, io, "Parsed stack is empty")
    #     if readall and io.bitpos != len(io):
    #         raise ParseError(stack, self, io, f"IO hasn't reached a terminator but {readall=}")
    #     return stack

    # def build(self, container: Container) -> bytes:
    #     """
    #     Called externally via users.

    #     Handles the core building of containers into raw bytes,
    #     then passes the IO stream into the io_build for custom building.
    #     - Generally not modified in subclasses
    #     """
    #     parent = StackV()
    #     io = BitStream()
    #     self.io_build(io, parent, container)
    #     if len(io) % 8 != 0:
    #         raise BuildError(
    #             parent, self.subcodec, container, "Built container must be divisible by 8 (1 byte)"
    #         )
    #     return bytes(io)


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
            self._subcodecs.push(arg)

    def __repr__(self) -> str:
        if isinstance(self.size, int):
            return f"{self.name} / {self.__class__.__name__}({self.size}, {self._embedded=})"
        return f"{self.name} / {self.__class__.__name__}({self._embedded=})"

    def __init__(self, *args: Any, embedded: bool = True) -> None:
        self._subcodecs = StackC()
        self._check_subcodec_type(*args)
        super().__init__()
        self.name = "__struct"
        self._embedded = embedded

    def parse(self, raw: bytes, readall: bool = True) -> StackV:
        """
        Called externally via users.

        Handles the core parsing of the raw bytes into a ConstBitStream object,
        then passes the IO stream into the io_parse for custom parsing.
        - Generally not modified in subclasses
        """
        io = self._parse_io(raw)
        stack = StackV()
        self.io_parse(io, stack)
        stack.set_frozen()
        if stack.empty():
            raise ParseError(stack, self, io, "Parsed stack is empty")
        if readall and io.bitpos != len(io):
            raise ParseError(stack, self, io, f"IO hasn't reached a terminator but {readall=}")
        if stack.sizeof() % 8 != 0:
            raise ParseError(
                stack, self, io, f"Parsed bits must be divisible by 8 (1 byte), {io!r}"
            )
        return stack

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        stack = parent if self._embedded else StackV()
        for sn, subcodec in self.subcodecs:
            subcodec.io_parse(io, stack)

        if not self._embedded:
            parent.push(Value(self.name, stack, size=stack.sizeof()))

    def io_build(self, parent: StackV, container: Container) -> None:
        container = container if self._embedded else container[self.name]
        stack = parent if self._embedded else StackV()
        for _sn, subcodec in self.subcodecs:
            subcodec.io_build(stack, container)

        if not self._embedded:
            parent.push(Value(self.name, stack, size=stack.sizeof()))

    def build(self, container: Container) -> bytes:
        # OVERRIDES BASE BUILD FUNCTION
        parent = StackV()
        for _sn, subcodec in self.subcodecs:
            if subcodec.name not in container and not isinstance(
                subcodec, Padding | Switch | Mapping | Struct
            ):
                raise BuildError(
                    parent,
                    subcodec,
                    container,
                    f"Missing key {subcodec.name} from the container {container!s}",
                )
            subcodec.io_build(parent, container)

        io = self._stack_to_bits(parent)
        if len(io) % 8 != 0:
            raise BuildError(
                parent, subcodec, container, f"Built bits must be divisible by 8 (1 byte), {io!r}"
            )
        return bytes(io)

    @property
    def subcodecs(self) -> StackC:
        return self._subcodecs


# ---------------- Error Handlers ----------------


class _Pass(Codec, metaclass=Singleton):
    """Declarer that this Codec *shouldn't* error when it fails to map"""

    def __init__(self) -> None:
        pass

    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    def io_build(self, parent: StackV, container: Container) -> None:
        pass

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        pass


Pass = _Pass()


class _Error(Codec, metaclass=Singleton):
    """Declarer that this Codec *should* error when it fails to map"""

    def __init__(self) -> None:
        pass

    def __rtruediv__(self, other: Any) -> Self:
        raise RDivError

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    def io_build(self, parent: StackV, container: Container) -> None:  # noqa: ARG002
        self.raise_error()

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:  # noqa: ARG002
        self.raise_error()

    def popitem(self) -> NoReturn:
        self.raise_error()

    @classmethod
    def raise_error(cls) -> NoReturn:
        raise TriggeredError("This error was triggered via a default set to Error")


Error = _Error()

# ---------------- Core Codecs ----------------


class RawBits(Codec):
    """
    Base class for some Bit Codecs, can be used externally.
    Defines a raw representation of the ConstBitStream,
    will return a ConstBitStream object when parsing and takes a ConstBitStream object on building.

    >>> raw_bits = "raw1" / RawBits(8)

    >>> raw_bits.build(
        Container(
            raw1=ConstBitStream("0b00010000")
        )
    )
    >>>> b"\x10"

    >>> raw_bits.parse(b"\x10")
    >>>> 0b00010000
    """

    def __init__(self, size: int) -> None:
        super().__init__()
        self.size = size

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        raise NotImplementedError(self.__class__.__name__)

    def io_build(self, parent: StackV, container: Container) -> None:
        raise NotImplementedError(self.__class__.__name__)


class Padding(Codec):
    """
    Used when we don't want any value to represent the allocated data,
    can be used as a *pad or fill* in a structure and will not be returned
    during building.

    >>> Struct(
        "int1" / BitInts(4, padding=0b0101),
        Padding(4)
    )
    """

    def __init__(self, size: int, pattern: int = 0b1) -> None:
        super().__init__()
        self.size = size
        self._padding = ConstBitStream(pattern)
        self.name = "__padding"

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        _, size = self._read_io(io, parent)
        parent.push(Value("__padding", None, size))

    def io_build(self, parent: StackV, container: Container) -> None:  # noqa: ARG002
        i = 0
        codec_size = self.sizeof(parent)
        while i < codec_size:
            size = len(self._padding)
            self._write_io(self.name, parent, self._padding.uint)
            i += size


class BitsInt(Codec):
    """
    Defines a integer representation from the ConstBitStream,
    will return an integer when parsing and takes ant int on building.

    >>> Struct(
        "int1" / BitInts(8),
    )
    """

    def __init__(self, size: int | FunctType) -> None:
        super().__init__()
        self.size = size

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        value, size = self._read_io(io, parent)
        parent.push(Value(self.name, value.uint, size))

    def io_build(self, parent: StackV, container: Container) -> None:
        if self.name not in container:
            raise BuildError(
                parent,
                self,
                container,
                f"Name {self.name} wasn't found in the container",
            )
        self._write_io(self.name, parent, container[self.name])


class Enum(BitsInt):
    def __init__(
        self,
        size: int | FunctType,
        *,
        default: DefaultType = Error,
        **kwargs: int | str,
    ) -> None:
        super().__init__(size)
        self._enum = Enumerate(self.name, kwargs)  # type: ignore[misc]
        self._default = default

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        peek = io.peek(self.sizeof(parent, io))
        super().io_parse(io, parent)

        sn, value = parent.get(self.name)
        enum_value = value.v_item
        if enum_value in self._enum:
            parent.set(sn, Value(value.name, self._enum(enum_value), value.size))
            return
        if enum_value in self._enum._value2member_map_:
            parent.set(sn, Value(value.name, self._enum[enum_value], value.size))
        if self._default.__class__ is _Pass:
            return
        raise ParseError(
            parent,
            self,
            peek,
            f"Value {value} wasn't a valid enum, {self._enum!r}",
        )

    def io_build(self, parent: StackV, container: Container) -> None:
        value = container[self.name]
        if value in self._enum:
            container[self.name] = self._enum(value)
            super().io_build(parent, container)
            return
        if value in self._enum._value2member_map_:
            container[self.name] = self._enum[value]
            super().io_build(parent, container)
            return
        if self._default.__class__ is _Pass:
            super().io_build(parent, container)
            return
        raise BuildError(
            parent,
            self,
            container,
            f"Failed to find the enum mapping for {parent.name} in {list(self._enum)}",
        )


class Flag(BitsInt):
    def __init__(self) -> None:
        super().__init__(size=1)


class Const(Codec):
    def __init__(self, subcodec: Codec, /, const: int | str) -> None:
        super().__init__(subcodec)
        self.constant = const

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        self._subcodec.io_parse(io, parent)
        _sn, value = parent.get(self.name)
        if value.v_item != self.constant:
            raise ConstantError(f"Was expecting the value {self.constant} but got {value}")

    def io_build(self, parent: StackV, container: Container) -> None:
        if self.name in container and (value := container[self.name]) != self.constant:
            raise ConstantError(f"Was expecting the value {self.constant} but got {value}")
        self._write_io(self.name, parent, self.constant)


class Default(Codec):
    def __init__(self, subcodec: Codec, /, default: Any) -> None:
        super().__init__(subcodec)
        self.default = default

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        self.subcodec.io_parse(io, parent)

    def io_build(self, parent: StackV, container: Container) -> None:
        # if self.name not in parent:
        #     parent[self.name] = self.default
        # super().io_build(io, parent, container)
        raise NotImplementedError(self.__class__.__name__)


class Peek(Codec):
    def __init__(self, subcodec: Codec, /, offset: int) -> None:
        super().__init__(subcodec)
        self._offset = offset

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        """This IO parse method doesn't consume the IO stream, we just *peek* at the stream"""
        try:
            peek = io.peek(self._offset)
        except ReadError as err:
            raise ParseError(
                parent,
                self.subcodec,
                peek,
                "Ran into an error reading ConstBitStream",
            ) from err
        return self._subcodec.io_parse(peek, parent)

    def io_build(self, parent: StackV, container: Container) -> None:
        pass


class Checksum(Codec):
    def __init__(self, subcodec: Codec, /, crc: FunctType) -> None:
        super().__init__(subcodec)
        self.crc = crc

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        return self._subcodec.io_parse(io, parent)

    def io_build(self, parent: StackV, container: Container) -> None:
        checksum = self.crc(parent)
        container[self.name] = checksum
        self._subcodec.io_build(parent, container)


# ---------------- Mappings ----------------


class Switch[MKey: Any, MValue: Codec](Codec):
    def __init__(
        self,
        funct: Callable[[Container], MKey],
        mapping: dict[MKey, MValue],
        *,
        default: DefaultType = Error,
    ) -> None:
        super().__init__()
        self.function = funct
        self.mapping = mapping
        for codec in self.mapping.values():
            codec.name = self.name
        self._default = default

    def __rtruediv__(self, other):
        for key, codec in self.mapping.items():
            self.mapping[key] = codec.__rtruediv__(other)
        return super().__rtruediv__(other)

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        try:
            mapping_key = self.function(parent)
            if isinstance(mapping_key, Enumerate):
                mapping_key = mapping_key.name
            subcodec = self.mapping[mapping_key]
        except (ValueError, KeyError):
            if self._default.__class__ is _Pass:
                return
            raise
        subcodec.io_parse(io, parent)

    def io_build(self, parent: StackV, container: Container) -> None:
        mapping_key = self.function(container)
        if isinstance(mapping_key, Enumerate):
            mapping_key = mapping_key.name
        if mapping_key not in self.mapping:
            if self._default.__class__ is _Pass:
                return
            raise BuildError(
                parent,
                self,
                container,
                f"Value {mapping_key} wasn't found in the mapping {self.mapping}",
            )

        subcodec = self.mapping[mapping_key]
        subcodec.io_build(parent, container)


class Mapping(Codec):
    def __init__(self, subcodec: Codec, mapping: dict[str, str | int]) -> None:
        super().__init__(subcodec)
        self.mapping = mapping

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        peek = io.peek(self.subcodec.sizeof(parent, io))
        self._subcodec.io_parse(io, parent)
        _sn, parent_value = parent.get(self._subcodec.name)
        for value in self.mapping.values():
            if parent_value.v_item == value:
                return
        raise ParseError(
            parent,
            self._subcodec,
            peek,
            f"Value {parent_value.v_item} wasn't found in the mapping {self.mapping}",
        )

    # def io_build(self, parent: StackV, container: Container) -> None:
    #     value = parent[self.name]
    #     if value not in self.mapping:
    #         raise BuildError(self, f"Value {value} wasn't found in the mapping {self.mapping}")
    #     self._subcodec.io_build(io, Container({self.subcodec.name: self.mapping[value]}))


# ---------------- Greedy ----------------


class Array(Codec):
    def __init__(self, subcodec: Codec, /, count: int | FunctType) -> None:
        super().__init__(subcodec)
        self._count = count

    def _get_count(self, parent: StackV) -> int:
        if callable(self._count):
            return self._count(parent)
        return self._count

    # def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
    #     count = self._get_count(parent)
    #     size = self.sizeof(parent, io) * count
    #     values = []
    #     i = 0
    #     while len(io) - io.pos > 0:
    #         if count != 0 and i >= count:
    #             break
    #         bits = ConstBitStream(io.read(self.subcodec.sizeof(parent, io)))
    #         self.subcodec.io_parse(bits, parent)
    #         values.append(value.value)
    #         i += 1
    #     return Container({self.name: Value(values, size)})

    # def io_build(self, parent: StackV, container: Container) -> None:
    #     count = self._get_count(parent)
    #     array = parent.pop(self._subcodec.name)
    #     if count != len(array.item):
    #         raise BuildError(
    #             self,
    #             f"Expected an array of len {count} got an array of len {len(array)}",
    #         )
    #     for value in array.item:
    #         container = parent
    #         container[self._subcodec.name] = value
    #         self._subcodec.io_build(io, container)


class GreedyArray(Codec):
    def __init__(self, subcodec: Codec, /, count: int | FunctType = 0) -> None:
        super().__init__(subcodec)
        self._count = count

    def _get_count(self, parent: StackV) -> int:
        if callable(self._count):
            return self._count(parent)
        return self._count

    # def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
    #     count = self._get_count(parent)
    #     size = self.sizeof(parent, io) * count
    #     values = []
    #     i = 0
    #     while len(io) - io.pos > 0:
    #         if count != 0 and i >= count:
    #             break
    #         bits = ConstBitStream(io.read(self.subcodec.sizeof(parent, io)))
    #         container = self.subcodec.io_parse(bits, parent)
    #         _name, value = container.popitem()
    #         values.append(value)
    #         i += 1
    #     return Container({self.name: Value(values, size)})

    # def io_build(self, parent: StackV, container: Container) -> None:
    #     count = self._get_count(parent)
    #     array = parent.pop(self._subcodec.name)
    #     if len(array) > count:
    #         raise BuildError(
    #             self,
    #             f"Expected an array of len 0 < x < {count} got an array of len {len(array)}",
    #         )
    #     for value in array:
    #         container = parent
    #         container[self._subcodec.name] = value
    #         self._subcodec.io_build(io, container)


class GreedyBits(Codec):
    def __init__(self, max_size: FunctType | int = 0) -> None:
        super().__init__()
        self._max_size: FunctType | int = max_size

    def sizeof(self, parent, io):
        if callable(self._max_size):
            size = self._max_size(parent)
        elif self._max_size == 0:
            size = len(io) - io.pos
        elif self._max_size < 0:
            size = len(io) - io.pos + self._max_size  # Offset
        else:
            size = self._max_size
        return size

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        value, size = self._read_io(io, parent)
        parent.push(Value(self.name, value, size))

    # def io_build(self, parent: StackV, container: Container) -> None:
    #     self._write_io(self.name, parent, container[self.name])


# ---------------- Statements ----------------


class Conditional(Codec):
    def __init__(
        self,
        condition: FunctType,
        then_: Codec,
        else_: Codec = Pass,
    ) -> None:
        super().__init__()
        self.condition = condition
        self.then_ = self.name / then_
        self.else_ = self.name / else_

    def __rtruediv__(self, other: Any) -> Self:
        new = super().__rtruediv__(other)
        # Give the sub-codecs the same name as this divisor
        new.then_ = new.name / new.then_
        new.else_ = new.name / new.else_
        return new

    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        if self.condition(parent):
            self.then_.io_parse(io, parent)
        elif self.else_ is not Pass:
            self.else_.io_parse(io, parent)

    # def io_build(self, parent: StackV, container: Container) -> None:
    #     if self.condition(parent):
    #         self.then_.io_build(io, parent, container)
    #     else:
    #         self.else_.io_build(io, parent, container)

    def sizeof(self, io: ConstBitStream, parent: StackV) -> int:
        if self.condition(parent):
            return self.then_.sizeof(parent, io)
        return self.else_.sizeof(parent, io)


class Optional(Codec):
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        if self.sizeof(parent, io) == 0:
            return
        with suppress(ParseError):
            self._subcodec.io_parse(io, parent)

    def io_build(self, parent: StackV, container: Container) -> None:
        if self.name in container:
            self._subcodec.io_build(parent, container)
