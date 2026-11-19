#!/usr/bin/env python3
"""Paired benchmark for the simpleeval parse-cache patch.

Workload: the documented one-shot usage pattern of the library

    for row in rows:
        value = simple_eval(expr, names=row)      # or SimpleEval().eval(expr)

i.e. a rule set evaluated once per row.  The same rows and the same
expressions are used for both implementations; only the implementation
directory changes.

Usage:
    python benchmark/bench.py --impl baseline  --corpus real --scale large
    python benchmark/bench.py --impl optimized --corpus real --scale large

Each run writes every timed sample to ``benchmark/raw/<impl>-<corpus>-<scale>-<i>.json``
and the aggregate to the path given by ``--out``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402

SCALES = {"small": 100, "medium": 500, "large": 2000}


def load_impl(impl: str):
    path = ROOT / "impl" / impl / "simpleeval.py"
    spec = importlib.util.spec_from_file_location(f"simpleeval_{impl}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def env_info() -> dict:
    cpu = ""
    mem = ""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                mem = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "cpu": cpu,
        "mem_total": mem,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def run_scale(mod, exprs: list[str], rows: list[dict]) -> tuple[float, int]:
    simple_eval = mod.simple_eval
    t0 = time.perf_counter()
    n = 0
    for row in rows:
        for expr in exprs:
            simple_eval(expr, names=row)
            n += 1
    return time.perf_counter() - t0, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", choices=["baseline", "optimized"], required=True)
    ap.add_argument("--corpus", choices=["real", "synthetic"], required=True)
    ap.add_argument("--scale", choices=sorted(SCALES), required=True)
    ap.add_argument("--samples", type=int, default=7)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "benchmark" / "raw")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    mod = load_impl(args.impl)
    entries = corpus.REAL if args.corpus == "real" else corpus.SYNTHETIC
    exprs = [e for e, _ in entries]
    rows = corpus.make_rows(SCALES[args.scale])

    # warmup (not timed)
    for _ in range(args.warmup):
        run_scale(mod, exprs, rows)

    samples = []
    for i in range(args.samples):
        elapsed, n_eval = run_scale(mod, exprs, rows)
        samples.append(
            {
                "impl": args.impl,
                "corpus": args.corpus,
                "scale": args.scale,
                "sample": i,
                "seconds": elapsed,
                "evaluations": n_eval,
                "rows": len(rows),
                "expressions": len(exprs),
                "seed": corpus.SEED,
            }
        )

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    for s in samples:
        p = args.raw_dir / f"{s['impl']}-{s['corpus']}-{s['scale']}-{s['sample']}.json"
        p.write_text(json.dumps(s, indent=2) + "\n")

    secs = [s["seconds"] for s in samples]
    q = statistics.quantiles(secs, n=4) if len(secs) > 1 else [secs[0]] * 3
    aggregate = {
        "impl": args.impl,
        "corpus": args.corpus,
        "scale": args.scale,
        "rows": len(rows),
        "expressions": len(exprs),
        "evaluations_per_sample": samples[0]["evaluations"],
        "seed": corpus.SEED,
        "samples": len(samples),
        "median_seconds": statistics.median(secs),
        "p25_seconds": q[0],
        "p75_seconds": q[2],
        "min_seconds": min(secs),
        "max_seconds": max(secs),
        "rel_stdev": (statistics.pstdev(secs) / statistics.mean(secs)) if len(secs) > 1 else 0.0,
        "command": " ".join(sys.argv),
        "env": env_info(),
        "raw_dir": str(args.raw_dir),
    }
    text = json.dumps(aggregate, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())