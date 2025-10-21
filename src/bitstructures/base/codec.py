from collections import UserDict
from collections.abc import Callable
from copy import deepcopy
from enum import Enum as Enumerate
from typing import Any, NoReturn, Self

from bitstring import Bits, BitStream, ConstBitStream, CreationError, ReadError

from bitstructures.exceptions import (
    BuildError,
    CodecError,
    ConstantError,
    CTypeError,
    InitError,
    LengthError,
    ParseError,
    RDivError,
    SizeError,
    TriggeredError,
)
from bitstructures.typing import CodecType, DefaultType, LambdaType, ParseReturn

# ---------------- Wrappers ----------------

# def singleton[T: Callable[..., Any]](class_: T) -> T:
#     """Defines a class that only ever needs to be initialised once"""
#     return class_()


class Singleton:
    """
    Defines a class that only ever needs to be initialised once
    *This class must be the first argument when subclassing*
    """

    instance = None

    def __new__(class_, *args, **kwargs):
        if not isinstance(class_.instance, class_):
            class_.instance = object.__new__(class_, *args, **kwargs)
        return class_.instance


# ---------------- Containers ----------------


class Container(UserDict):
    def __getattr__(self, attr: str) -> Any:
        return self.get(attr)


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
        self.name: str = self.__class__.__name__.lower()
        self._subcodec: Codec = subcodec or self
        self._size: int | LambdaType
        if subcodec.__class__ is self:  # Prevent recursion
            self._size = -1
        else:
            self._size = len(self._subcodec)
        self._default: DefaultType = Error

    @property
    def subcodec(self) -> "Codec":
        return self._subcodec

    def __repr__(self) -> str:
        return f"{self.name} / {self.__class__.__name__}({len(self)})"

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

    def __len__(self) -> int:
        if callable(self._size):
            raise SizeError(
                f"Cannot perform a size method on {self.__class__.__name__}, using a callable size"
            )
        if self._size < 0:  # If size is negative
            raise SizeError(f"Cannot perform a size method on {self.__class__.__name__}")
        return self._size

    def sizeof(self) -> int:
        if self._size == 0:
            raise SizeError(f"Cannot determine size of a {self.__class__.__name__}")
        if self._size < 0:  # If size is negative
            raise SizeError(f"Cannot perform a size method on {self.__class__.__name__}")
        return len(self)

    @staticmethod
    def _parse_io(raw: bytes) -> ConstBitStream:
        """Converts raw bytes into a ConstBitStream to work with"""
        return ConstBitStream(raw)

    def _read_io(self, io: ConstBitStream | Bits, parent: Container, size: int) -> ConstBitStream:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.

        - Must be used in the subclass
        """
        peek = io.peek(size)
        try:
            return ConstBitStream(io.read(size))
        except ReadError as err:
            raise ParseError(
                parent,
                self.subcodec,
                peek,
                "Ran into an error reading ConstBitStream",
            ) from err

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        """
        Not called externally, only via this module.

        Handles the implementation of the parsing from an IO ConstBitStream to a Container.
        - Must be modified in the subclasses
        """
        raise NotImplementedError(f"Method io_parse must be created via subclass {self.__class__}")

    def _write_io(self, io: ConstBitStream, value: int, size: int) -> None:
        """
        Handles the reading of the ConstBitStream's IO, raises a parsing error
        if it failed to read.

        - Must be used in the subclass
        """
        try:
            io += ConstBitStream(uint=value, length=size)
        except CreationError as err:
            raise BuildError(
                self.subcodec,
                "Ran into an error reading ConstBitStream",
            ) from err

    def io_build(self, io: BitStream, parent: Container) -> None:
        """
        Not called externally, only via this module.

        Handles the implementation of the build from Container to bytes.
        - Must be modified in the subclasses
        """
        raise NotImplementedError(f"Method io_build must be created via subclass {self.__class__}")

    def parse(self, raw: bytes, readall: bool = True) -> ParseReturn:
        """
        Called externally via users.

        Handles the core parsing of the raw bytes into a ConstBitStream object,
        then passes the IO stream into the io_parse for custom parsing.
        - Generally not modified in subclasses
        """
        io = self._parse_io(raw)
        container = self.io_parse(io, Container())
        if container.__class__ is _Pass or container.__class__ is _Error:
            raise CodecError
        if readall and io.bitpos != len(io):
            raise ParseError(container, self, io, f"IO hasn't reached a terminator but {readall=}")
        return container

    def build(self, container: Container) -> bytes:
        """
        Called externally via users.

        Handles the core building of containers into raw bytes,
        then passes the IO stream into the io_build for custom building.
        - Generally not modified in subclasses
        """
        io = BitStream()
        self.io_build(io, container.copy())
        if len(io) % 8 != 0:
            raise BuildError(self.subcodec, "Built container must be divisible by 8 (1 byte)")
        return bytes(io)


# ---------------- Error Handlers ----------------


class _Pass(Singleton, Codec):
    """Declarer that this Codec *shouldn't* error when it fails to map"""

    def __init__(self) -> None:
        pass

    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    def io_build(self, io: BitStream, parent: Container) -> None:
        pass

    def io_parse(self, io: ConstBitStream, parent: Container) -> Self:  # noqa: ARG002
        return self


Pass = _Pass()


class _Error(Singleton, Codec):
    """Declarer that this Codec *should* error when it fails to map"""

    def __init__(self) -> None:
        pass

    def __rtruediv__(self, other: Any) -> Self:
        raise RDivError

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    def io_build(self, io: BitStream, parent: Container) -> None:  # noqa: ARG002
        self.raise_error()

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:  # noqa: ARG002
        self.raise_error()

    @classmethod
    def raise_error(cls) -> NoReturn:
        raise TriggeredError("This error was triggered via a default set to Error")


Error = _Error()

# ---------------- Core Codecs ----------------


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
            if arg.__class__ is Struct:
                self.subcodecs.update(
                    {subcodec.name: subcodec for subcodec in arg.subcodecs.values()}
                )
            else:
                self.subcodecs[arg.name] = arg

    def __init__(self, *args: Any, description: str = "") -> None:
        self._subcodecs: dict[str, Codec] = {}
        self._check_subcodec_type(*args)
        self._size = sum(len(subcodec) for subcodec in self.subcodecs.values())
        super().__init__()
        self.__rtruediv__(description)

    def io_parse(self, io: ConstBitStream, parent: Container) -> Container:
        container = parent or Container()
        for subcodec in self.subcodecs.values():
            cont = subcodec.io_parse(io, container)
            if cont.__class__ is _Pass:
                continue
            if cont.__class__ is _Error:
                Error.raise_error()
            container.update(cont)
        return container

    def io_build(self, io: BitStream, parent: Container) -> None:
        for subcodec in self.subcodecs.values():
            subcodec.io_build(io, parent)

    def build(self, container: Container) -> bytes:
        # OVERRIDES BASE BUILD FUNCTION
        container = container.copy()
        io = BitStream()
        for subcodec in self.subcodecs.values():
            if isinstance(subcodec, (Padding, Switch | Mapping)):
                subcodec.io_build(io, container)
            else:
                if subcodec.name not in container:
                    raise BuildError(
                        subcodec,
                        f"Missing key {subcodec.name} from the container {container!s}",
                    )
                subcodec.io_build(io, container)
        if len(io) % 8 != 0:
            raise BuildError(subcodec, "Built container must be divisible by 8 (1 byte)")
        return bytes(io)

    @property
    def subcodecs(self) -> dict[str, Codec]:
        return self._subcodecs


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
        self._size = size
        super().__init__()


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
        self._size = size
        super().__init__()
        self._padding = ConstBitStream(pattern)

    def io_parse(self, io: ConstBitStream, parent: Container) -> _Pass:
        _ = self._read_io(io, parent, self._size)
        return Pass

    def io_build(self, io: BitStream, parent: Container) -> None:  # noqa: ARG002
        i = 0
        while i < self._size:
            size = len(self._padding)
            self._write_io(io, self._padding.uint, size)
            i += size


class BitsInt(Codec):
    """
    Defines a integer representation from the ConstBitStream,
    will return an integer when parsing and takes ant int on building.

    >>> Struct(
        "int1" / BitInts(8),
    )
    """

    def __init__(self, size: int | LambdaType) -> None:
        self._size = size
        super().__init__()

    def _get_size(self, parent: Container) -> int:
        if callable(self._size):
            return self._size(parent)
        return self._size

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        value = self._read_io(io, parent, self._get_size(parent))
        return Container({self.name: value.uint})

    def io_build(self, io: BitStream, parent: Container) -> None:
        self._write_io(io, parent[self.name], self._get_size(parent))


class Enum(Codec):
    def __init__(
        self,
        subcodec: Codec | Codec,
        *,
        default: DefaultType = Error,
        **kwargs: int | str,
    ) -> None:
        super().__init__(subcodec)
        self._enum = Enumerate(self.name, kwargs)  # type: ignore[misc]
        self._default = default

    def io_parse(self, io: ConstBitStream, parent: Container) -> Container:
        peek = io.peek(len(self.subcodec))
        p_value = self.subcodec.io_parse(io, parent)[self.subcodec.name]
        try:
            return Container({self.name: self._enum(p_value)})
        except ValueError:
            try:
                return Container({self.name: self._enum[p_value]})
            except KeyError as err:
                if self._default.__class__ is _Pass:
                    return Container({self.name: p_value})
                raise ParseError(
                    parent,
                    self._subcodec,
                    peek,
                    f"Value {p_value} wasn't a valid enum, {self._enum!r}",
                ) from err

    def io_build(self, io: BitStream, parent: Container) -> None:
        value = parent[self.name]
        if value in self._enum:
            parent[self.name] = self._enum(value).value
            self.subcodec.io_build(io, parent)
            return
        if value in self._enum._value2member_map_:
            parent[self.name] = self._enum[value].value
            self.subcodec.io_build(io, parent)
            return
        if self._default.__class__ is _Pass:
            self.subcodec.io_build(io, parent)
            return
        raise BuildError(
            self.subcodec,
            f"Failed to find the enum mapping for {parent.name} in {list(self._enum)}",
        )


class Flag(BitsInt):
    def __init__(self) -> None:
        super().__init__(size=1)

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        value = self._read_io(io, parent, len(self))
        return Container({self.name: bool(value.uint)})


class Const(Codec):
    def __init__(self, subcodec: Codec, /, const: int | str) -> None:
        super().__init__(subcodec)
        self.constant = const

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        container = self._subcodec.io_parse(io, parent)
        name, value = container.popitem()
        if value != self.constant:
            raise ConstantError(f"Was expecting the value {self.constant} but got {value}")
        return Container({name: container})

    def io_build(self, io: BitStream, parent: Container) -> None:
        if self.name not in parent:
            parent[self.name] = self.constant
        self._write_io(io, parent[self.name], self._size)


class Default(Codec):
    def __init__(self, subcodec: Codec, /, default: Any) -> None:
        super().__init__(subcodec)
        self.default = default

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        return self.subcodec.io_parse(io, parent)

    def io_build(self, io: BitStream, parent: Container) -> None:
        if self.name not in parent:
            parent[self.name] = self.default
        super().io_build(io, parent)


class Peek(Codec):
    def __init__(self, subcodec: Codec, /, offset: int) -> None:
        super().__init__(subcodec)
        self._offset = offset

    def io_parse(self, io: ConstBitStream, parent: Container) -> Container | Any:
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

    def io_build(self, io: BitStream, parent: Container) -> None:
        pass


class Checksum(Codec):
    def __init__(self, subcodec: CodecType, /, crc: LambdaType) -> None:
        super().__init__(subcodec)
        self.crc = crc

    def io_parse(self, io: ConstBitStream, parent: Container) -> Container | _Pass | _Error:
        return self._subcodec.io_parse(io, parent)

    def io_build(self, io: BitStream, parent: Container) -> None:
        checksum = self.crc(parent)
        parent[self.name] = checksum
        self._subcodec.io_build(io, parent)


# ---------------- Mappings ----------------


class Switch(Codec):
    def __init__(
        self,
        funct: Callable[[Container], Any],
        mapping: dict[Any, CodecType],
        *,
        default: DefaultType = Error,
    ) -> None:
        self._size = 0
        super().__init__()
        self.function = funct
        self.mapping = mapping
        self._default = default

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        try:
            mapping_key = self.function(parent)
            subcodec = self.mapping[mapping_key]
        except (ValueError, KeyError):
            if self._default.__class__ is _Pass:
                return Pass
            raise
        return subcodec.io_parse(io, parent)

    def io_build(self, io: BitStream, parent: Container) -> None:
        mapping_key = self.function(parent)
        subcodec = self.mapping[mapping_key]
        if self.name in parent:
            subcodec.io_build(io, parent[self.name])
            return
        subcodec.io_build(io, parent)


class Mapping(Codec):
    def __init__(self, subcodec: Codec, mapping: dict[str, str | int]) -> None:
        super().__init__(subcodec)
        self.mapping = mapping

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        peek = io.peek(len(self.subcodec))
        map_key = self._subcodec.io_parse(io, parent)[self._subcodec.name]

        for key, value in self.mapping.items():
            if map_key == value:
                return Container({self.name: key})
        raise ParseError(
            parent,
            self._subcodec,
            peek,
            f"Value {map_key} wasn't found in the mapping {self.mapping}",
        )

    def io_build(self, io: BitStream, parent: Container) -> None:
        value = parent[self.name]
        if value not in self.mapping:
            raise BuildError(f"Value {value} wasn't found in the mapping {self.mapping}")
        self._subcodec.io_build(io, Container({self.subcodec.name: self.mapping[value]}))


# ---------------- Greedy ----------------


class Array(Codec):
    def __init__(self, subcodec: Codec, /, count: int | LambdaType) -> None:
        self._size = -1
        if not callable(count):
            self._size = len(subcodec) * count
        super().__init__(subcodec)
        self._count = count

    def _get_count(self, parent: Container) -> int:
        if callable(self._count):
            return self._count(parent)
        return self._count

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        count = self._get_count(parent)
        values = []
        i = 0
        while len(io) - io.pos > 0:
            if count != 0 and i >= count:
                break
            bits = ConstBitStream(io.read(len(self.subcodec)))
            container = self.subcodec.io_parse(bits, parent)
            _name, value = container.popitem()
            values.append(value)
            i += 1
        return Container({self.name: values})

    def io_build(self, io: BitStream, parent: Container) -> None:
        count = self._get_count(parent)
        array = parent.pop(self._subcodec.name)
        if count != len(array):
            raise BuildError(
                self,
                f"Expected an array of len {count} got an array of len {len(array)}",
            )
        for value in array:
            container = parent
            container[self._subcodec.name] = value
            self._subcodec.io_build(io, container)


class GreedyArray(Codec):
    def __init__(self, subcodec: Codec, /, count: int | LambdaType = 0) -> None:
        self._size = -1  # Greedy has no size, and isn't size 0
        super().__init__(subcodec)
        self._count = count

    def _get_count(self, parent: Container) -> int:
        if callable(self._count):
            return self._count(parent)
        return self._count

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        count = self._get_count(parent)
        values = []
        i = 0
        while len(io) - io.pos > 0:
            if count != 0 and i >= count:
                break
            bits = ConstBitStream(io.read(len(self.subcodec)))
            container = self.subcodec.io_parse(bits, parent)
            _name, value = container.popitem()
            values.append(value)
            i += 1
        return Container({self.name: values})

    def io_build(self, io: BitStream, parent: Container) -> None:
        count = self._get_count(parent)
        array = parent.pop(self._subcodec.name)
        if len(array) > count:
            raise BuildError(
                self,
                f"Expected an array of len 0 < x < {count} got an array of len {len(array)}",
            )
        for value in array:
            container = parent
            container[self._subcodec.name] = value
            self._subcodec.io_build(io, container)


class GreedyBits(Codec):
    def __init__(self, max_size: LambdaType | int = 0) -> None:
        self._size = -1  # Greedy has no size, and isn't size 0
        super().__init__()
        self._max_size: LambdaType | int = max_size

    def io_parse(self, io: ConstBitStream, parent: Container) -> Container:
        if callable(self._max_size):
            size = self._max_size(parent)
        elif self._max_size == 0:
            size = len(io) - io.pos
        elif self._max_size < 0:
            size = len(io) - io.pos + self._max_size  # Offset
        else:
            size = self._max_size

        if size < 0:
            raise LengthError(f"Tried parsing but got a negative Greedy length of {self._max_size}")

        value = self._read_io(io, parent, size)
        return Container({self.name: value})

    def io_build(self, io: BitStream, parent: Container) -> None:
        # TODO: Implement io_build
        raise NotImplementedError


# ---------------- Statements ----------------


class Conditional(Codec):
    def __init__(
        self,
        condition: LambdaType,
        then_: CodecType,
        else_: CodecType = Pass,
    ) -> None:
        self._size = 0
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

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        if self.condition(parent):
            return self.then_.io_parse(io, parent)
        if self.else_ is not Pass:
            return self.else_.io_parse(io, parent)
        return Pass

    def io_build(self, io: BitStream, parent: Container) -> None:
        if self.condition(parent):
            self.then_.io_build(io, parent)
        else:
            self.else_.io_build(io, parent)


class Optional(Codec):
    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        try:
            return self._subcodec.io_parse(io, parent)
        except ParseError:
            return Pass

    def io_build(self, io: BitStream, parent: Container) -> None:
        if self.name in parent:
            self._subcodec.io_build(io, parent)
