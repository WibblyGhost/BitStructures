from collections.abc import Generator
from copy import copy
from enum import Enum as Enum_
from typing import Any, Self, SupportsIndex, override

from bitstructures.constants import PP_DETENT, PP_INDENT, PP_TAB
from bitstructures.exceptions import FrozenError
from bitstructures.typing import SupportsName


class FrozenSlots:
    """
    Used to create a frozen class which cannot be modified after
    setting it as frozen.
    """

    __slots__ = ("_frozen",)

    def __init__(self) -> None:
        self._frozen: bool = False

    def freeze(self) -> None:
        """Sets the frozen state, disallowing modification to the underlying class."""
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


class Container[VT: Any = Any](dict[str, VT]):  # noqa: PLW1641
    """
    Wrapper for a dictionary-like object, we use this to add extra functionality to
    the container indexing, and adding frozen attributes to the setters.

    You can access container attributes like normal `container["id"]` or via
    direct access `container.id`.
    """

    __slots__ = ("__parent",)  # store only the extra attribute, no __dict__

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:  # noqa: D102
        # Needed for deepcopy
        class_ = dict.__new__(cls, *args, **kwargs)
        class_.__parent = None  # noqa: SLF001
        return class_

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        dict.update(self, *args, **kwargs)
        self.__parent: Container[VT] | None = None

    def __copy__(self) -> "Container[VT]":
        """Create a new Container and keep references to all values in the object."""
        cls = type(self)()
        cls.update(self.items())
        if self.__parent is not None:
            cls.set_parent(self.__parent)
        return cls

    def copy(self) -> "Container[VT]":
        """Create a new Container and keep references to all values in the object."""
        return copy(self)

    def __eq__(self, other: object, /) -> bool:
        if self is other:
            return True
        if not isinstance(other, dict):
            return False
        return self.items() == other.items()

    def __repr__(self) -> str:
        items = {
            k: v
            for k, v in self.items()
            if not (k.startswith("__") or k.startswith(f"_{self.__class__.__name__}"))
        }
        return repr(items)

    def set_parent(self, parent: "Container") -> None:
        """Sets the parent Container object allowing accessing the parent's attributes."""
        assert isinstance(parent, Container)
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
        if attr in self:
            return self[attr]
        try:
            return object.__getattribute__(self, attr)
        except AttributeError as err:
            err.add_note(f"Attempted to access {attr} from the object {self!r}")
            err.add_note(f"Parent={self.__parent}")
            raise

    def set(self, name: str, value: VT) -> None:
        """Sets an item inside our dictionary to a value."""
        self[name] = value

    def pprint(self, *, padding: str = "\t{t}{v:-^38}{t}\n", depth: int = 1) -> str:
        """Returns a nice representation of this class with padding."""
        # RECURSIVE
        stack = ""
        for key, value in self.items():
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

    __slots__ = ("_items",)

    def __init__(self) -> None:
        self._items: list[T] = []
        super().__init__()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._items})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._items})"

    def __len__(self) -> int:
        return len(self._items)

    def pop(self, index: SupportsIndex = -1) -> T:
        """Remove an item from the top of the stack."""
        self._check_frozen()
        return self._items.pop(index)

    def set(self, index: SupportsIndex, value: T) -> None:
        """Modify an item at a given index in the stack."""
        self._check_frozen()
        self._items[index] = value

    @property
    def is_empty(self) -> bool:
        """Returns True if this Stack is empty."""
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
        """Push an item ontop of the stack."""
        self._check_frozen()
        self._validate_item(item)
        self._items.append(item)

    def __contains__(self, key: str) -> bool:
        return any(key == item.name for item in self._items)

    def __iter__(self) -> Generator[T]:
        yield from self._items

    def enumerate(self) -> Generator[tuple[int, T]]:
        """Returns a tuple given an index and item pair enumeration."""
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
