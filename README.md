# simpleeval-opt-lab

**simpleeval** is a tiny MIT-licensed safe expression evaluator (617★) for Python.
This lab makes its documented one-shot API — `simple_eval(expr, names=row)` called
once per row, i.e. a rule engine — about **1.78× faster** by caching the immutable
AST that `ast.parse()` rebuilds on every call. One mechanism, +15/−2 lines.

Upstream: https://github.com/danthedeckie/simpleeval

## What was changed

`SimpleEval.eval()` called `self.parse(expr)` — `ast.parse(expr.strip())` — on
every evaluation. The parse product depends only on the expression string, yet
the library hands users a per-call evaluator (`simple_eval()` constructs a fresh
`SimpleEval` for every call), so the same expression is re-parsed for every row.

The patch adds a bounded (`lru_cache`, 1024 entries) parse cache keyed by
`(evaluator class, expression)`. Two behaviours are preserved on purpose:

* an instance-level or subclass override of `parse()` is still honoured (an
  explicit `previously_parsed=` argument still short-circuits everything);
* the upstream test that monkey-patches `self.s.parse` to raise still sees the
  raise — the cache is only used when `parse` is the stock `SimpleEval.parse`
  and no instance attribute shadows it.

The cached tree is only read by the evaluator; the differential test re-dumps
the AST after evaluation to prove it is not mutated.

## Benchmark (median of 3 warmup + 7 timed samples, `time.perf_counter`)

Workload = the documented per-row API: for every row, evaluate a fixed rule set
with `simple_eval(expr, names=row)` (a fresh evaluator per call, exactly what
the library does). `rows` are deterministic (seed 20261120); every timed sample
is in `benchmark/raw/`.

### Real corpus — expressions from upstream `README.rst` / `tests/` (see `benchmark/corpus.py`,每条第 source)

| scale (rows × exprs) | baseline median | optimized median | speedup |
|---|---|---|---|
| small 100 × 29 = 2,900 evals | 63.128 ms | 35.521 ms | **1.777×** |
| medium 500 × 29 = 14,500 evals | 316.667 ms | 174.688 ms | **1.813×** |
| large 2,000 × 29 = 58,000 evals | 1,285.829 ms | 720.953 ms | **1.784×** |

Real-corpus median **1.784×**. (simpleeval ships no data files — its own
documented examples and test expressions are the closest real corpus it has;
each expression is annotated with its upstream source in `benchmark/corpus.py`.)

### Synthetic corpus — generated arithmetic/boolean expressions (`benchmark/corpus.py::SYNTHETIC`)

| scale | baseline median | optimized median | speedup |
|---|---|---|---|
| small 100 × 8 = 800 evals | 18.343 ms | 9.432 ms | **1.945×** |
| medium 500 × 8 = 4,000 evals | 91.473 ms | 49.387 ms | **1.852×** |
| large 2,000 × 8 = 16,000 evals | 365.191 ms | 191.745 ms | **1.905×** |

Synthetic median **1.905×**. Both numbers are reported because the synthetic
workload is the more favourable one; the real-corpus number is the headline.

**Noise:** all real-corpus scales have relative standard deviation <2%. The
synthetic medium optimized run has RSD **14.4%** (3.1–6.4% elsewhere); the host
is a shared 4-core VM, so CPU-frequency/steal variation and allocator noise
dominate that one cell. It does not move the median conclusion (1.905× vs 1.852×).

### G1–G5

| gate | result | reproduce |
|---|---|---|
| G1 upstream tests | **160 passed, 4 subtests passed**, 0 failed (pristine: same 160) | `cd /tmp/g1opt && python -m pytest tests -q` (patched file + upstream `tests/`) |
| G2 differential | **13,321 unique samples, 39,963 comparisons, 0 mismatches**, 0 second-pass differences, 13,141 AST-immutability checks | `python3 tests/test_diff.py` |
| G3 median speedup | **1.784×** real corpus (threshold 1.15×) | `python3 benchmark/bench.py --impl {baseline,optimized} --corpus real --scale medium` |
| G3b real corpus | **1.784×** ≥ 1.15× → `-opt-lab` naming is allowed | same command, all three scales |
| G4 largest scale | **1.784×** ≥ 0.95× | `python3 benchmark/bench.py --impl {baseline,optimized} --corpus real --scale large` |
| G5 peak RSS | 17,408 KB → 17,536 KB = **1.0074×** ≤ 1.10× (`/usr/bin/time -v`) | `/usr/bin/time -v python3 benchmark/bench.py --impl optimized --corpus real --scale large --samples 1 --warmup 0` |

**How the samples are made independent:** each sample is a
`(evaluator, expression, names)` triple; the key
`sha256(expr + "\x00" + canonical(names))` is deduplicated before running, so
the reported 13,321 is the number of *distinct* inputs, not loop iterations.
Outputs are compared as `("ok", module, qualname, repr(value))` or
`("err", ExceptionType, str(msg))` — exact string equality, no `approx`.
The corpus covers both `simple_eval()` and `EvalWithCompoundTypes`, generated
arithmetic, chained comparisons, non-ASCII names/values, `None`/NaN/inf/huge
ints, empty/whitespace/syntax-error expressions, overlong string literals,
disallowed modules via `names`, and division by zero.

**G1 honesty note:** the first version of the patch failed
`tests/test_evaluator.py::test_parse_and_use_previously_parsed` because that
test monkey-patches `self.s.parse` and asserts `eval()` calls it. The shipped
patch checks for that override and bypasses the cache, so the mock contract is
kept — the failure was real, not waived.

## Reproduce

```bash
# 1) differential test: 13,321 unique samples, 0 mismatches
python3 tests/test_diff.py

# 2) paired benchmark, real corpus (all three scales, both implementations)
python3 benchmark/bench.py --impl baseline  --corpus real --scale large
python3 benchmark/bench.py --impl optimized --corpus real --scale large

# 3) upstream test suite against the patch (needs pytest)
cp impl/optimized/simpleeval.py /tmp/g1opt/simpleeval.py && cp -r tests /tmp/g1opt/tests  # or: git clone upstream; git apply patch.diff; pytest tests
```

## Environment

* CPU: AMD EPYC 7K62 48-Core Processor, 4 vCPU (shared host)
* RAM: 3,812,564 kB total; no swap pressure observed
* Runtime: CPython **3.12.3** (the only interpreter on this machine; 3.10/3.11
  are not installed, so no cross-interpreter data is claimed)
* Seed: **20261120** (row generation and generated expressions)
* Upstream commit: `3b30888d0d5954df8a11b7e5ef26d17e19a96c29` (2026-09-15, MIT)
* Patch: `patch.diff` (+15/−2, 17 changed lines), `git apply --check` passes on
  the pristine upstream commit

## 本轮创新

**新在把「表达式求值库的一次性 API 税」拆开测量，并证伪了库自身的性能建议。**
台账里已有缓存型优化（pydash/parse/jsonpath-rw 等），但没有人区分
「解析产物（不可变，可按表达式驻留）」与「每次调用的求值器状态（随 names 变化，
不可驻留）」：本仓库用 `ast.dump` 前后哈希证明 AST 在求值中不被修改，
从而证明按 `(class, expr)` 缓存 AST 不是「缓存结果」（对可变 names 不成立），
而是一次语义透明的编译产物复用。实测成本分解：每行 `simple_eval` 约
42% 在 `ast.parse`、40% 在每次重建求值器、仅约 12% 在真正的求值 dispatch；
因此对 dispatch/算子内联做单点优化只能拿到 ~1.0×（原型实测 0.99×，放弃），
真正可摘的是解析税。与 `parse-opt-lab`（另一个上游的 Parser 构造缓存）的区别：
那条是「按语义键缓存 Parser 对象」，本条给出了解析产物不可变性的可执行证书
（13,141 次 AST dump 比对）并覆盖了上游 `parse` 被 mock 的契约（G1 曾失败并已修）。

## Layout

```
impl/baseline/simpleeval.py    # upstream file, byte-identical to 3b30888
impl/optimized/simpleeval.py   # patched file
patch.diff                     # +15/−2, applies to upstream root
benchmark/bench.py             # paired benchmark, writes benchmark/raw/*
benchmark/corpus.py            # real (sourced) + synthetic expressions
benchmark/baseline.json        # all baseline runs (3 scales × 2 corpora)
benchmark/optimized.json       # all optimized runs
benchmark/raw/*.json           # 84 raw samples + 12 aggregates
tests/test_diff.py             # differential + AST-immutability checks
LICENSE                        # upstream MIT notice + provenance paragraph
```