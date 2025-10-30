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
<!-- 
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
-->
