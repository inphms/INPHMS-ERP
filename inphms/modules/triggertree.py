from __future__ import annotations
import typing as t

from collections import defaultdict

from inphms.tools import OrderedSet

if t.TYPE_CHECKING:
    from inphms.orm.fields import Field
    from collections.abc import Collection, Iterator, Callable


class TriggerTree(dict['Field', 'TriggerTree']):
    """ The triggers of a field F is a tree that contains the fields that
        depend on F, together with the fields to inverse to find out which records
        to recompute.

        For instance, assume that G depends on F, H depends on X.F, I depends on
        W.X.F, and J depends on Y.F. The triggers of F will be the tree:

                                    [G]
                                X/   \\Y
                                [H]     [J]
                            W/
                            [I]

        This tree provides perfect support for the trigger mechanism:
        when F is # modified on records,
        - mark G to recompute on records,
        - mark H to recompute on inverse(X, records),
        - mark I to recompute on inverse(W, inverse(X, records)),
        - mark J to recompute on inverse(Y, records).
    """
    __slots__ = ['root']
    root: Collection[Field]

    # pylint: disable=keyword-arg-before-vararg
    def __init__(self, root: Collection[Field] = (), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root = root

    def __bool__(self) -> bool:
        return bool(self.root or len(self))

    def __repr__(self) -> str:
        return f"TriggerTree(root={self.root!r}, {super().__repr__()})"

    def increase(self, key: Field) -> TriggerTree:
        try:
            return self[key]
        except KeyError:
            subtree = self[key] = TriggerTree()
            return subtree

    def depth_first(self) -> Iterator[TriggerTree]:
        yield self
        for subtree in self.values():
            yield from subtree.depth_first()

    @classmethod
    def merge(cls, trees: list[TriggerTree], select: Callable[[Field], bool] = bool) -> TriggerTree:
        """ Merge trigger trees into a single tree. The function ``select`` is
        called on every field to determine which fields should be kept in the
        tree nodes. This enables to discard some fields from the tree nodes.
        """
        root_fields: OrderedSet[Field] = OrderedSet()              # fields in the root node
        subtrees_to_merge = defaultdict(list)   # subtrees to merge grouped by key

        for tree in trees:
            root_fields.update(tree.root)
            for label, subtree in tree.items():
                subtrees_to_merge[label].append(subtree)

        # the root node contains the collected fields for which select is true
        result = cls([field for field in root_fields if select(field)])
        for label, subtrees in subtrees_to_merge.items():
            subtree = cls.merge(subtrees, select)
            if subtree:
                result[label] = subtree

        return result
