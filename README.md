# BitStructures

## Intro

This package was inspired by many byte level decoders and structure packing that were made for python, many of them didn't really handle bit streams directly.
Many packages I came across had a large list of outstanding issues and weren't updated in years.
So I decided to make a package that does exactly this, making it easy to define structural patterns to define network payloads on the bit level.

Running in **Python-3.13.xx** and greater with new type support for the structures and classes that help classify the built and parsed data. Making it easy to see what data is getting processed, the size of the data and what we are trying to write. There are also methods to present the structure in a human readable form.

## Issues/Discussions

Currently this is just a fun/personal project in my spare time so I may be unavailable to resolve or answer questions regarding this repo.
But feel free to raise discussions/issues with me and I may be able to have a look.

If raising an issue please include the following:
- The complete structure you are trying to build/parse.
- Both the raw byte stream you tried to parse and the Container you tried to build.
- What you expected to occur and any additional error output.

## Development

This project uses UV as its package manager, Ruff for code linting and formatting, and MyPy for type checking. Start by cloning down this repo, then running `uv sync` and `pre-commit install`.

Create a custom `test.py` file under the `src/` directory to test out changes and custom codecs.

### MRs

Feel free to fork this repo and apply modifications/customization to it. Upon wanting changes modified in the main repo firstly raise a discussion with me on what you propose to change and we can continue from there.

<!-- TODO: Move this README to a WIKI page -->

### Unit Tests

TODO:


## Supporting Classes

### BitStream

`BitStream` is a custom IO buffer class which works on [`bitarray`](https://github.com/ilanschnell/bitarray) objects.
Taking in a bytes/bits buffer type and creating a buffer to read and write upon.
This class contains many methods to make it easier to convert between bits and integers or bytes.
Writing and reading to/from the stream modifies the underlying buffer.

```python
class BitStream:
    """Custom IO class which converts a bytestream into a bitstream with read and write methods."""
    bitarray: bitarray
    def __init__(self, buffer: bytes | bitarray | str = b'', *, size: int = -1) -> None: ...
    def peek(self, size: int) -> BitStream: ...
    def read(self, size: int | None = -1) -> BitStream: ...
    def write(self, value: int | BitStream, size: int) -> None: ...
    def copy(self) -> Self: ...
    @property
    def bin(self) -> str: ...
    def __len__(self) -> int: ...
    def __int__(self) -> int: ...
    def __bytes__(self) -> bytes: ...
```

### Stacks & Values

The encoders/decoders handle *key, value* pairs by pushing them onto a stack, rather than using a dictionary, which helps with error detection and ordering.
Each *key, value* pair is assigned a `Value(name, item, size)` class which makes it easy at computation time to determine the size of objects and where it went wrong when encoding/decoding patterns.

```python
@dataclass(slots=True, frozen=True)
class Value:
    """
    Dataclass which stores all the information about the current encoded/decoded value,
    this will get passed around all the parse functions and contains name, size and values.
    """
    name: str
    v_item: ValueType
    size: int = field(default=-1, compare=False, hash=False)
    def pprint(self) -> str: ...
```

Containers are essentially glorified `deque`'s which have dictionary getter and setter methods, whilst also including some additional attribute access functionality.
Meaning that you can access the items of the Container with direct `container.item` analogy, upon failure to find an attribute it will search the underlying data store for that attribute too.
This class can be set as frozen to disallow any modifications and deletions to the object, and has a nice **pretty print** function built in.

```python

class Container[T: Any = Any](MutableMapping[str, T]):
    """
    Wrapper for a dictionary-like object, we use this to add extra functionality to
    the container indexing, and adding frozen attributes to the setters.

    You can access container attributes like normal `container["id"]` or via
    direct access `container.id`.
    """

    def set_frozen(self) -> None: ...
    def pprint(self, *, padding: str = "\t{t}{v:-^38}{t}\n", depth: int = 1) -> str: ...
```

Stacks work off a base layer of the **list** to create stack functionality, which includes pushing items onto a stack and popping items off a stack.
You can assign the type of the **Stack** using the `Stack[Value]` terminology.

All stacks have definitions for pushing, setting, clearing, popping and freezing the stack.

```python
class Stack[T: SupportsName](FrozenSlots):
    items: list[T]
    def pop(self, index: SupportsIndex = -1) -> T: ...
    def set(self, index: SupportsIndex, value: T) -> None: ...
    def empty(self) -> bool: ...
    def push(self, item: T) -> None: ...
    def enumerate(self) -> Generator[tuple[int, T]]: ...
```

There is a subclassed version of the **Stack** called `StackC` which is specifically used during parsing and building to attach exception tracebacks.
It contains all the previously parsed/built Codecs and the current Codec.
There's also a **pretty print** function built into this Stack to help print out the Codec's and their sizes.

```python
class StackC(Stack["Codec | StackC"]):
    """Version of the stack which contains methods for holding Codec's."""
    name: str
    def pprint(self, *, depth: int = 1) -> str: ...
```

EnumBase is just a wrapper for the Enum class which helps with string representations for the codecs.

```python
class EnumBase(Enum_):
    """Basic override for the Enum object to change string representations."""

    name: str
    value: int
```

## Codec

Codecs are all defined from the base class `Codec` which provides:
- All the needed base functions to decode byte streams into bit streams.
- Subcodecs for any subclass to use as its codec.
- Sizes and default parsers like `Error` and `Pass` which are needed for conditional type `Codec`s.
- Division functions to allow naming of the Codec.

The `Codec` class is meant to be subclassed and built upon to create custom encoders/decoders.
The following methods are meant to be overridden when subclassing.

```python
class Codec(CodecProtocol):
    """
    Base class for codecs and is ideally subclassed for ALL codecs, contains
    all the logic needed for representing sizes, hashes, strings, naming, parsing and building.

    Most codecs need to initialised with a description, except for
    any Struct's or special types.

    The size of the Codec can be a concrete integer type, or calculated during
    parsing/building via a lambda.

    *Count*
    >>>  "codewords" / Codec(4)

    *Functional*
    >>>  "codewords" / Codec(lambda packet: packet.codeword_size)
    """

    def __init__(self, subcodec: Codec | None = None) -> None:
        """
        self._subcodec:     Codec to use when building, parsing or getting sizeof
        self.name:          Name of this codec, can use "name" / Codec to name this codec
        self.size:         Size in bits of this codec.
        """
    @property
    def name(self) -> str: ...
    @property
    def size(self) -> int:
        """
        Attempts to calculate the size of this Codec
        NOTE: This will not always work, or be accurate, please double check the
              output size is what you expect.
        """
    def __rtruediv__(self, other: Any) -> Self:
        """
        Method which defines the behaviour of right side '/' operator.
        When a string is divided, apply that the name/describer
        of this Codec.
        E.g.

        >>> codec = "name" / Codec
        >>> print(codec.name)
        >>>> "name"
        """
    def rename(self, name: str) -> None: ...
    def sizeof(self, io: BitStream, context: Container, codecs: StackC) -> int: ...
```

### Defaults

> [!NOTE]
> This section is different to the Default Codec type defined later down.

Some `Codec`'s can take a *default* argument which will take a Singleton object of `Pass` or `Error`, if this default is triggered then it will either ignore the failed conditional or error out of building/parsing.
These Codec's don't need to be initialised via `Pass()` or `Error()`, since they are Singletons assigned to a variable.
Please see the *Pass* and *Error* Codec headers for more information around these Codecs

#### Pass

Simple codec that parses and builds to an empty string/container, useful if there is an optional codec.

```python
class Pass(Codec):
    """
    Declarer that this Codec *shouldn't* error when it fails to map,
    this class will encode into a null terminated bitarray and skip decoding.
    """
```

#### Error

Much like the Pass codec but instead when this Codec is parsed or built, will raise an exception.

```python
class Error(Codec):
    """
    Declarer that this Codec *should* error when it fails to map,
    this class will raise an exception upon parsing or building upon.
    """

    @classmethod
    def raise_error(cls, io: BitStream, context: Container, codecs: StackC, **kwargs: Any) -> NoReturn: ...
```

#### NotImplementedCodec

Acts exactly the same as the Error Codec, but is useful for flagging future development for this Codec.

```python
NotImplementedCodec = Error
```

### Structures

#### Struct

`Struct`'s are the main building block and wrapper of codecs, these are what we use to call the `parse()` and `build()` methods and contain an array of `Codec`'s.
These can be nested inside each other, and may be either embedded into the current structure or wrapped into a seperate container upon parsing and building.

```python
class Struct(Codec, StructProtocol):
    """
    Parent codec which is used to group Codecs together, this class must
    handle recursive Codecs when parsing and building.

    >>> codec = Struct(
        "int1" / BitInts(4),
        "int2" / BitInts(4),
    )
    """

    def __init__(self, *args: Any, embedded: bool = False) -> None: ...
```

#### Pointers

Sometimes you need advanced IO handling so that you can read IO out of sequence. The Pointer class helps forward the
IO stream, parse the later stream, then reverse the stream and parse the original segment.

```python
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

    def __init__(
        self,
        start_codec: Iterable[Codec],
        end_codec: Iterable[Codec],
        /,
        *,
        start: int,
        end: int,
        embedded: bool = False,
    ) -> None: ...
```


### Conditionals

#### Conditional

Provides a simple way to choose between two different Codec's given a *lambda* expressions output.
Very helpful if there are different Codec's getting parsed when a value or flag is present.

```python
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

    def __init__(
        self, condition: FunctType[int], then_: Codec, else_: Codec = ..., *, embedded: bool = False
    ) -> None: ...
```

#### Switch

Super useful Codec which takes in large dictionary mappings (`dict[MappingType, Codec]`) returning a Codec.
These can be toggled to be embedded much like the Struct can be, and can default to erroring or just parsing to an empty string.
```python
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

    def __init__(
        self,
        funct: FunctType[MKey],
        mapping: dict[MKey, MValue],
        *,
        default: DefaultType | MValue = ...,
        embedded: bool = False,
    ) -> None: ...
```

#### Optional

This Codec will attempt to parse and build the Codec, but upon failing, will just parse/build to an empty string.

```python
class Optional(Codec):
    """
    Will attempt to parse/build this Codec, but upon failure, will ignore the
    errors and parse an empty value.

    >>> "options" / Optional(BitsInt(8))
    """
```

### Codecs

#### Padding

You can define an empty bits object which doesn't care whether the value is present when building or parsing. You can pass in a padding pattern in bit format, e.g. `0b0101`. These aren't returned upon parsing as they are meant for *reserved*/*padded*/filler definitions.

```python
class Padding(Codec):
    """
    Used when we don't want any value to represent the allocated data,
    can be a *pad or fill* in a structure and will not be returned
    during building.

    >>> Padding(4, padding=0b0101)
    """

    def __init__(self, size: int, /, *, pattern: int = 0) -> None: ...
```

#### BitsInt

Core Codec which converts a bitstream into an unsigned integer.

```python
class BitsInt(Codec):
    """
    Defines an integer representation from the BitStream,
    will return an integer when parsing and takes any int on building.

    >>> "int1" / BitInts(8)
    """

    def __init__(self, size: int | FunctType[int]) -> None: ...
```

#### Enum

The Enum Codec is a BitsInt type which contains a string to integer mapping for its parsed/built values.
By default, if a value cannot be mapped, it will raise an exception, but this can be changed to ignore missing
mappings via the `default=Pass` keyword argument.

```python
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

    def __init__(
        self, size: int | FunctType[int], *, default: DefaultType = ..., **kwargs: int | str
    ) -> None: ...
    @property
    def enum(self) -> EnumBase: ...
```

#### Mapping

Works exactly the same as the Enum Codec except that it takes a dictionary as its initialization.

```python
class Mapping(Enum):
    """
    Essentially the an Enum Codec, except that it takes a dictionary
    a list of enum values instead of building them out of the kwargs.

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

    def __init__(
        self, size: int | FunctType[int], map: dict[str, int | str], *, default: DefaultType = ...
    ) -> None: ...
```

#### Flag

Used to represent a boolean object or a flag, it is exactly one bit long.

```python
class Flag(BitsInt):
    """
    Defines a boolean or a 'flag' which represents one bit.

    >>> "inbound" / Flag()
    """

    def __init__(self) -> None: ...
```

#### Const

Wrapper Codec which takes a constant value, upon parsing and building it asserts that the value is the same.
Otherwise the parse/build will raise an exception.

```python
class Const(Codec):
    """
    Asserts that the parsed/built value always equals the constant,
    and adds the value to the build if not presented.

    >>> "version" / Const(BitsInt(24), const=0x2)
    """

    constant: int | str
    def __init__(self, subcodec: Codec, /, const: int | str) -> None: ...
```

#### Default

Wrapper for any codec which assigns a default value to the container upon building if not provided.

```python
class Default(Codec):
    """
    If a value wasn't provided in the build container, this Codec
    will add the value to the container set to it's default value.

    >>> "version" / Default(BitsInt(24), default=0x2)
    """

    def __init__(self, subcodec: Codec, /, default: Any) -> None: ...
```

#### Array

Codec which allows parsing segments of the IO stream into a lists of values,
this is done by assigning a codec and count amount.

The *count* argument can be an integer or a *lambda* expression.

```python
class Array(Codec):
    """
    Used to parse/build a collection of codecs, can be used with concretely
    defined counts, or via a lambda expression.

    *Count*
    >>>  "signs" / Array(BitsInt(4), count=8)

    *Functional*
    >>>  "signs" / Array(BitsInt(4), count=lambda packet: packet.array_count)
    """

    def __init__(self, subcodec: Codec, /, count: int | FunctType[int]) -> None: ...
```

#### Raw Bits

This codec just copies over the bitstream into the Container and vice versa.
Useful if you want to include a payload but don't want to perform any calculations on the output values.

```python
class RawBits(Codec):
    """
    When parsing or building this Codec, it will just copy over the raw
    IO stream into the container/stream.

    >>> "raw" / RawBits(8)
    """

    def __init__(self, size: FunctType[int] | int) -> None: ...
```

### Computations

#### Computed

Special Codec type which can perform calculations and representations of values **without** modifying the IO stream.

```python
class Computed[T: ValueType](Codec):
    """
    Calculates the field upon parsing but doesn't build into the stream.
    Useful for performing calculations that don't affect the stream.

    >>> Computed(lambda packet: packet.length * 8)
    """

    def __init__(self, function: FunctType[T], *args: Any, **kwargs: Any) -> None: ...
```

#### Bitshift

Useful for splitting and combining two different bit fields into one bit field,
meaning you can have codecs between the two integer parts then combine them into one field.


```python
class Bitshift[T: Any = int](Codec):
    """
    Codec which deals with splitting addresses into multiple
    bit fields, done by checking the size of the packet and
    applying a bitshift to combine the two packets.

    >>> Struct(
        "id_p1" / BitsInt(2),
        "random" / BitsInt(6),
        "id_p2" / BitsInt(8),
        "id" / Bitshift[int]("id", bitshift),
    )
    """

    def __init__(
        self, field_name: str, funct: Callable[..., T], msb: bool = True, *args: Any, **kwargs: Any
    ) -> None: ...
```

#### Checksum

Checksum is a very special Codec type which will perform checksum calculations on your packet after building.
The fields to perform the checksum calculations must be listed and present before the checksum Codec.

```python
class Checksum(BitsInt):
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

    def __init__(
        self, size: int, /, crc: Callable[[Buffer], int], field_names: set[str]
    ) -> None: ...
```

### Greedy

#### Greedy Array

Subset of the Array Codec but instead of giving the Codec a hardcoded container count, this Codec will keep parsing until an end of stream (EOS).
It can also take a *max_count* argument which will only parse the stream up to the specified count and no further.
Or the *max_count* argument can take a *lambda* expression.

```python
class GreedyArray(Array):
    """
    Used to parse/build a collection of codecs, can be used with concretely
    defined counts, or via a lambda expression. Except with this one we can
    define an infinite or bounded amount of collections.

    If infinite, it will consume the collection until there are no
    more to consume and add them to the stream.

    *Count until EOS*
    >>>  "signs" / GreedyArray(BitsInt(4))

    *Consume until count*
    >>>  "signs" / Array(BitsInt(4), max_count=4)

    *Functionally consume until count*
    >>>  "signs" / Array(BitsInt(4), max_count=lambda packet: packet.array_count)
    """

    def __init__(self, subcodec: Codec, /, max_count: int | FunctType[int] = -1) -> None: ...
```


#### Greedy Bits

Defines a Greedy bits consumer which will keep consuming the IO stream until an end of stream (EOS).
The output value will be a `BitStream` type. It works the same way as the `RawBits` Codec.

It can also take a *max_size* argument which will only parse the stream up to the specified length and no further.
Or the *max_size* argument can take a *lambda* expression.
Or the *max_size* argument can take a negative value which will parse until the IO head is -x bits from the EOS.

```python
class GreedyBits(Codec):
    """
    Used to parse/build an arbitrarily sized Codec, can be used with concretely
    defined max size or via a lambda expression. This Codec will consume the IO
    stream until it reaches a EOS or when it is at it's max size.

    If infinite, it will consume the collection until there are no
    more to consume and add them to the stream.

    If size is a negative value, the stream will continue
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

    def __init__(self, *, max_size: FunctType[int] | int = 0) -> None: ...
```

### Validators

#### Blacklisted

Simple wrapper for the BitsInt Codec which will raise an exception if the parsed value is in the blacklisted range.

```python
class Blacklisted(BitsInt):
    """
    Prevents parsing/building a certain range of values, failing to do so
    will raise a BlacklistedError.

    >>> "digit" = Blacklisted(8, [0])
    """

    def __init__(self, size: int, array: Iterable[int]) -> None: ...
```

#### Whitelisted

Simple wrapper for the BitsInt Codec which will raise an exception if the parsed value is not in the whitelisted range.

```python
class Whitelisted(BitsInt):
    """
    Only allows parsing/building a certain range of values, failing to do so
    will raise a WhitelistedError.

    >>> "digit" = Whitelisted(8, list(range(34)))
    """

    def __init__(self, size: int, array: Iterable[int]) -> None: ...
```

### Adapters

Adapters are easier to subclass than a Codec due to their simplicity.
They define a `decode` and `encode` function which will get called inside their respective `io_parse` and `io_build` functions.
When subclassing these, you only need to add/modify the `decode` and `encode` functions.

```python
class Adapter(Codec, AdapterProtocol):
    """
    Used for creating basic encoding/decoding functions that work on the
    stream during the parsing/building process. This allows us to perform
    small tweaks and value manipulation.

    This class isn\'t used directly and is subclassed to create custom functions.
    The following two functions must be defined in the subclass:

    def decode(self, context: Container, value: Any) -> Any: ...
    def encode(self, context: Container, value: Any) -> Any: ...
    """

    def __init__(self, subcodec: Codec) -> None: ...
    def decode(self, context: Container, value: Any) -> Any: ...
    def encode(self, context: Container, value: Any) -> Any: ...
```

#### IpAddress

This adapter converts the defined Codec into an IpAddress string and back into an integer field.

```python
class IpAddress(Adapter):
    """
    Converts an integer into an IP Address and vice versa, this is usually a 32 bit field.

    >>> "source_ip" / IpAddress(BitsInt(32))
    """
```

#### Scaler

Applies a multiplication upon the parsed/built field.

```python
class Scaler(Adapter):
    """
    Simple adapter which multiplies the encoded/decoded value by an integer factor.

    >>> "timer" / Scaler(BitsInt(16), factor=0.1)
    """

    def __init__(self, subcodec: Codec, /, factor: float) -> None: ...
```

#### ExprAdapter

Takes two lambda expressions inside the *init* for their respective *encoder* and *decoder* functions.

```python
class ExprAdapter(Adapter):
    """
    Simple adapter that takes lambda's as the encoders and decoders.

    >>> "header_length" / ExprAdapter(
        BitsInt(4),
        encoder=lambda value: ceil(value / 4),
        decoder=lambda value: value * 4,
    )
    """

    def __init__(self, subcodec: Codec, encoder: ExpType, decoder: ExpType) -> None: ...
```

## Examples

[Simple IPv4 Codecs](src/examples/ip_codec.py)
```python

IPV4_HEADER = Struct(
    "version" / Const(BitsInt(4), const=4),
    "header_length"
    / ExprAdapter(
        # Indicates the length of the header in 32-bit words (minimum is 5, which equals 20 bytes).
        BitsInt(4),
        encoder=lambda obj: obj * 4,
        decoder=lambda obj: ceil(obj / 4),
    ),
    "tos"
    / Struct(
        "precedence" / BitsInt(3),
        "minimize_delay" / Flag(),
        "high_throuput" / Flag(),
        "high_reliability" / Flag(),
        "minimize_cost" / Flag(),
        Padding(1),
        embedded=False,
    ),
    "total_length" / BitsInt(16),
    "identification" / BitsInt(16),
    "flags" / Struct(Padding(1), "dont_fragment" / Flag(), "more_fragments" / Flag()),
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
    "length"
    / ExprAdapter(
        BitsInt(4),
        encoder=lambda obj: obj * 4,
        decoder=lambda obj: ceil(obj / 4),
    ),
    Padding(3),
    "flags"
    / Struct(
        "ns" / Flag(),
        "cwr" / Flag(),
        "ece" / Flag(),
        "urg" / Flag(),
        "ack" / Flag(),
        "psh" / Flag(),
        "rst" / Flag(),
        "syn" / Flag(),
        "fin" / Flag(),
        embedded=False,
    ),
    "window" / BitsInt(16),
    "checksum" / BitsInt(16),
    "urgent" / BitsInt(16),
    "options" / Optional(BitsInt(lambda packet: packet.length - 20)),
)

UDP_HEADER = Struct(
    "source_port" / BitsInt(16),
    "destination_port" / BitsInt(16),
    # Indicates the total length of the UDP header plus the payload.
    # The minimum value for this field is 8 (the header size), as there is always a header present.
    "length" / BitsInt(16),
    "checksum" / BitsInt(16),
)


# IP/UDP packet used for basic packet data tests, not in spec
IP_PACKET = Struct(
    IPV4_HEADER,
    "header"
    / Switch[str, Codec](lambda packet: packet.protocol, {"UDP": UDP_HEADER, "TCP": TCP_HEADER}),
    "payload" / GreedyBits(),
)
```
