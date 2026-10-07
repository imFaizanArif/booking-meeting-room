"""Safe expression language (ADR 0004)."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.enums import ErrorCode
from app.orchestration.expressions import ExpressionError, check_syntax, evaluate, jsonpath, resolve

JOBS = [{"id": "a", "rate": 85, "skills": ["py"]}, {"id": "b", "rate": 40, "skills": []},
        {"id": "c", "rate": 120, "skills": ["go"]}, "not-a-dict"]
NAMES: dict[str, Any] = {"input": {"min": 50, "tags": ["x"]}, "nodes": {"search": {"output": {"jobs": JOBS}}},
                         "vars": {"rate": "80"}}


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("=len(nodes.search.output.jobs) > 3", True),
        ("input.min * 2", 100),
        ("int(vars.rate) >= 80 and 'x' in input.tags", True),
        ("get(input, 'missing.path', 'fallback')", "fallback"),
        ("get(nodes, 'search.output.jobs.0.id')", "a"),
        ("pluck(filter_by(nodes.search.output.jobs, 'rate', '>=', input.min), 'id')", ["a", "c"]),
        ("pluck(nodes.search.output.jobs, 'rate')", [85, 40, 120]),
        ("filter_by(nodes.search.output.jobs, 'skills', 'contains', 'go')", [JOBS[2]]),
        ("first(pluck(nodes.search.output.jobs, 'id'))", "a"),
        ("first([], 'none')", "none"),
        ("any_of([False, 0, 1]) and not all_of([1, 0])", True),
        ("join(['a', 'b'], '-')", "a-b"),
        ("{'n': len(input.tags), 'up': upper('ok')}", {"n": 1, "up": "OK"}),
        ("keys(input)", ["min", "tags"]),
    ],
)
def test_evaluates_safely(expr: str, expected: Any) -> None:
    assert evaluate(expr, NAMES) == expected


def test_results_are_plain_python() -> None:
    value = evaluate("nodes.search.output", NAMES)
    assert type(value) is dict and type(value["jobs"][0]) is dict


@pytest.mark.parametrize(
    "expr",
    [
        "input.__class__",
        "input.__class__.__mro__",
        "().__class__.__bases__[0].__subclasses__()",
        "nodes.__dict__",
        "__import__('os').system('true')",
        "open('/etc/passwd').read()",
        "eval('1+1')",
        "input.missing",
        "1/0",
        "filter_by(nodes.search.output.jobs, 'rate', '~=', 1)",
        "",
        "x" * 2001,
    ],
)
def test_rejects_unsafe_or_invalid(expr: str) -> None:
    with pytest.raises(ExpressionError) as info:
        evaluate(expr, NAMES)
    assert info.value.code == ErrorCode.expression_error


def test_power_and_string_limits() -> None:
    with pytest.raises(ExpressionError):
        evaluate("9 ** 9 ** 9", {})
    with pytest.raises(ExpressionError):
        evaluate("'a' * 10000000", {})


def test_resolve_only_evaluates_prefixed_strings() -> None:
    template = {"id": "=first(pluck(nodes.search.output.jobs, 'id'))", "literal": "plain = text",
                "list": ["=input.min", 3], "nested": {"n": "=len(input.tags)"}}
    assert resolve(template, NAMES) == {"id": "a", "literal": "plain = text", "list": [50, 3], "nested": {"n": 1}}


def test_jsonpath_and_syntax_check() -> None:
    assert jsonpath(NAMES["nodes"], "$.search.output.jobs[?(@.rate > 80)].id") == ["a", "c"]
    with pytest.raises(ExpressionError):
        jsonpath({}, "$[")
    assert check_syntax("=len(x) > 1") is None
    assert check_syntax("len(x") is not None
