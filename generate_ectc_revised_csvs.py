#!/usr/bin/env python3
"""Build ECTC* revised CSV tables from thermal_suite CSV output and inference sweep data.

training / wide tables (ECTC16 / ECTC2 / ECTC5 scope)
======================================================
``thermal_suite.py`` emits rows including ``thermal_case``, ``system_name``,
``hbm_stack_height``, ``model_config``, ``runtime_seconds``. The archived ``*_revised.csv`` layouts
normalize against one **ideal** thermal_case per model and stack-height family:

- 8-high 2p5D packages: thermal_case ``2.5D_baseline_high+htc10``
- 8-high 3D GPU bottom **and** GPU-on-top:
  ``3D_baseline_high_htc10_high_tim50_high_infill19_high_underfill19`` (GPU-on-top rows reuse this
  ideal runtime measured on the GPU-bottom stack).
- 16-high 2p5D:
  ``2.5D_baseline_high_htc10_high_tim50_high_infill19_high_underfill19_16high``
- 16-high 3D GPU bottom **and** GPU-on-top:
  ``3D_baseline_high_htc10_high_tim50_high_infill19_high_underfill19_16high``

For each emitted row::

    normalization_constant = ideal runtime seconds (model_config + stack + effective system family)
    normalized_runtime = runtime_seconds / normalization_constant
    normalized_performance = 1 / normalized_runtime

``runtime_seconds2`` duplicates ``runtime_seconds`` and ``system_name2`` copies ``system_name``,
matching the paper CSV layout.

ECTC14 (inference sweep)
========================
Needs a *raw* sweep CSV produced by ``dedeepyo_integration/run_inference_decode_prefill_sweep.py``.
Each row repeats ``thermal_case`` in
``ideal_2p5D``, ``ideal_3D``, ``2.5D_baseline``, ``3D_1GPU_baseline`` across a decode/prefill grid.
Normalization follows
``normalized_performance = ideal_runtime / measured_runtime``.
``3D_1GPU_baseline`` is labelled ``3D_baseline`` in the output CSV for ``ECTC13.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Mapping, MutableMapping, Sequence, Tuple

import pandas as pd


IdealKey = Tuple[str, int]  # (system_name, hbm_stack_height)

IDEAL_THERMAL_CASE: Mapping[IdealKey, str] = {
    ("2p5D_1GPU", 8): "2.5D_baseline_high+htc10",
    # GPU-on-top rows reuse the GPU-bottom ideal runtime (see archived ECTC CSVs).
    ("3D_1GPU", 8): "3D_baseline_high_htc10_high_tim50_high_infill19_high_underfill19",
    ("2p5D_1GPU", 16): "2.5D_baseline_high_htc10_high_tim50_high_infill19_high_underfill19_16high",
    ("3D_1GPU", 16): "3D_baseline_high_htc10_high_tim50_high_infill19_high_underfill19_16high",
}


MODEL_NAME_HINTS: Sequence[Tuple[str, str]] = (
    ("Llama3.1-8B", "Llama3.1-8B"),
    ("Llama2-7B", "Llama2-7B"),
)


def derive_model_short_name(model_config: str) -> str:
    path = Path(model_config)
    name = path.name
    for hint, short in MODEL_NAME_HINTS:
        if hint in name:
            return short
    return path.stem


def _effective_system_for_ideal(system_name: str) -> str:
    """ECTC normalization uses the 3D GPU-bottom ideal row for GPU-on-top silicon as well."""

    if system_name == "3D_1GPU_top":
        return "3D_1GPU"
    return system_name


def _fetch_ideal_runtime_seconds(
    model_config: str,
    lookup_system: str,
    ideal_case: str,
    primary: pd.DataFrame,
    anchor: pd.DataFrame | None,
) -> float:
    """Return runtime_seconds row for canonical ideal thermal_case."""

    frames: Sequence[Tuple[str, pd.DataFrame]] = (
        ("--train-csv", primary),
    )
    if anchor is not None:
        frames = (*frames, ("--ideal-anchor-csv", anchor))

    for label, df in frames:
        match = df[
            (df["model_config"].astype(str) == model_config)
            & (df["system_name"].astype(str) == lookup_system)
            & (df["thermal_case"].astype(str) == ideal_case)
        ]
        if len(match) > 1:
            raise RuntimeError(
                "Expected exactly one ideal row for "
                f"model_config={model_config}, system={lookup_system}, thermal_case={ideal_case!r} in {label}; "
                f"found {len(match)}"
            )
        if len(match) == 1:
            return float(match.iloc[0]["runtime_seconds"])
    hints = ""
    if anchor is None:
        hints = " Provide --ideal-anchor-csv with a fuller thermal_suite export if yours omits ideals."
    raise RuntimeError(
        "Missing ideal thermal row "
        f"(model_config={model_config}, system={lookup_system}, thermal_case={ideal_case!r}). "
        "Include those YAML thermal cases or pass ideal anchor CSV." + hints
    )


def build_wide_normalized_table(train_df: pd.DataFrame, *, ideal_anchor_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Wide schema with normalization columns (ECTC16/ECTC2/ECTC5 family)."""
    work = train_df.copy()
    work["model_name"] = work["model_config"].map(derive_model_short_name)

    lut: MutableMapping[Tuple[str, str, int], float] = {}

    grouping_keys = {
        (
            str(r["model_config"]),
            str(r["system_name"]),
            int(r["hbm_stack_height"]),
        )
        for _, r in work.iterrows()
    }

    for mc, sys_name, h in grouping_keys:
        lookup_sys = _effective_system_for_ideal(sys_name)
        ideal_case = IDEAL_THERMAL_CASE.get((lookup_sys, h))
        if ideal_case is None:
            raise KeyError(f"No IDEAL_THERMAL_CASE entry for ({lookup_sys!r}, {h}); extend IDEAL_THERMAL_CASE.")
        lut[(mc, sys_name, h)] = _fetch_ideal_runtime_seconds(mc, lookup_sys, ideal_case, work, ideal_anchor_df)

    norm_const: list[float] = []
    perf: list[float] = []
    nrun: list[float] = []

    for row in work.itertuples(index=False):
        key = (
            str(getattr(row, "model_config")),
            str(getattr(row, "system_name")),
            int(getattr(row, "hbm_stack_height")),
        )
        nc = lut[key]
        rt = float(getattr(row, "runtime_seconds"))
        norm_const.append(nc)
        nrun.append(rt / nc if nc != 0 else float("nan"))
        perf.append(nc / rt if rt != 0 else float("nan"))

    out = work.copy()
    out["system_name2"] = out["system_name"]
    out["runtime_seconds2"] = pd.to_numeric(out["runtime_seconds"], errors="coerce")
    out["normalization_constant"] = norm_const
    out["normalized_runtime"] = nrun
    out["normalized_performance"] = perf

    canonical_order = [
        "backend_kind",
        "hardware_config",
        "model_config",
        "thermal_config",
        "thermal_case",
        "system_name",
        "htc",
        "tim_cond",
        "infill_cond",
        "underfill_cond",
        "hbm_stack_height",
        "dummy_si",
        "no_throttle",
        "runtime_seconds",
        "gpu_peak_temperature_c",
        "hbm_peak_temperature_c",
        "gpu_time_frac_idle",
        "nominal_frequency_ghz",
        "hbm_bandwidth_gbps",
        "iterations",
        "system_name2",
        "runtime_seconds2",
        "normalization_constant",
        "normalized_runtime",
        "normalized_performance",
        "model_name",
    ]
    existing = [c for c in canonical_order if c in out.columns]
    remaining = [c for c in out.columns if c not in existing]
    return out[existing + remaining]


def split_wide_for_ectc_paper(wide_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (non-16-high-like rows, 16-high rows) matching archived ECTC2/ECTC16 vs ECTC5 splits."""

    stacks = pd.to_numeric(wide_df["hbm_stack_height"], errors="coerce").fillna(-1).astype(int)
    sixteen_stack = stacks == 16
    case_hint = wide_df["thermal_case"].astype(str).str.contains("16high", regex=False)
    is_high_stack = sixteen_stack | case_hint
    return wide_df.loc[~is_high_stack].copy(), wide_df.loc[is_high_stack].copy()


IDEAL_MAPPING_INFERENCE: Mapping[str, str] = {
    "ideal_2p5D": "ideal_2p5D",
    "2.5D_baseline": "ideal_2p5D",
    "ideal_3D": "ideal_3D",
    "3D_1GPU_baseline": "ideal_3D",
}

THERMAL_DISPLAY: Mapping[str, str] = {
    "ideal_2p5D": "ideal_2p5D",
    "ideal_3D": "ideal_3D",
    "2.5D_baseline": "2.5D_baseline",
    "3D_1GPU_baseline": "3D_baseline",
}


def normalize_inference_prefill_decode_csv(raw_infer_df: pd.DataFrame) -> pd.DataFrame:
    df = raw_infer_df.copy()
    err_col = df.get("run_error", pd.Series("", index=df.index))
    df = df[err_col.fillna("") == ""].copy()

    for column in ["prefill_tokens", "decode_tokens", "runtime_seconds"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["prefill_tokens", "decode_tokens", "runtime_seconds"]).copy()

    ideal_candidates = sorted({"ideal_2p5D", "ideal_3D"})

    ideals = df[df["thermal_case"].isin(ideal_candidates)][
        ["model", "prefill_tokens", "decode_tokens", "thermal_case", "runtime_seconds"]
    ].rename(columns={"runtime_seconds": "ideal_runtime_seconds", "thermal_case": "ideal_case"})

    lookup: MutableMapping[Tuple[str, int, int, str], float] = {}
    for row in ideals.itertuples(index=False):
        lookup[
            (
                str(row.model),
                int(row.prefill_tokens),
                int(row.decode_tokens),
                str(row.ideal_case),
            )
        ] = float(row.ideal_runtime_seconds)

    out_rows = []
    for row in df.itertuples(index=False):
        scenario = str(row.thermal_case)
        if scenario not in IDEAL_MAPPING_INFERENCE:
            continue
        ideal_case_name = IDEAL_MAPPING_INFERENCE[scenario]
        key = (str(row.model), int(row.prefill_tokens), int(row.decode_tokens), ideal_case_name)
        ideal_runtime = lookup.get(key)
        if ideal_runtime is None:
            raise RuntimeError(f"Missing ideal runtime for {key}")

        rt = float(row.runtime_seconds)
        norm_perf = ideal_runtime / rt if rt != 0 else float("nan")
        display_case = THERMAL_DISPLAY.get(scenario, scenario)
        out_rows.append((row.model, int(row.prefill_tokens), int(row.decode_tokens), display_case, norm_perf))

    out_df = pd.DataFrame(
        out_rows,
        columns=[
            "model",
            "prefill_tokens",
            "decode_tokens",
            "thermal_case",
            "normalized_performance",
        ],
    )
    return (
        out_df.sort_values(["model", "decode_tokens", "thermal_case"], ascending=[True, False, True])
        .reset_index(drop=True)
    )


def _write_csv(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train-csv", type=Path, required=True, help="CSV from thermal_suite.py")
    parser.add_argument(
        "--ideal-anchor-csv",
        type=Path,
        default=None,
        help="Optional thermal_suite CSV with ideal thermal rows when --train-csv is a slim excerpt.",
    )
    parser.add_argument(
        "--infer-raw-csv",
        type=Path,
        default=None,
        help="Raw sweep CSV from run_inference_decode_prefill_sweep.py (use with --ectc14)",
    )
    parser.add_argument(
        "--out-ectc16",
        type=Path,
        default=Path("ECTC16_revised.csv"),
        help="Subset without 16-HBM-stack rows.",
    )
    parser.add_argument(
        "--out-ectc2",
        type=Path,
        default=Path("ECTC2_revised.csv"),
        help="Historical duplicate slice of ectc16 in this repo (same partitioning).",
    )
    parser.add_argument(
        "--out-ectc5",
        type=Path,
        default=Path("ECTC5_revised.csv"),
        help="16-HBM-stack rows.",
    )
    parser.add_argument(
        "--ectc-wide-all",
        type=Path,
        default=None,
        help="Optional path to emit the full wide dataframe prior to partitioning.",
    )
    parser.add_argument("--out-ectc14", type=Path, default=Path("ECTC14_revised.csv"))
    parser.add_argument(
        "--ectc14",
        action="store_true",
        help="Also emit inference table from raw sweep CSV.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    train = pd.read_csv(args.train_csv)
    anchor = pd.read_csv(args.ideal_anchor_csv) if args.ideal_anchor_csv else None
    wide = build_wide_normalized_table(train, ideal_anchor_df=anchor)
    if args.ectc_wide_all:
        _write_csv(wide, Path(args.ectc_wide_all))

    ectc16_partition, ectc5_partition = split_wide_for_ectc_paper(wide)
    _write_csv(ectc16_partition, args.out_ectc16)
    _write_csv(ectc16_partition, args.out_ectc2)
    _write_csv(ectc5_partition, args.out_ectc5)
    print(f"Wrote {args.out_ectc16.name}, {args.out_ectc2.name}, {args.out_ectc5.name}")

    if args.ectc14:
        if args.infer_raw_csv is None or not args.infer_raw_csv.exists():
            raise SystemExit("--ectc14 requires --infer-raw-csv with an existing file.")
        ectc14_df = normalize_inference_prefill_decode_csv(pd.read_csv(args.infer_raw_csv))
        _write_csv(ectc14_df, args.out_ectc14)
        print(f"Wrote {args.out_ectc14.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
