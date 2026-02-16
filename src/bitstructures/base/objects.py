from collections import deque
from collections.abc import Generator, Iterable, Iterator
from dataclasses import dataclass, field
from enum import Enum as Enum_
from typing import Any, Self, SupportsIndex, overload, override

from bitstructures.base.bitstream import BitStream
from bitstructures.constants import PP_DETENT, PP_INDENT, PP_TAB
from bitstructures.exceptions import FrozenError, SizeError
from bitstructures.typing import SupportsKeysAndGetItem, SupportsName, ValueType


class FrozenSlots:
    """
    Used to create a frozen class which cannot be modified after
    setting it as frozen.
    """

    __slots__ = ("_frozen",)

    def __init__(self) -> None:
        self._frozen: bool = False

    def freeze(self) -> None:
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
    this will get passed around all the parse functions and contains name, size and values.
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
    def bitstream(self) -> BitStream:
        if isinstance(self.v_item, Container):
            bitstream = BitStream()
            for value in self.v_item.values():
                bitstream += value.bitstream
            return bitstream

        if not isinstance(self.v_item, BitStream):
            raise TypeError(
                f"Expected item to be of type BitStream but got "
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


class Deque[VT](deque[tuple[str, VT]]):
    """
    Overrided version of the buildin deque class, which ONLY takes tuples containing
    a str as the first argument.

    **For direct use in the Container's only.**
    """

    @override
    def __repr__(self) -> str:
        return f"{dict(self)}"


class Container[VT: Any = Any]:  # Can't use FrozenSlots here due to __getattr__
    """
    Wrapper for a dictionary-like object, we use this to add extra functionality to
    the container indexing, and adding frozen attributes to the setters.

    You can access container attributes like normal `container["id"]` or via
    direct access `container.id`.
    """

    __slots__ = ("__deque", "__frozen", "__parent")

    def __init__(
        self, dictionary: SupportsKeysAndGetItem[str, VT] | None = None, **kwargs: VT
    ) -> None:
        self.__deque: Deque[VT] = Deque()
        self.__frozen: bool = False
        self.__parent: Container[VT] | None = None
        if dictionary is not None:
            for key, value in dictionary.items():
                self.__deque.append((key, value))
        if kwargs:
            for key, value in kwargs.items():
                self.__deque.append((key, value))
        for key, value in self:
            if isinstance(value, dict):
                self[key] = Container(self[key])  # type: ignore[assignment]

    def _check_frozen(self) -> None:
        if self.__frozen:
            raise FrozenError("Class is now frozen, cannot change attributes")

    def __iter__(self) -> Iterator[tuple[str, VT]]:
        return iter(self.__deque)

    def __contains__(self, key: object) -> bool:
        return any(kv == key for kv, _value in self.__deque)

    def __len__(self) -> int:
        return len(self.__deque)

    def __setitem__(self, key: str, value: VT, /) -> None:
        self._check_frozen()
        for i, (kv, _v) in enumerate(self):
            if key == kv:
                self.__deque[i] = (kv, value)
                return
        self.__deque.append((key, value))

    def __getitem__(self, key: str) -> VT:
        for kv, v in self:
            if kv == key:
                return v
        raise KeyError(key)

    def __delitem__(self, key: str, /) -> None:
        self._check_frozen()
        value = self[key]
        self.__deque.remove((key, value))

    def clear(self) -> None:
        self._check_frozen()
        self.__deque.clear()

    def freeze(self) -> None:
        self.__frozen = True

    def unfreeze(self) -> None:
        self.__frozen = False

    def copy(self) -> Self:
        container = self.__class__()
        for key, value in self:
            container[key] = value
        if self.__frozen:
            container.freeze()
        return container

    def values(self) -> Iterable[VT]:
        for _k, v in self:
            yield v

    def keys(self) -> Iterable[str]:
        for k, _v in self:
            yield k

    def items(self) -> Iterable[tuple[str, VT]]:
        yield from self

    @overload
    def get(self, key: str, /) -> VT: ...

    @overload
    def get(self, key: str, default: Any = None, /) -> VT | Any: ...

    def get(self, key: str, default: Any = None, /) -> VT | None | Any:
        return self[key] if key in self else default  # noqa: SIM401  # This __is__ the .get() funct

    def set(self, key: str, value: VT) -> None:
        self[key] = value

    def _rec_str(self, value: VT | Deque[VT]) -> Any:
        """Formats any nested Container's."""
        # RECURSIVE
        if isinstance(value, BitStream):
            if len(value) % 8 == 0:
                return bytes(value)
            return f"0b{value.bin}"
        if isinstance(value, list):
            return [self._rec_str(v) for v in value]
        if isinstance(value, Container | Deque):
            return {key: self._rec_str(value) for key, value in value if not key.startswith("__")}
        return value

    def __str__(self) -> str:
        return f"{self._rec_str(self.__deque)!s}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.__deque!r})"

    def __hash__(self) -> int:
        return hash(tuple(self.__deque))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Container):
            return False
        return self.__deque == other.__deque

    # CUSTOM GETATTR

    def set_parent(self, parent: "Container") -> None:
        self.__parent = parent

    @property
    def _(self) -> "Container[VT]":
        """
        Used to retrieve the parent stack if the structure isn't embedded.

        | opcode
        | --|
            | Switch(lambda packet: packet._.opcode, ...)
        """
        if self.__parent is None:
            raise AttributeError("Parent stack was never set, cannot retrieve value")
        return self.__parent

    def __getattr__(self, attr: str) -> VT:
        """
        Custom getattr method that also searches the dictionary for the attribute.
        Gets triggered upon failure to get attribute in the Self.
        """
        if attr in self.__slots__:
            return object.__getattribute__(self, attr)
        if attr in self:
            return self[attr]
        raise AttributeError(attr)

    def pprint(self, *, padding: str = "\t{t}{v:-^38}{t}\n", depth: int = 1) -> str:
        # RECURSIVE
        stack = ""
        for key, value in self:
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

    def __contains__(self, key: str) -> bool:
        return any(key == item.name for item in self._items)

    def __iter__(self) -> Generator[T]:
        yield from self._items

    def enumerate(self) -> Generator[tuple[int, T]]:
        yield from enumerate(self._items)


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
