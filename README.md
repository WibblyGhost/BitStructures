# BitStructures

## Intro

This package was inspired by many byte level decoders and structure packing that were made for python, many of them didn't really handle bit streams directly.
Many packages I came across had a large list of outstanding issues and weren't updated in years.
So I decided to make a package that does exactly this, making it easy to define structural patterns to define network payloads on the bit level.

Running in **Python-3.12.xx** and greater with new type support for the structures and classes that help classify the built and parsed data. Making it easy to see what data is getting processed, the size of the data and what we are trying to write. There are also methods to present the structure in a human readable form.

## Issues/Discussions

Currently this is just a fun/personal project in my spare time so I may be unavailable to resolve or answer questions regarding this repo.
But feel free to raise discussions/issues with me and I may be able to have a look.

If raising an issue please include the following:
- The complete structure you are trying to build/parse.
- Both the raw byte stream you tried to parse and the Container you tried to build.
- What you expected to occur and any additional error output.

## Development

This project uses Astral-UV as it's package manager, Astral-Ruff as code linting and formatting and MyPy for type checking. Start by cloning down this repo, the running a `uv sync` and `pre-commit install`.

Create a custom `test.py` file under the `src/` directory to test out changes and custom codecs.

### MR's

Feel free to give this repo a fork and apply modifications/customisation to it. Upon wanting changes modified in the main repo firstly raise a discussion with me on what you propose to change and we can continue from there.

<!-- TODO: Move this README to a WIKI page -->

### Unit Tests

TODO:

## Quick Overview


### Supporting Classes

The encoders/decoders handle *key, value* pairs by pushing them onto a stack, rather that using a dictionary at this helps with error detection and ordering.
Each *key, value* pair is assigned a `Value(name, item, size)` class which makes it easy at computation time to determine the size of objects and where it went wrong when encoding/decoding patterns.

```python
@dataclass(slots=True, frozen=True)
class Value:
    name: str
    v_item: str | int | Enumerate | ConstBitStream | StackV
    size: int = field(default=-1, compare=False, hash=False)
```

There are two types of stacks, one for the values `StackV` or `Stack[Value]` and one for Structures `StackC` or `Stack[Codec]`.
All stacks have definitions for pushing, setting, clearing, popping and freezing the stack.
With `StackV` having an extended function set to help with recursive stacks, pretty printing and retreiving raw IO.

```python
class Stack[T: (Codec, Value)]:
    items: list[T]
    def __init__(self) -> None: ...
    def set_frozen(self) -> None: ...
    def pop(self, index: SupportsIndex = -1) -> T: ...
    def set(self, index: SupportsIndex, value: T) -> None: ...
    def empty(self) -> bool: ...
    def push(self, item: T) -> None: ...
    def __contains__(self, key: str) -> bool: ...
    def __iter__(self) -> Generator[tuple[int, T], Any, None]: ...
```

### Codecs

Codecs are all defined from the base class `Codec` which provides:
- All the needed base fucntions to decode byte streams into bit streams.
- Subcodecs for any subclass to use as it's codec.
- Sizes and defaut parsers like `Error` and `Pass` which are needed for conditional type `Codec`'s.
- Division functions to allow naming of the Codec.

The `Codec` class is meant to be subclassed and built upon to create custom encoders/decoders.
The following methods are meant to be overrided when subclassing.

```python
class Codec:
    name: str
    size: int | Callable[[StackV], int]
    def __init__(self, subcodec: Codec | None = None) -> None:
        '''
        Base class for codecs and is ideally subclassed for ALL codecs, contains
        all the logic needed for representing sizes, hashes,
        strings, naming, parsing and building.

        self.name:          Name of this codec, can use "name" / Codec to name this codec
        self._subcodec:     Codec to use when building, parsing or getting sizeof
        self._size:         Size in bits of this codec
        self._default:      Declarer on whether this Codec errors when no mapping is found
                            Only used in certain subclasses
        '''
    def __rtruediv__(self, other: Any) -> Self:
        '''
        Method which defines the behaviour of right side division.
        When a string is divided, apply that string as the name/describer
        of this Codec.
        E.g.

        >>> codec = "name" / Codec
        >>> print(codec.name)
        >>>> "name"
        '''
    def sizeof(self, parent: StackV, io: ConstBitStream | None = None) -> int: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        """
        Not called externally, only via this module.

        Handles the implementation of the parsing from an IO ConstBitStream to a Container.
        - Must be modified in the subclasses
        """
    def io_build(self, parent: StackV, container: Container) -> None:
        """
        Not called externally, only via this module.

        Handles the implementation of the build from Container to bytes.
        - Must be modified in the subclasses
        """
```

### Structures

`Struct`'s are the main building block and wrapper of codecs, these are what we use to call the `parse()` and `build()` methods and contain an array of `Codec`'s.
These can be nested inside each other, and may be either embedded into the current structure or wrapped into a seperate container upon parsing and building.

```python
class Struct(Codec):
    """
    Parent codec which is used to group Codecs together, this class must
    handle recursive Codecs when parsing and building.

    >>> codec = Struct(
        "int1" / BitInts(4),
        "int2" / BitInts(4),
    )
    """

    name: str
    def __init__(self, *args: Any, embedded: bool = True) -> None: ...
    def parse(self, raw: bytes, readall: bool = True) -> StackV:
        """
        Called externally via users.

        Handles the core parsing of the raw bytes into a ConstBitStream object,
        then passes the IO stream into the io_parse for custom parsing.
        - Generally not modified in subclasses
        """
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...
    def build(self, container: Container) -> bytes:
        """
        Called externally via users.

        Handles the core building of a Container into a bytes object,
        by passing the Container into the io_build for custom parsing.
        - Generally not modified in subclasses
        """
```

### Defaults

Some `Codec`'s can take a *default* argument which will take a Singleton object of `Pass` or `Error`, if this default is triggered then it will either ignore the failed conditional or error out of building/parsing.

```python
class Pass(Codec, metaclass=Singleton):
    """Declarer that this Codec *shouldn't* error when it fails to map"""

class Error(Codec, metaclass=Singleton):
    """Declarer that this Codec *should* error when it fails to map"""
    @classmethod
    def raise_error(cls) -> NoReturn: ...
```

### Padding

You can define an empty bits object which doesn't care whether the value is present when building or parsing. You can pass in a padding pattern in bit format, e.g. `0b0101`. These aren't returned upon parsing as they are meant for *reserved*/*padded*/filler definitions.

```python
class Padding(Codec):
    """
    Used when we don\'t want any value to represent the allocated data,
    can be used as a *pad or fill* in a structure and will not be returned
    during building.

    >>> Struct(
        "int1" / BitInts(4, padding=0b0101),
        Padding(4)
    )
    """
```


### Core Codecs

```python
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

    size: int | Callable[[StackV], int]
    def __init__(self, size: int) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...

class Padding(Codec):
    """
    Used when we don\'t want any value to represent the allocated data,
    can be used as a *pad or fill* in a structure and will not be returned
    during building.

    >>> Struct(
        "int1" / BitInts(4, padding=0b0101),
        Padding(4)
    )
    """

    size: int | Callable[[StackV], int]
    name: str
    def __init__(self, size: int, pattern: int = 1) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...

class BitsInt(Codec):
    """
    Defines a integer representation from the ConstBitStream,
    will return an integer when parsing and takes ant int on building.

    >>> Struct(
        "int1" / BitInts(8),
    )
    """

    size: int | Callable[[StackV], int]
    def __init__(self, size: int | FunctType) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...

class Enum(BitsInt):
    def __init__(
        self, size: int | FunctType, *, default: DefaultType = ..., **kwargs: int | str
    ) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...

class Flag(BitsInt):
    def __init__(self) -> None: ...

class Const(Codec):
    constant: Pass | Error
    def __init__(self, subcodec: Codec, /, const: int | str) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...

class Default(Codec):
    default: Pass | Error
    def __init__(self, subcodec: Codec, /, default: Any) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...

class Peek(Codec):
    def __init__(self, subcodec: Codec, /, offset: int) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None:
        """This IO parse method doesn't consume the IO stream, we just *peek* at the stream"""
    def io_build(self, parent: StackV, container: Container) -> None: ...

class Checksum(Codec):
    crc: Incomplete
    def __init__(self, subcodec: Codec, /, crc: FunctType) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...

class Switch[MKey: Any, MValue: Codec](Codec):
    function: Incomplete
    mapping: Incomplete
    def __init__(
        self,
        funct: Callable[[Container], MKey],
        mapping: dict[MKey, MValue],
        *,
        default: DefaultType = ...,
    ) -> None: ...
    def __rtruediv__(self, other: Any) -> Self: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...

class Mapping(Codec):
    mapping: Incomplete
    def __init__(self, subcodec: Codec, mapping: dict[str, str | int]) -> None: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...

class Array(Codec):
    def __init__(self, subcodec: Codec, /, count: int | FunctType) -> None: ...

class GreedyArray(Codec):
    def __init__(self, subcodec: Codec, /, count: int | FunctType = 0) -> None: ...

class GreedyBits(Codec):
    def __init__(self, max_size: FunctType | int = 0) -> None: ...
    def sizeof(self, parent: StackV, io: ConstBitStream) -> int: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...

class Conditional(Codec):
    condition: Incomplete
    then_: Codec
    else_: Codec | Pass | Error
    def __init__(self, condition: FunctType, then_: Codec, else_: Codec = ...) -> None: ...
    def __rtruediv__(self, other: Any) -> Self: ...
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def sizeof(self, parent: StackV, io: ConstBitStream) -> int: ...

class Optional(Codec):
    def io_parse(self, io: ConstBitStream, parent: StackV) -> None: ...
    def io_build(self, parent: StackV, container: Container) -> None: ...
```

```python
PrettyPrint:
        'version'            | size=4  | 4
        'header_length'      | size=4  | 20
        >----------------tos 8----------------->
        'precedence'         | size=3  | 0
        'minimize_delay'     | size=1  | 0
        'high_throuput'      | size=1  | 0
        'high_reliability'   | size=1  | 0
        'minimize_cost'      | size=1  | 0
        '__padding'          | size=1  | 0b0
        <--------------------------------------<
        'total_length'       | size=16 | 28
        'identification'     | size=16 | 1
        >---------------flags 3---------------->
        '__padding'          | size=1  | 0b0
        'dont_fragment'      | size=1  | 0
        'more_fragments'     | size=1  | 0
        <--------------------------------------<
        'fragment_offset'    | size=13 | 0
        'ttl'                | size=8  | 64
        'protocol'           | size=8  | enum.UDP
        'checksum'           | size=16 | 60351
        'source_ip'          | size=32 | 127.0.0.1
        'destination_ip'     | size=32 | 8.8.8.8
        >--------------header 64--------------->
        'source_port'        | size=16 | 53
        'destination_port'   | size=16 | 53
        'payload_length'     | size=16 | 16
        'checksum'           | size=16 | 28771
        <--------------------------------------<
```

## Examples

[Simple IPv4 Codecs](src/examples/ip_codec.py)
```python
IPV4_HEADER = Struct(
    "version" / Const(BitsInt(4), const=4),
    "header_length"
    / ExprAdapter(
        BitsInt(4),
        encoder=lambda obj: obj * 4,
        decoder=lambda obj: ceil(obj / 4),
    ),
    "tos" /
    Struct(
        "precedence" / BitsInt(3),
        "minimize_delay" / Flag(),
        "high_throuput" / Flag(),
        "high_reliability" / Flag(),
        "minimize_cost" / Flag(),
        Padding(1),
        embedded=False
    ),
    "total_length" / BitsInt(16),
    "identification" / BitsInt(16),
    "flags" / Struct(
        Padding(1),
        "dont_fragment" / Flag(),
        "more_fragments" / Flag(),
        embedded=False
    ),
    "fragment_offset" / BitsInt(13),
    "ttl" / BitsInt(8),
    "protocol"
    / Enum(
        8,
        ICMP=1,
        TCP=6,
        UDP=17,
    ),
    "checksum" / BitsInt(16),
    "source_ip" / IpAddress(BitsInt(32)),
    "destination_ip" / IpAddress(BitsInt(32)),
    "options" / Optional(BitsInt(lambda packet: packet.header_length - 20)),
)

TCP_HEADER = Struct(
    "source_port" / BitsInt(16),
    "destination_port" / BitsInt(16),
    "seq" / BitsInt(32),
    "ack" / BitsInt(32),
    "header_length"
    / ExprAdapter(
        BitsInt(4),
        encoder=lambda obj: obj * 4,
        decoder=lambda obj: ceil(obj / 4),
    ),
    Padding(3),
    "flags" / Struct(
        "ns" / Flag(),
        "cwr" / Flag(),
        "ece" / Flag(),
        "urg" / Flag(),
        "ack" / Flag(),
        "psh" / Flag(),
        "rst" / Flag(),
        "syn" / Flag(),
        "fin" / Flag(),
        embedded=False
    ),
    "window" / BitsInt(16),
    "checksum" / BitsInt(16),
    "urgent" / BitsInt(16),
    "options" / Optional(BitsInt(lambda packet: packet.header_length - 20)),
    embedded=False,
)

UDP_HEADER = Struct(
    "source_port" / BitsInt(16),
    "destination_port" / BitsInt(16),
    "payload_length"
    / ExprAdapter(
        BitsInt(16),
        encoder=lambda obj: obj + 8,
        decoder=lambda obj: obj - 8,
    ),
    "checksum" / BitsInt(16),
    embedded=False,
)
```