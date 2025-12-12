from __future__ import annotations
import typing as t
import itertools

from functools import reduce
from collections.abc import Mapping, MutableSet, MutableMapping, Iterable

K = t.TypeVar('K')
T = t.TypeVar('T')
if t.TYPE_CHECKING:
    from collections.abc import Iterable, Collection, Iterator


__all__ = ["ReadonlyDict", "frozendict", "clean_context", "OrderedSet",
           "Collector", "StackMap", "LastOrderedSet", "is_list_of",
           "has_list_types", "DotDict", "ConstantMapping"]


class ReadonlyDict(Mapping[K, T], t.Generic[K, T]):
    """Helper for an unmodifiable dictionary, not even updatable using `dict.update`. """
    __slots__ = ('_data__',)

    def __init__(self, data):
        self._data__ = dict(data)

    def __contains__(self, key: K):  # type: ignore
        return key in self._data__

    def __getitem__(self, key: K) -> T:
        return self._data__[key]

    def __len__(self):
        return len(self._data__)

    def __iter__(self):
        return iter(self._data__)


class DotDict(dict):
    """Helper for dot.notation access to dictionary attributes

        E.g.
          foo = DotDict({'bar': False})
          return foo.bar
    """
    def __getattr__(self, attrib):
        val = self.get(attrib)
        return DotDict(val) if isinstance(val, dict) else val


class frozendict(dict[K, T], t.Generic[K, T]):
    """ An implementation of an immutable dictionary. """
    __slots__ = ()

    def __delitem__(self, key):
        raise NotImplementedError("'__delitem__' not supported on frozendict")

    def __setitem__(self, key, val):
        raise NotImplementedError("'__setitem__' not supported on frozendict")

    def clear(self):
        raise NotImplementedError("'clear' not supported on frozendict")

    def pop(self, key, default=None):
        raise NotImplementedError("'pop' not supported on frozendict")

    def popitem(self):
        raise NotImplementedError("'popitem' not supported on frozendict")

    def setdefault(self, key, default=None):
        raise NotImplementedError("'setdefault' not supported on frozendict")

    def update(self, *args, **kwargs):
        raise NotImplementedError("'update' not supported on frozendict")

    def __hash__(self) -> int:  # type: ignore
        return hash(frozenset((key, freehash(val)) for key, val in self.items()))


class OrderedSet(MutableSet[T], t.Generic[T]):
    """ A set collection that remembers the elements first insertion order. """
    __slots__ = ['_map']

    def __init__(self, elems: Iterable[T] = ()):
        self._map: dict[T, None] = dict.fromkeys(elems)

    def __contains__(self, elem):
        return elem in self._map

    def __iter__(self):
        return iter(self._map)

    def __len__(self):
        return len(self._map)

    def add(self, elem):
        self._map[elem] = None

    def discard(self, elem):
        self._map.pop(elem, None)

    def update(self, elems):
        self._map.update(zip(elems, itertools.repeat(None)))

    def difference_update(self, elems):
        for elem in elems:
            self.discard(elem)

    def __repr__(self):
        return f'{type(self).__name__}({list(self)!r})'

    def intersection(self, *others):
        return reduce(OrderedSet.__and__, others, self)


class LastOrderedSet(OrderedSet[T], t.Generic[T]):
    """ A set collection that remembers the elements last insertion order. """
    def add(self, elem):
        self.discard(elem)
        super().add(elem)


class Collector(dict[K, tuple[T, ...]], t.Generic[K, T]):
    """ A mapping from keys to tuples.  This implements a relation, and can be
        seen as a space optimization for ``defaultdict(tuple)``.
    """
    __slots__ = ()

    def __getitem__(self, key: K) -> tuple[T, ...]:
        return self.get(key, ())

    def __setitem__(self, key: K, val: Iterable[T]):
        val = tuple(val)
        if val:
            super().__setitem__(key, val)
        else:
            super().pop(key, None)

    def add(self, key: K, val: T):
        vals = self[key]
        if val not in vals:
            self[key] = vals + (val,)

    def discard_keys_and_values(self, excludes: Collection[K | T]) -> None:
        for key in excludes:
            self.pop(key, None)  # type: ignore
        for key, vals in list(self.items()):
            self[key] = tuple(val for val in vals if val not in excludes)  # type: ignore


class StackMap(MutableMapping[K, T], t.Generic[K, T]):
    """ A stack of mappings behaving as a single mapping, and used to implement
        nested scopes. The lookups search the stack from top to bottom, and
        returns the first value found. Mutable operations modify the topmost
        mapping only.
    """
    __slots__ = ['_maps']

    def __init__(self, m: MutableMapping[K, T] | None = None):
        self._maps = [] if m is None else [m]

    def __getitem__(self, key: K) -> T:
        for mapping in reversed(self._maps):
            try:
                return mapping[key]
            except KeyError:
                pass
        raise KeyError(key)

    def __setitem__(self, key: K, val: T):
        self._maps[-1][key] = val

    def __delitem__(self, key: K):
        del self._maps[-1][key]

    def __iter__(self) -> Iterator[K]:
        return iter({key for mapping in self._maps for key in mapping})

    def __len__(self) -> int:
        return sum(1 for key in self)

    def __str__(self) -> str:
        return f"<StackMap {self._maps}>"

    def pushmap(self, m: MutableMapping[K, T] | None = None):
        self._maps.append({} if m is None else m)

    def popmap(self) -> MutableMapping[K, T]:
        return self._maps.pop()


class ConstantMapping(Mapping[t.Any, T], t.Generic[T]):
    """
    An immutable mapping returning the provided value for every single key.

    Useful for default value to methods
    """
    __slots__ = ['_value']

    def __init__(self, val: T):
        self._value = val

    def __len__(self):
        """
        defaultdict updates its length for each individually requested key, is
        that really useful?
        """
        return 0

    def __iter__(self):
        """
        same as len, defaultdict updates its iterable keyset with each key
        requested, is there a point for this?
        """
        return iter([])

    def __getitem__(self, item) -> T:
        return self._value

##########
# HELPER #
##########
def freehash(arg: t.Any) -> int:
    try:
        return hash(arg)
    except Exception:
        if isinstance(arg, Mapping):
            return hash(frozendict(arg))
        elif isinstance(arg, Iterable):
            return hash(frozenset(freehash(item) for item in arg))
        else:
            return id(arg)


def clean_context(context: dict[str, t.Any]) -> dict[str, t.Any]:
    """ This function take a dictionary and remove each entry with its key
        starting with ``default_``
    """
    return {k: v for k, v in context.items() if not k.startswith('default_')}


def is_list_of(values, type_: type) -> bool:
    """Return True if the given values is a list / tuple of the given type.

    :param values: The values to check
    :param type_: The type of the elements in the list / tuple
    """
    return isinstance(values, (list, tuple)) and all(isinstance(item, type_) for item in values)


def has_list_types(values, types: tuple[type, ...]) -> bool:
    """Return True if the given values have the same types as
    the one given in argument, in the same order.

    :param values: The values to check
    :param types: The types of the elements in the list / tuple
    """
    return (
        isinstance(values, (list, tuple)) and len(values) == len(types)
        and all(itertools.starmap(isinstance, zip(values, types)))
    )