"""Safe expression language (ADR 0004).

simpleeval with compound types, a fixed function set and dot access into dicts:
    nodes.search_jobs.output.jobs
    len(nodes.filter.output.shortlist) > 0
    filter_by(nodes.search.output.jobs, "hourly_rate", ">=", vars.min_rate)
"""

from __future__ import annotations

import json
import operator
from datetime import UTC, datetime
from typing import Any

from jsonpath_ng.ext import parse as jsonpath_parse
from simpleeval import EvalWithCompoundTypes, InvalidExpression

from app.core.enums import ErrorCode
from app.core.errors import AppError

EXPR_PREFIX = "="
_MAX_EXPR = 2000


class ExpressionError(AppError):
    code = ErrorCode.expression_error


class DotDict(dict[str, Any]):
    """dict with attribute access, so expressions can write a.b.c."""

    def __getattr__(self, name: str) -> Any:
        try:
            return wrap(self[name])
        except KeyError as exc:
            raise AttributeError(name) from exc


def wrap(value: Any) -> Any:
    if isinstance(value, DotDict):
        return value
    if isinstance(value, dict):
        return DotDict(value)
    if isinstance(value, list):
        return [wrap(v) for v in value]
    return value


def unwrap(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [unwrap(v) for v in value]
    return value


_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: b in (a or []),
}


def _filter_by(items: list[Any], field: str, op: str, value: Any) -> list[Any]:
    fn = _OPS.get(op)
    if fn is None:
        raise ExpressionError(f"Unknown operator {op!r} in filter_by")
    return [i for i in (items or []) if isinstance(i, dict) and fn(i.get(field), value)]


def _get(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return default
    return cur


FUNCTIONS: dict[str, Any] = {
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "min": min,
    "max": max,
    "sum": sum,
    "round": round,
    "abs": abs,
    "sorted": sorted,
    "list": list,
    "lower": lambda s: str(s).lower(),
    "upper": lambda s: str(s).upper(),
    "contains": lambda container, item: item in (container or []),
    "keys": lambda d: list((d or {}).keys()),
    "get": _get,
    "filter_by": _filter_by,
    "pluck": lambda items, field: [i.get(field) for i in (items or []) if isinstance(i, dict)],
    "first": lambda items, default=None: (items or [default])[0],
    "join": lambda items, sep=", ": sep.join(str(i) for i in (items or [])),
    "to_json": lambda v: json.dumps(unwrap(v), default=str),
    "now_iso": lambda: datetime.now(UTC).isoformat(),
    "enumerate": lambda items: list(enumerate(items or [])),
    "zip": lambda *lists: list(zip(*lists, strict=False)),
    "any_of": lambda items: any(items or []),
    "all_of": lambda items: all(items or []),
}


def evaluate(expression: str, names: dict[str, Any]) -> Any:
    expr = expression.strip()
    if expr.startswith(EXPR_PREFIX):
        expr = expr[1:].strip()
    if not expr:
        raise ExpressionError("Expression is empty")
    if len(expr) > _MAX_EXPR:
        raise ExpressionError("Expression is too long", details={"limit": _MAX_EXPR})
    evaluator = EvalWithCompoundTypes(names={k: wrap(v) for k, v in names.items()}, functions=FUNCTIONS)
    try:
        return unwrap(evaluator.eval(expr))
    except (
        InvalidExpression,
        AttributeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        ZeroDivisionError,
        SyntaxError,
    ) as exc:
        raise ExpressionError(
            f"Cannot evaluate {expr!r}: {exc.__class__.__name__}: {exc}", details={"expression": expr}
        ) from exc


def resolve(value: Any, names: dict[str, Any]) -> Any:
    """Resolve an argument/template structure: `=expr` strings are evaluated, the rest is literal."""
    if isinstance(value, str) and value.startswith(EXPR_PREFIX):
        return evaluate(value, names)
    if isinstance(value, dict):
        return {k: resolve(v, names) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, names) for v in value]
    return value


def jsonpath(document: Any, path: str) -> list[Any]:
    try:
        expr = jsonpath_parse(path)
    except Exception as exc:
        raise ExpressionError(f"Invalid JSONPath {path!r}: {exc}") from exc
    return [m.value for m in expr.find(unwrap(document))]


def check_syntax(expression: str) -> str | None:
    """Return an error message if the expression cannot be parsed, else None."""
    expr = expression.strip().removeprefix(EXPR_PREFIX).strip()
    try:
        compile(expr, "<expr>", "eval")
    except SyntaxError as exc:
        return f"Syntax error: {exc.msg}"
    return None
