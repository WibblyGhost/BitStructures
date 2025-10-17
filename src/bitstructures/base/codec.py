from collections import UserDict
from collections.abc import Callable
from copy import deepcopy
from enum import Enum as Enumerate
from types import LambdaType
from typing import Any, Self

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
from bitstructures.typing import DefaultType, ParseReturn

# ---------------- Wrappers ----------------


def singleton[T: Callable[..., Any]](class_: T) -> T:
    """Defines a class that only ever needs to be initialised once"""
    return class_()


# ---------------- Containers ----------------


class Container(UserDict):
    def __getattr__(self, attr: str) -> Any:
        return self.get(attr)


# ---------------- Bits ----------------


class Codec:
    def __init__(self, subcodec: "Codec" = None) -> None:
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
        if subcodec.__class__ is self.__class__:  # Prevent recursion
            self._size: int = -1
        else:
            self._size = len(self._subcodec)
        self._default: DefaultType = Error

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
            if new.subcodec and new.subcodec.__class__ is not new.__class__:
                new.subcodec.name = other
            return new
        if isinstance(other, Codec):
            raise CTypeError(
                f"This {Codec.__name__.lower()} {self.__class__.__name__} doesn't support "
                f"rdiv on other {Codec.__name__} structures"
            )
        raise CTypeError(f"Unhandled type {type(other)} for division")

    def __len__(self) -> int:
        return self._size

    def sizeof(self) -> int:
        if self._size < 0:  # If size is negative
            raise SizeError("This class has no length defined")
        return len(self)

    @property
    def subcodec(self) -> "Codec":
        return self._subcodec

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
            return io.read(size)
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

    def parse(self, raw: bytes, parent: Container = None) -> ParseReturn:
        """
        Called externally via users.

        Handles the core parsing of the raw bytes into a ConstBitStream object,
        then passes the IO stream into the io_parse for custom parsing.
        - Generally not modified in subclasses
        """
        io = self._parse_io(raw)
        container = self.io_parse(io, parent or Container())
        if container is Pass or container is Error:
            raise CodecError
        return container

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

    def io_build(self, io: BitStream, container: Container) -> None:
        """
        Not called externally, only via this module.

        Handles the implementation of the build from Container to bytes.
        - Must be modified in the subclasses
        """
        raise NotImplementedError(f"Method io_build must be created via subclass {self.__class__}")

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
            raise BuildError("Built container must be divisible by 8 (1 byte)")
        return bytes(io)


# ---------------- Error Handlers ----------------


@singleton
class Pass(Codec):
    """Declarer that this Codec *shouldn't* error when it fails to map"""

    def __init__(self, subcodec: Codec = None) -> None:
        pass

    def __rtruediv__(self, other: Any) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    def io_build(self, io: BitStream, container: Container) -> None:
        pass

    def io_parse(self, io: ConstBitStream, parent: Container) -> Self:
        return self


@singleton
class Error(Codec):
    """Declarer that this Codec *should* error when it fails to map"""

    def __init__(self, subcodec: Codec = None) -> None:
        pass

    def __rtruediv__(self, other: Any) -> Self:
        raise RDivError

    def __deepcopy__(self, memo: Any) -> Self:
        return self

    def __len__(self) -> int:
        return 0

    def io_build(self, io: BitStream, container: Container) -> None:
        raise TriggeredError("This error was triggered via a default set to Error")

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        raise TriggeredError("This error was triggered via a default set to Error")


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

    def _check_subcodec_len(self) -> None:
        self._size = sum(len(subcodec) for subcodec in self.subcodecs.values())
        if self._size % 8 != 0:
            init_error = InitError(
                f"Incorrect total bit size ({self._size}) was defined for a {Struct.__name__}, "
                f"all {Codec.__name__} under this struct must be divisible by 8 (1 byte)"
            )
            init_error.add_note(
                str({subcodec.name: len(subcodec) for subcodec in self.subcodecs.values()})
            )
            raise init_error

    def __init__(self, *args: Any, description: str = None) -> None:
        self._subcodecs: dict[str, Codec] = {}
        self._check_subcodec_type(*args)
        self._check_subcodec_len()
        super().__init__()
        self.__rtruediv__(description)

    def io_parse(self, io: ConstBitStream, parent: Container = None) -> Container:
        container = parent or Container()
        for subcodec in self.subcodecs.values():
            cont = subcodec.io_parse(io, container)
            if cont is Pass:
                continue
            container.update(cont)
        return container

    def io_build(self, io: BitStream, container: Container) -> None:
        for subcodec in self.subcodecs.values():
            subcodec.io_build(io, container)

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
                        f"Missing key {subcodec.name} from the container {container!s}"
                    )
                subcodec.io_build(io, container)
        if len(io) % 8 != 0:
            raise BuildError("Built container must be divisible by 8 (1 byte)")
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

    def __init__(self, size: int, padding: int = 0b1) -> None:
        self._size = size
        super().__init__()
        self._padding = ConstBitStream(padding)

    def io_parse(self, io: ConstBitStream, parent: Container) -> Pass:
        _ = self._read_io(io, parent, self._size)
        return Pass

    def io_build(self, io: BitStream, container: Container) -> None:
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

    def __init__(self, bit_size: int) -> None:
        self._size = bit_size
        super().__init__()

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        value = self._read_io(io, parent, len(self))
        return Container({self.name: value.uint})

    def io_build(self, io: BitStream, container: Container) -> None:
        self._write_io(io, container[self.name], self._size)


class Enum(Codec):
    def __init__(
        self,
        subcodec: Codec | Codec,
        *,
        default: DefaultType = Error,
        **kwargs: int | str,
    ) -> None:
        super().__init__(subcodec)
        self._enum = Enumerate(self.name, kwargs)
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
                if self._default is Pass:
                    return Container({self.name: p_value})
                raise ParseError(
                    parent,
                    self._subcodec,
                    peek,
                    f"Value {p_value} wasn't a valid enum, {self._enum!r}",
                ) from err

    def io_build(self, io: BitStream, container: Container) -> None:
        value = container[self.name]
        if value in self._enum:
            container[self.name] = self._enum(value).value
            self.subcodec.io_build(io, container)
            return
        if value in self._enum._value2member_map_:
            container[self.name] = self._enum[value].value
            self.subcodec.io_build(io, container)
            return
        if self._default is Pass:
            self.subcodec.io_build(io, container)
            return
        raise BuildError(
            f"Failed to find the enum mapping for {container.name} in {list(self._enum)}"
        )


@singleton
class Flag(BitsInt):
    def __init__(self) -> None:
        super().__init__(bit_size=1)

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        value = self._read_io(io, parent, len(self))
        return Container({self.name: bool(value.uint)})


class Const(BitsInt):
    def __init__(self, constant: int | str, bit_size: int) -> None:
        super().__init__(bit_size)
        self.constant = constant

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        container = super().io_parse(io, parent)
        name, value = container.popitem()
        if value != self.constant:
            raise ConstantError(f"Was expecting the value {self.constant} but got {value}")
        return Container({name: container})

    def io_build(self, io: BitStream, container: Container) -> None:
        if self.name not in container:
            container[self.name] = self.constant
        super().io_build(io, container)


class Default(Codec):
    def __init__(self, default: Any, subcodec: Codec) -> None:
        super().__init__(subcodec)
        self.constant = default

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        return self.subcodec.io_parse(io, parent)

    def io_build(self, io: BitStream, container: Container) -> None:
        if self.name not in container:
            container[self.name] = self.constant
        super().io_build(io, container)


# ---------------- Mappings ----------------


class Switch(Codec):
    def __init__(
        self,
        funct: Callable[[Container], Any],
        mapping: dict[Any, Codec],
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
            if self._default is Pass:
                return Pass
            raise
        return subcodec.io_parse(io, parent)

    def io_build(self, io: BitStream, container: Container) -> None:
        mapping_key = self.function(container)
        subcodec = self.mapping[mapping_key]
        if self.name in container:
            subcodec.io_build(io, container[self.name])
            return
        subcodec.io_build(io, container)


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

    def io_build(self, io: BitStream, container: Container) -> None:
        value = container[self.name]
        if value not in self.mapping:
            raise BuildError(f"Value {value} wasn't found in the mapping {self.mapping}")
        self._subcodec.io_build(io, Container({self.subcodec.name: self.mapping[value]}))


# ---------------- Greedy ----------------


class Array(Codec):
    def __init__(self, subcodec: Codec, *, count: int) -> None:
        if count < 1:
            raise InitError(f"Array must have a positive count, got {count}")
        self._size = len(self.subcodec) * count
        super().__init__(subcodec)
        self._count: int = count

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        values = []
        i = 0
        while len(io) - io.pos > 0:
            if self._count != 0 and i >= self._count:
                break
            bits = io.read(len(self.subcodec))
            container = self.subcodec.io_parse(bits, parent)
            _name, value = container.popitem()
            values.append(value)
            i += 1
        return Container({self.name: values})


class GreedyArray(Codec):
    def __init__(self, subcodec: Codec, *, count: int = 0) -> None:
        self._size = -1  # Greedy has no size, and isn't size 0
        super().__init__(subcodec)
        self._count: int = count

    def io_parse(self, io: ConstBitStream, parent: Container) -> ParseReturn:
        values = []
        i = 0
        while len(io) - io.pos > 0:
            if self._count != 0 and i >= self._count:
                break
            bits = io.read(len(self.subcodec))
            container = self.subcodec.io_parse(bits, parent)
            _name, value = container.popitem()
            values.append(value)
            i += 1
        return Container({self.name: values})


class GreedyBits(Codec):
    def __init__(self, *, max_size: LambdaType | int = 0) -> None:
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


# ---------------- Statements ----------------


class Conditional(Codec):
    def __init__(
        self,
        condition: LambdaType,
        then_: "Codec | Pass | Error",
        else_: "Codec | Pass | Error" = Pass,
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

    def io_build(self, io: BitStream, container: Container) -> None:
        if self.condition(container):
            self.then_.io_build(io, container)
        else:
            self.else_.io_build(io, container)
