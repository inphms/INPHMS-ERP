from __future__ import annotations
import logging

_logger = logging.getLogger(__name__)


FLAG_MAPPING = {
    "GF": "fr",
    "BV": "no",
    "BQ": "nl",
    "GP": "fr",
    "HM": "au",
    "YT": "fr",
    "RE": "fr",
    "MF": "fr",
    "UM": "us",
}
NO_FLAG_COUNTRIES = [
    "AQ", #Antarctica
    "SJ", #Svalbard + Jan Mayen : separate jurisdictions : no dedicated flag
]