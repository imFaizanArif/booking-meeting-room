"""Sandboxed prompt rendering."""

from __future__ import annotations

import pytest

from app.core.enums import ErrorCode
from app.prompts.render import TemplateError, preview, referenced_variables, render


def test_renders_variables_loops_and_filters() -> None:
    out = render(
        "Hi {{ name }}.{% for s in skills %} [{{ s | upper }}]{% endfor %} {{ data | tojson }}",
        {"name": "Sam", "skills": ["py", "sql"], "data": {"a": 1}},
    )
    assert out == 'Hi Sam. [PY] [SQL] {"a": 1}'
    assert render("{{ text | truncate_chars(3) }}", {"text": "abcdef"}) == "abc…"


def test_missing_variables_are_listed() -> None:
    with pytest.raises(TemplateError) as info:
        render("{{ a }} {{ b.c }} {{ present }}", {"present": 1})
    assert info.value.code == ErrorCode.template_error
    assert info.value.details == {"missing": ["a", "b"]}
    assert "a, b" in info.value.message


def test_undefined_nested_value_fails_strictly() -> None:
    with pytest.raises(TemplateError, match="undefined"):
        render("{{ user.nickname }}", {"user": {"name": "x"}})


@pytest.mark.parametrize(
    "source",
    [
        "{{ ''.__class__ }}",
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ obj.__dict__ }}",
        "{{ cycler.__init__.__globals__ }}",
        "{{ lipsum.__globals__['os'] }}",
        "{% set x = [].append(1) %}{{ x }}",
        "{{ {}.update({'a': 1}) }}",
    ],
)
def test_sandbox_blocks_escapes(source: str) -> None:
    context = {"obj": object(), "cycler": None, "lipsum": None}
    with pytest.raises(TemplateError):
        render(source, context)


def test_syntax_errors_are_template_errors() -> None:
    with pytest.raises(TemplateError) as info:
        referenced_variables("{% if x %}unterminated")
    assert "line" in info.value.details


def test_referenced_variables_and_preview() -> None:
    assert referenced_variables("{{ a }}{% for i in items %}{{ i }}{% endfor %}") == {"a", "items"}
    output, missing, error = preview("Hello {{ name }} from {{ city }}", {"name": "Sam"})
    assert (output, missing, error) == ("Hello Sam from {{city}}", ["city"], None)
    assert preview("{{ ''.__class__ }}", {})[2] is not None
