from __future__ import annotations
import typing as t
import collections

from collections import defaultdict
from collections.abc import Reversible
from itertools import islice
from .sentinel import Sentinel, SENTINEL

K = t.TypeVar('K')
T = t.TypeVar('T')
if t.TYPE_CHECKING:
    from collections.abc import Mapping, Iterable, Iterator, Sequence, Callable, Collection

    P = t.TypeVar('P')

__all__ = ["submap", "unique", "reverse_enumerate", "Callbacks", "split_every",
           "partition", "ReversedIterable", "topological_sort", "merge_sequences",
           "groupby"]


def submap(mapping: Mapping[K, T], keys: Iterable[K]) -> Mapping[K, T]:
    """ Return a new mapping with the specified keys and values. """
    keys = frozenset(keys)
    return {k: mapping[k] for k in mapping if k in keys}


def unique(it: Iterable[T]) -> Iterator[T]:
    seen = set()
    for e in it:
        if e not in seen:
            seen.add(e)
            yield e


def groupby(iterable: Iterable[T], key: Callable[[T], K] = lambda arg: arg) -> Iterable[tuple[K, list[T]]]:
    """ Return a collection of pairs ``(key, elements)`` from ``iterable``. The
        ``key`` is a function computing a key value for each element. This
        function is similar to ``itertools.groupby``, but aggregates all
        elements under the same key, not only consecutive elements.
    """
    groups = defaultdict(list)
    for elem in iterable:
        groups[key(elem)].append(elem)
    return groups.items()


def reverse_enumerate(lst: Sequence[T]) -> Iterator[tuple[int, T]]:
    return zip(range(len(lst) - 1, -1, -1), reversed(lst))


class Callbacks:
    """ A simple queue of callback functions.  Upon run, every function is
    called (in addition order), and the queue is emptied.

    ::

        callbacks = Callbacks()

        # add foo
        def foo():
            print("foo")

        callbacks.add(foo)

        # add bar
        callbacks.add
        def bar():
            print("bar")

        # add foo again
        callbacks.add(foo)

        # call foo(), bar(), foo(), then clear the callback queue
        callbacks.run()

    The queue also provides a ``data`` dictionary, that may be freely used to
    store anything, but is mostly aimed at aggregating data for callbacks.  The
    dictionary is automatically cleared by ``run()`` once all callback functions
    have been called.

    ::

        # register foo to process aggregated data
        @callbacks.add
        def foo():
            print(sum(callbacks.data['foo']))

        callbacks.data.setdefault('foo', []).append(1)
        ...
        callbacks.data.setdefault('foo', []).append(2)
        ...
        callbacks.data.setdefault('foo', []).append(3)

        # call foo(), which prints 6
        callbacks.run()

    Given the global nature of ``data``, the keys should identify in a unique
    way the data being stored.  It is recommended to use strings with a
    structure like ``"{module}.{feature}"``.
    """
    __slots__ = ['_funcs', 'data']

    def __init__(self):
        self._funcs: collections.deque[Callable] = collections.deque()
        self.data = {}

    def add(self, func: Callable) -> None:
        """ Add the given function. """
        self._funcs.append(func)

    def run(self) -> None:
        """ Call all the functions (in addition order), then clear associated data.
        """
        while self._funcs:
            func = self._funcs.popleft()
            func()
        self.clear()

    def clear(self) -> None:
        """ Remove all callbacks and data from self. """
        self._funcs.clear()
        self.data.clear()


@t.overload
def split_every(n: int, iterable: Iterable[T]) -> Iterator[tuple[T, ...]]:
    ...


@t.overload
def split_every(n: int, iterable: Iterable[T], piece_maker: type[Collection[T]]) -> Iterator[Collection[T]]:
    ...


@t.overload
def split_every(n: int, iterable: Iterable[T], piece_maker: Callable[[Iterable[T]], P]) -> Iterator[P]:
    ...


def split_every(n: int, iterable: Iterable[T], piece_maker=tuple):
    """Splits an iterable into length-n pieces. The last piece will be shorter
       if ``n`` does not evenly divide the iterable length.

       :param int n: maximum size of each generated chunk
       :param Iterable iterable: iterable to chunk into pieces
       :param piece_maker: callable taking an iterable and collecting each
                           chunk from its slice, *must consume the entire slice*.
    """
    iterator = iter(iterable)
    piece = piece_maker(islice(iterator, n))
    while piece:
        yield piece
        piece = piece_maker(islice(iterator, n))


def partition(pred: Callable[[T], bool], elems: Iterable[T]) -> tuple[list[T], list[T]]:
    """ Return a pair equivalent to:
        ``filter(pred, elems), filter(lambda x: not pred(x), elems)``
    """
    yes: list[T] = []
    nos: list[T] = []
    for elem in elems:
        (yes if pred(elem) else nos).append(elem)
    return yes, nos


class ReversedIterable(Reversible[T], t.Generic[T]):
    """ An iterable implementing the reversal of another iterable. """
    __slots__ = ['iterable']

    def __init__(self, iterable: Reversible[T]):
        self.iterable = iterable

    def __iter__(self):
        return reversed(self.iterable)

    def __reversed__(self):
        return iter(self.iterable)


def topological_sort(elems: Mapping[T, Collection[T]]) -> list[T]:
    """ Return a list of elements sorted so that their dependencies are listed
        before them in the result.

        :param elems: specifies the elements to sort with their dependencies; it is
            a dictionary like `{element: dependencies}` where `dependencies` is a
            collection of elements that must appear before `element`. The elements
            of `dependencies` are not required to appear in `elems`; they will
            simply not appear in the result.

        :returns: a list with the keys of `elems` sorted according to their
            specification.
    """
    # the algorithm is inspired by [Tarjan 1976],
    # http://en.wikipedia.org/wiki/Topological_sorting#Algorithms
    result = []
    visited = set()

    def visit(n):
        if n not in visited:
            visited.add(n)
            if n in elems:
                # first visit all dependencies of n, then append n to result
                for it in elems[n]:
                    visit(it)
                result.append(n)

    for el in elems:
        visit(el)

    return result


def merge_sequences(*iterables: Iterable[T]) -> list[T]:
    """ Merge several iterables into a list. The result is the union of the
        iterables, ordered following the partial order given by the iterables,
        with a bias towards the end for the last iterable::

            seq = merge_sequences(['A', 'B', 'C'])
            assert seq == ['A', 'B', 'C']

            seq = merge_sequences(
                ['A', 'B', 'C'],
                ['Z'],                  # 'Z' can be anywhere
                ['Y', 'C'],             # 'Y' must precede 'C';
                ['A', 'X', 'Y'],        # 'X' must follow 'A' and precede 'Y'
            )
            assert seq == ['A', 'B', 'X', 'Y', 'C', 'Z']
    """
    # dict is ordered
    deps: defaultdict[T, list[T]] = defaultdict(list)  # {item: elems_before_item}
    for iterable in iterables:
        prev: T | Sentinel = SENTINEL
        for item in iterable:
            if prev is SENTINEL:
                deps[item]  # just set the default
            else:
                deps[item].append(prev)
            prev = item
    return topological_sort(deps)
