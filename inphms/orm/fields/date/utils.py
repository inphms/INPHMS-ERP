from __future__ import annotations
import dateutil.relativedelta

from datetime import date, datetime

from inphms import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT as DATETIME_FORMAT

from ...utils import READ_GROUP_TIME_GRANULARITY, READ_GROUP_NUMBER_GRANULARITY

DATE_LENGTH = len(date.today().strftime(DATE_FORMAT))
DATETIME_LENGTH = len(datetime.now().strftime(DATETIME_FORMAT))


def parse_field_expr(field_expr: str) -> tuple[str, str | None]:
    if (property_index := field_expr.find(".")) >= 0:
        property_name = field_expr[property_index + 1:]
        field_expr = field_expr[:property_index]
    else:
        property_name = None
    if not field_expr:
        raise ValueError(f"Invalid field expression {field_expr!r}")
    return field_expr, property_name