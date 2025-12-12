from __future__ import annotations
import typing as t
import logging

from operator import attrgetter

from inphms.orm.domains import Domain
from inphms.orm.utils import PREFETCH_MAX
from ..field import Field
from ..utils import COLLECTION_TYPES
from inphms.tools import unquote

if t.TYPE_CHECKING:
    from inphms.tools import Collector
    from ...types import DomainType, ContextType
    from inphms.modules import Environment, Registry
    from ...models import BaseModel

_logger = logging.getLogger("inphms.fields")


class _Relational(Field["BaseModel"]):
    """ Abstract class for relational fields. """
    relational: t.Literal[True] = True
    comodel_name: str
    domain: DomainType = []         # domain for searching values
    context: ContextType = {}       # context for searching values
    bypass_search_access: bool = False  # whether access rights are bypassed on the comodel
    check_company: bool = False

    def __get__(self, records: BaseModel, owner=None):
        # base case: do the regular access
        if records is None or len(records._ids) <= 1:
            return super().__get__(records, owner)

        records._check_field_access(self, 'read')

        # multi-record case
        if self.compute and self.store:
            self.recompute(records)

        # get the cache
        env = records.env
        field_cache = self._get_cache(env)

        # retrieve values in cache, and fetch missing ones
        vals = []
        for record_id in records._ids:
            try:
                vals.append(field_cache[record_id])
            except KeyError:
                if self.store and record_id and len(vals) < len(records) - PREFETCH_MAX:
                    # a lot of missing records, just fetch that field
                    remaining = records[len(vals):]
                    remaining.fetch([self.name])
                else:
                    remaining = records.__class__(env, (record_id,), records._prefetch_ids)
                    super().__get__(remaining, owner)
                # we have the record now
                vals.append(field_cache[record_id])

        return self.convert_to_record_multi(vals, records)

    def _update_inverse(self, records: BaseModel, value: BaseModel):
        """ Update the cached value of ``self`` for ``records`` with ``value``. """
        raise NotImplementedError

    def convert_to_record_multi(self, values, records):
        """ Convert a list of (relational field) values from the cache format to
        the record format, for the sake of optimization.
        """
        raise NotImplementedError

    def setup_nonrelated(self, model: BaseModel):
        super().setup_nonrelated(model)
        assert self.comodel_name in model.pool, \
            f"Field {self} with unknown comodel_name {self.comodel_name or '???'!r}"

    def setup_inverses(self, registry: Registry, inverses: Collector[Field, Field]):
        """ Populate ``inverses`` with ``self`` and its inverse fields. """

    def get_comodel_domain(self, model: BaseModel) -> Domain:
        """ Return a domain from the domain attribute. """
        domain = self.domain
        if callable(domain):
            # the callable can return either a list, Domain or a string
            domain = domain(model)
        if not domain or isinstance(domain, str):
            # if we don't have a domain or
            # domain=str is used only for the client-side
            return Domain.TRUE
        return Domain(domain)

    @property
    def _related_domain(self) -> DomainType | None:
        def validated(domain):
            if isinstance(domain, str) and not self.inherited:
                # string domains are expressions that are not valid for self's model
                return None
            return domain

        if callable(self.domain):
            # will be called with another model than self's
            return lambda recs: validated(self.domain(recs.env[self.model_name]))  # pylint: disable=not-callable
        else:
            return validated(self.domain)

    _related_context = property(attrgetter('context'))

    _description_relation = property(attrgetter('comodel_name'))
    _description_context = property(attrgetter('context'))

    def _description_domain(self, env: Environment) -> str | list:
        domain = self._internal_description_domain_raw(env)
        if self.check_company:
            field_to_check = None
            if self.company_dependent:
                cids = '[allowed_company_ids[0]]'
            elif self.model_name == 'res.company':
                # when using check_company=True on a field on 'res.company', the
                # company_id comes from the id of the current record
                cids = '[id]'
            elif 'company_id' in env[self.model_name]:
                cids = '[company_id]'
                field_to_check = 'company_id'
            elif 'company_ids' in env[self.model_name]:
                cids = 'company_ids'
                field_to_check = 'company_ids'
            else:
                _logger.warning(
                    "Couldn't generate a company-dependent domain for field %s. "
                    "The model doesn't have a 'company_id' or 'company_ids' field, and isn't company-dependent either.",
                    self.model_name + '.' + self.name,
                )
                return domain
            company_domain = env[self.comodel_name]._check_company_domain(companies=unquote(cids))
            if not field_to_check:
                return f"{company_domain} + {domain or []}"
            else:
                no_company_domain = env[self.comodel_name]._check_company_domain(companies='')
                return f"({field_to_check} and {company_domain} or {no_company_domain}) + ({domain or []})"
        return domain

    def _description_allow_hierachy_operators(self, env):
        """ Return if the child_of/parent_of makes sense on this field """
        comodel = env[self.comodel_name]
        return comodel._parent_name in comodel._fields

    def _internal_description_domain_raw(self, env) -> str | list:
        domain = self.domain
        if callable(domain):
            domain = domain(env[self.model_name])
        if isinstance(domain, Domain):
            domain = list(domain)
        return domain or []

    def filter_function(self, records, field_expr, operator, value):
        getter = self.expression_getter(field_expr)

        if (self.bypass_search_access or operator == 'any!') and not records.env.su:
            # When filtering with bypass access, search the corecords with sudo
            # and a special key in the context. To evaluate sub-domains, the
            # special key makes the environment un-sudoed before evaluation.
            expr_getter = getter
            sudo_env = records.sudo().with_context(filter_function_reset_sudo=True).env
            getter = lambda rec: expr_getter(rec.with_env(sudo_env))  # noqa: E731

        corecords = getter(records)
        if operator in ('any', 'any!'):
            assert isinstance(value, Domain)
            if operator == 'any' and records.env.context.get('filter_function_reset_sudo'):
                corecords = corecords.sudo(False)._filtered_access('read')
            corecords = corecords.filtered_domain(value)
        elif operator == 'in' and isinstance(value, COLLECTION_TYPES):
            value = set(value)
            if False in value:
                if not corecords:
                    # shortcut, we know none of records has a corecord
                    return lambda _: True
                if len(value) > 1:
                    value.discard(False)
                    filter_values = self.filter_function(records, field_expr, 'in', value)
                    return lambda rec: not getter(rec) or filter_values(rec)
                return lambda rec: not getter(rec)
            corecords = corecords.filtered_domain(Domain('id', 'in', value))
        else:
            corecords = corecords.filtered_domain(Domain('id', operator, value))

        if not corecords:
            return lambda _: False

        ids = set(corecords._ids)
        return lambda rec: any(id_ in ids for val in getter(rec) for id_ in val._ids)
