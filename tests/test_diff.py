#!/usr/bin/env python3
"""Differential test: baseline vs parse-cache implementation.

Every sample is a (evaluator, expression, names) triple.  Both implementations
must produce byte-identical output: success values are reduced to
``("ok", module, qualname, repr(value))`` and exceptions to
``("err", type, str(msg))``; the two strings are compared with ``==``.

Samples are deduplicated with sha256 over the canonical sample key, so the
reported count is the number of *independent* samples, not loop iterations.

Also checked:
  * the cached AST is not mutated by evaluation (``ast.dump`` before/after),
  * a second evaluation of the same sample (cache-hit path) is identical,
  * boundary inputs (empty/whitespace/syntax-error/overlong strings,
    disallowed modules, division by zero, non-ASCII, None) agree.

Usage:  python tests/test_diff.py
Exit 0 iff at least 1000 unique samples and zero mismatches.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "benchmark"))

import corpus  # noqa: E402

SEED = 20261120
sys.set_int_max_str_digits(0)  # huge ints are legal values; repr must round-trip


def load(impl: str):
    path = ROOT / "impl" / impl / "simpleeval.py"
    spec = importlib.util.spec_from_file_location(f"simpleeval_{impl}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def canon_names(row) -> str:
    if callable(row):
        return "<callable>"
    return json.dumps(row, sort_keys=True, ensure_ascii=False, default=repr)


def outcome(fn) -> str:
    try:
        value = fn()
    except BaseException as exc:  # noqa: BLE001 - parity means parity
        return f"err|{type(exc).__name__}|{exc}"
    return f"ok|{type(value).__module__}.{type(value).__qualname__}|{value!r}"


def build_samples(base, opt):
    rng = random.Random(SEED)
    rows = corpus.make_rows(40)
    boundary_rows = [
        {},
        {"a": 0, "b": 0, "c": 0, "x": 0, "y": 0, "total": 0, "count": 1,
         "name": "", "age": 0, "items": []},
        {"a": 2**63, "b": -1, "c": 1, "x": 10**30, "y": -10**30,
         "total": 1e308, "count": 3, "name": "héllo 世界", "age": 200,
         "items": [None, True, 3.5]},
        {"变量": 1, "a": 1},
        {"a": True, "b": False, "c": None, "x": float("nan"), "y": float("inf"),
         "total": float("-inf"), "count": 2, "name": "\x00nul", "age": -1,
         "items": (1, 2)},
    ]
    boundary_exprs = [
        "", "   ", "1 +", "(", "a", "None", "True and None", "1 / 0",
        "a / 0", "undefined_name + 1", "1 if 0 else 0", "'x' * 10**6",
        "'a' + \"\\x00\"", "a < b < c < x < y", "not not not False",
        "1 << 100", "~(1 << 100)", "[1, 2, 3][1]", "{'a': 1}['a']",
        "(1, 2)[0]", "a if b else c if x else y", "int('  42  ')",
        "round(3.14159, 2)", "abs(-10) + min(1, 2) + max(3, 4)",
    ]
    exprs = [e for e, _ in corpus.REAL] + [e for e, _ in corpus.SYNTHETIC] + boundary_exprs
    # generated arithmetic / comparison expressions (fresh strings, fixed seed)
    atoms = ["a", "b", "c", "x", "y", "total", "count", "1", "2", "3.5"]
    ops = ["+", "-", "*", "/", "%", "<", ">", "==", "!="]  # no **: exponent towers explode
    for _ in range(240):
        n = rng.randrange(1, 4)
        parts = [rng.choice(atoms)]
        for _ in range(n):
            parts.append(rng.choice(ops))
            parts.append(rng.choice(atoms))
        exprs.append(" ".join(parts))
    exprs = list(dict.fromkeys(exprs))  # order-preserving text dedup

    seen: dict[str, tuple] = {}
    for expr in exprs:
        if "'x' * 10**6" == expr:
            row_pool = [{}]  # overlong literal: no names needed
        else:
            row_pool = rows + boundary_rows
        for row in row_pool:
            key = hashlib.sha256((expr + "\x00" + canon_names(row)).encode()).hexdigest()
            if key in seen:
                continue
            seen[key] = (expr, row)
    return list(seen.values())


def main() -> int:
    base = load("baseline")
    opt = load("optimized")
    samples = build_samples(base, opt)

    mismatches = []
    cache_hits = 0
    ast_checked = 0
    for expr, row in samples:
        if isinstance(row, dict) and "变量" in row:
            # simpleeval names must be str-keyed; this row only exercises the
            # name-error path, which is fine.
            pass
        eff_base = outcome(lambda: base.simple_eval(expr, names=row))
        eff_opt = outcome(lambda: opt.simple_eval(expr, names=row))
        eff_opt2 = outcome(lambda: opt.simple_eval(expr, names=row))  # cache hit
        if eff_base != eff_opt:
            mismatches.append((expr, canon_names(row), eff_base, eff_opt))
        if eff_opt != eff_opt2:
            cache_hits += 1  # second pass differed -> also a mismatch
            mismatches.append((expr, canon_names(row), eff_opt, eff_opt2))

        # AST immutability: parse through the optimised module, dump, evaluate,
        # dump again; the two dumps must be identical.  Expressions that do not
        # parse are covered by the outcome comparison above.
        try:
            tree = opt.SimpleEval.parse(expr)
        except Exception:  # noqa: BLE001 - syntax errors are compared above
            pass
        else:
            before = ast.dump(tree, include_attributes=False)
            outcome(lambda: opt.simple_eval(expr, names=row))
            after = ast.dump(tree, include_attributes=False)
            if before != after:
                mismatches.append((expr, canon_names(row), "AST", "mutated"))
            ast_checked += 1

    print(f"unique_samples={len(samples)}")
    print(f"comparisons={len(samples) * 3}")
    print(f"mismatches={len(mismatches)}")
    print(f"second_pass_differences={cache_hits}")
    print(f"ast_immutability_checked={ast_checked}")
    if mismatches:
        for m in mismatches[:10]:
            print("MISMATCH:", m)
        return 1
    if len(samples) < 1000:
        print(f"FAIL: only {len(samples)} unique samples (<1000)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())