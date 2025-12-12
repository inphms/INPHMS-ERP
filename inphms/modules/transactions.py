from __future__ import annotations
import typing as t
import logging

from weakref import WeakSet
from collections import defaultdict
from contextlib import suppress

from .registry import Registry
from .environments import Environment
from .cache import Cache
from inphms.tools import OrderedSet, StackMap, reset_cached_properties

if t.TYPE_CHECKING:
    from inphms.orm.fields import Field, IdType

_logger = logging.getLogger(__name__)

class Transaction:
    """ A object holding ORM data structures for a transaction. """
    __slots__ = (
        '_Transaction__file_open_tmp_paths', 'cache',
        'default_env', 'envs', 'field_data', 'field_data_patches', 'field_dirty',
        'protected', 'registry', 'tocompute',
    )

    def __init__(self, registry: Registry):
        self.registry = registry
        # weak OrderedSet of environments
        self.envs = WeakSet[Environment]()
        self.envs.data = OrderedSet()  # type: ignore[attr-defined]
        # default environment (for flushing)
        self.default_env: Environment | None = None

        # cache data {field: cache_data_managed_by_field} often uses a dict
        # to store a mapping from id to a value, but fields may use this field
        # however they need
        self.field_data = defaultdict["Field", t.Any](dict)
        # {field: set[id]} stores the fields and ids that are changed in the
        # cache, but not yet written in the database; their changed values are
        # in `data`
        self.field_dirty = defaultdict["Field", OrderedSet["IdType"]](OrderedSet)
        # {field: {record_id: ids}} record ids to be added to the values of
        # x2many fields if they are not in cache yet
        self.field_data_patches = defaultdict["Field", defaultdict["IdType", list["IdType"]]](lambda: defaultdict(list))
        # fields to protect {field: ids}
        self.protected = StackMap["Field", OrderedSet["IdType"]]()
        # pending computations {field: ids}
        self.tocompute = defaultdict["Field", OrderedSet["IdType"]](OrderedSet)
        # backward-compatible view of the cache
        self.cache = Cache(self)

        # temporary directories (managed in inphms.tools.file_open_temporary_directory)
        self.__file_open_tmp_paths = ()  # type: ignore # noqa: PLE0237

    def flush(self) -> None:
        """ Flush pending computations and updates in the transaction. """
        if self.default_env is not None:
            self.default_env.flush_all()
        else:
            for env in self.envs:
                _logger.warning("Missing default_env, flushing as public user")
                public_user = env.ref('base.public_user')
                Environment(env.cr, public_user.id, {}).flush_all()
                break

    def clear(self):
        """ Clear the caches and pending computations and updates in the transactions. """
        self.invalidate_field_data()
        self.field_data_patches.clear()
        self.field_dirty.clear()
        self.tocompute.clear()
        for env in self.envs:
            env.cr.cache.clear()
            break  # all envs of the transaction share the same cursor

    def reset(self) -> None:
        """ Reset the transaction.  This clears the transaction, and reassigns
            the registry on all its environments.  This operation is strongly
            recommended after reloading the registry.
        """
        self.registry = Registry(self.registry.db_name)
        for env in self.envs:
            reset_cached_properties(env)
        self.clear()

    def invalidate_field_data(self) -> None:
        """ Invalidate the cache of all the fields.

            This operation is unsafe by default, and must be used with care.
            Indeed, invalidating a dirty field on a record may lead to an error,
            because doing so drops the value to be written in database.
        """
        self.field_data.clear()
        # reset Field._get_cache()
        for env in self.envs:
            with suppress(AttributeError):
                del env._field_cache_memo
