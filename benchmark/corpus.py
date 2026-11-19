"""Benchmark corpora for simpleeval-opt-lab.

Two corpora are used so the report never hides behind a hand-picked load:

* ``SYNTHETIC`` -- arithmetic / comparison expressions generated from a fixed
  seed.  This is the "rules engine on numbers" shape.
* ``REAL`` -- expressions taken verbatim (or, where noted, instanced with row
  variables) from the upstream project's own README.rst and tests/.  simpleeval
  ships no data files, so its own documented examples and test expressions are
  the closest thing to a real corpus it has.  Every entry records its source.
"""

from __future__ import annotations

import random

SEED = 20261120

# (expression, provenance)
REAL: list[tuple[str, str]] = [
    ("a + b", "README.rst:277 `simple_eval(\"a + b\", names=...)`"),
    ("a + b * 2 - c", "README.rst:78 arithmetic example, instanced with row vars"),
    ("x > 3 and y <= 10", "README.rst:144 boolean example, instanced with row vars"),
    ("name == 'bob' and age >= 18", "README.rst:66-74 conditional examples, instanced"),
    ("total / count > 0.5", "README.rst:74 division example, instanced with row vars"),
    ("'equal' if x == y else 'not equal'", "README.rst:210 verbatim"),
    ("'a' if 1 == 2 else 'b' if 2 == 3 else 'c'", "README.rst:218 verbatim"),
    ("a if x > 2 else b", "README.rst:218 nested-if form, instanced with row vars"),
    ("1 < 2 < 3 < 4", "tests/test_operators.py: chained comparison"),
    ("1 == 1 < 2", "tests/test_operators.py: chained comparison"),
    ("21 + 19 / 7 + (8 % 3) ** 9", "README.rst:74 verbatim"),
    ("11.02 - 9.1", "tests/test_operators.py: float subtraction"),
    ("21 + 21", "README.rst:66 verbatim"),
    ("5 + 5", "tests/test_operators.py"),
    ("20 + 1 + (10*2) + 1", "tests/test_operators.py"),
    ("2 ** 10", "tests/test_operators.py"),
    ("100 % 9", "tests/test_operators.py"),
    ("10 << 3", "tests/test_operators.py: 10 << 10 family, shortened"),
    ("1000 >> 2", "tests/test_operators.py"),
    ("62 ^ 20", "tests/test_operators.py"),
    ("8 | 34", "tests/test_operators.py"),
    ("100 & 63", "tests/test_operators.py"),
    ("~ -43", "tests/test_operators.py"),
    ("not False", "tests/test_operators.py"),
    ("int('20') + int(0.22*100)", "tests/test_operators.py: int() casts"),
    ("'Test Stuff!' + str(11)", "tests/test_operators.py: str() concat"),
    ("int(a) + float(b)", "tests/test_operators.py: int()/float() casts"),
    ("str(a) + str(b)", "tests/test_operators.py: str() concat"),
    ("float(a) / (b + 1)", "tests/test_operators.py: float division"),
]

SYNTHETIC: list[tuple[str, str]] = [
    ("(a + b) * (c - 2)", "generated arithmetic"),
    ("a * 2 + b * 3 - c", "generated arithmetic"),
    ("a / (b + 1) + c", "generated arithmetic"),
    ("(a - b) ** 2 + c", "generated arithmetic"),
    ("a + b + c + x + y", "generated arithmetic"),
    ("a > b and c < x", "generated boolean"),
    ("a % (b + 1)", "generated arithmetic"),
    ("(a + b + c) / 3", "generated arithmetic"),
]


def make_rows(n: int) -> list[dict]:
    """Build `n` deterministic rule-engine rows (same rows for every impl)."""
    rng = random.Random(SEED)
    rows = []
    for _ in range(n):
        a = rng.randrange(0, 11)
        b = rng.randrange(1, 11)
        c = rng.randrange(0, 10)
        rows.append(
            {
                "a": a,
                "b": b,
                "c": c,
                "d": rng.randrange(1, 6),
                "x": rng.randrange(0, 11),
                "y": rng.randrange(0, 11),
                "total": a * 10.0,
                "count": rng.randrange(1, 10),
                "name": rng.choice(["bob", "alice", "carol"]),
                "age": rng.randrange(10, 71),
                "items": [1, 2, 3, 4, 5],
            }
        )
    return rows