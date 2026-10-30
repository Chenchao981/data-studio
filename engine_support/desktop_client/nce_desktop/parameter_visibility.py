"""Analysis-only parameter visibility; never rewrite measurement artifacts."""
from functools import wraps
import re
import unicodedata


_CONTROL = re.compile(r"^CONT(?=$|[^A-Z])", re.ASCII)


def is_analysis_parameter(name):
    normalized = unicodedata.normalize("NFKC", str(name)).strip().upper()
    return _CONTROL.match(normalized) is None


def visible_parameter_names(names):
    """Keep original names, order and duplicates; only exclude CONT items."""
    return [name for name in names if is_analysis_parameter(name)]


def analysis_parameter_result(function):
    @wraps(function)
    def visible(*args, **kwargs):
        return visible_parameter_names(function(*args, **kwargs))
    return visible
