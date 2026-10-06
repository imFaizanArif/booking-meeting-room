# ADR 0004: Expression language for Condition / Transform / argument mapping

- Status: accepted

## Decision
A sandboxed **simpleeval** evaluator with a fixed set of functions (`len`, `lower`,
`upper`, `contains`, `int`, `float`, `str`, `bool`, `min`, `max`, `sum`, `round`,
`any_of`, `all_of`, `keys`, `get`), plus **JSONPath** (`jsonpath-ng`) for Transform nodes in
`jsonpath` mode, plus `filter`/`map` helpers that take a lambda-free field predicate.
Names visible to expressions: `input`, `nodes` (upstream outputs), `item` (map element),
`vars` (workspace prompt variables).

## Reason
Python `eval` is unsafe. simpleeval parses with `ast`, rejects attribute access to dunder
names, imports, comprehensions over unbounded ranges and lambdas, and caps power/string
sizes. Its syntax is familiar to operators (`nodes.filter.output.count > 3`).

## Trade-off
Less expressive than JSONata or JMESPath for deep reshaping. Transform nodes offer a
JSONPath mode for selection and an object-template mode (a JSON object whose leaf strings
are expressions) for reshaping, which covers the demo and common cases.
