#!/usr/bin/env python3
"""Generate raw + normalized decode/prefill CSVs for inference (ECTC14-style inputs).

Thermal cases match ``tmp/run_decode_prefill_sweep_ideal_and_baselines.py`` but resolve paths
relative to the DeepFlow repository root and default the Python interpreter to ``sys.executable``.

Example::

    cd /path/to/DeepFlow/dedeepyo_integration
    python3 run_inference_decode_prefill_sweep.py

Raw output: ``dedeepyo_integration/tmp/decode_prefill_ratio_sweep_ideal_and_baselines_raw.csv``
Normalized preview: ``dedeepyo_integration/tmp/decode_prefill_ratio_sweep_ideal_and_baselines_normalized.csv``

Pipe the raw file into ``python3 ../generate_ectc_revised_csvs.py --train-csv ... --infer-raw-csv ... --ectc14``
or point ``--infer-raw-csv`` at the raw path above.
"""

from __future__ import annotations

import copy
import csv
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List, Tuple

import pandas as pd
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DED = _REPO_ROOT / "dedeepyo_integration"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_DED) not in sys.path:
    sys.path.insert(0, str(_DED))

from thermal_analysis_george import ThermalAnalysisGeorge, WorkloadConfig


PYTHON_BIN = sys.executable or "python3"
HARDWARE_CONFIG = _REPO_ROOT / "dedeepyo_integration" / "Rapid-LLM" / "configs" / "hardware-config" / "a100_80GB_legacy_thermal_port.yaml"
CACHE_PATH = _REPO_ROOT / "dedeepyo_integration" / "state_cache.sqlite"
SEQ_LEN = 4096
DECODE_TOKENS_SWEEP = (3584, 3072, 2560, 2048, 1536, 1024, 768, 512, 256)

MODEL_SOURCES = (
    ("Llama2-7B", _REPO_ROOT / "dedeepyo_integration" / "Rapid-LLM" / "configs" / "model-config" / "Llama2-7B_inf_2048_1792_thermal.yaml"),
    ("Llama3.1-8B", _REPO_ROOT / "dedeepyo_integration" / "Rapid-LLM" / "configs" / "model-config" / "Llama3.1-8B_inf_2048_1792_thermal.yaml"),
)

CASE_THERMAL_CONFIGS: Dict[str, Path] = {
    "ideal_2p5D": _REPO_ROOT / "dedeepyo_integration" / "configs" / "thermal" / "2.5D_no_throttle.yaml",
    "ideal_3D": _REPO_ROOT / "dedeepyo_integration" / "configs" / "thermal" / "3D_no_throttle.yaml",
    "2.5D_baseline": _REPO_ROOT / "dedeepyo_integration" / "configs" / "thermal" / "2.5D_baseline.yaml",
    "3D_1GPU_baseline": _REPO_ROOT / "dedeepyo_integration" / "configs" / "thermal" / "3D_baseline.yaml",
}

IDEAL_CASE_BY_CASE = {
    "ideal_2p5D": "ideal_2p5D",
    "2.5D_baseline": "ideal_2p5D",
    "ideal_3D": "ideal_3D",
    "3D_1GPU_baseline": "ideal_3D",
}


def _load_case_workloads() -> Dict[str, WorkloadConfig]:
    case_workloads: Dict[str, WorkloadConfig] = {}
    for case_name, cfg_path in CASE_THERMAL_CONFIGS.items():
        with open(cfg_path, "r", encoding="utf-8") as handle:
            cfg = yaml.safe_load(handle)
        case_workloads[case_name] = WorkloadConfig(
            system_name=str(cfg["system_name"]),
            htc=float(cfg["htc"]),
            tim_cond=float(cfg["tim_cond"]),
            infill_cond=float(cfg["infill_cond"]),
            underfill_cond=float(cfg["underfill_cond"]),
            hbm_stack_height=int(cfg["hbm_stack_height"]),
            dummy_si=bool(cfg["dummy_si"]),
            no_throttle=bool(cfg.get("no_throttle", False)),
        )
    return case_workloads


def _tmp_dir() -> Path:
    path = _REPO_ROOT / "dedeepyo_integration" / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _render_model_cfg(base_cfg_path: Path, decode_tokens: int) -> str:
    with open(base_cfg_path, "r", encoding="utf-8") as handle:
        base_cfg = yaml.safe_load(handle)
    run_cfg = copy.deepcopy(base_cfg)
    run_cfg["model_param"]["global_batch_size"] = 32
    run_cfg["model_param"]["seq_len"] = SEQ_LEN
    run_cfg["model_param"]["decode_len"] = int(decode_tokens)
    return yaml.safe_dump(run_cfg, sort_keys=False)


def _run_one_model(
    model_name: str,
    base_cfg_path: Path,
    case_workloads: Dict[str, WorkloadConfig],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for decode_tokens in DECODE_TOKENS_SWEEP:
        prefill_tokens = SEQ_LEN - int(decode_tokens)
        rendered_cfg = _render_model_cfg(base_cfg_path, int(decode_tokens))

        with NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
            handle.write(rendered_cfg)
            run_cfg_path = Path(handle.name)

        try:
            with ThermalAnalysisGeorge(
                backend_kind="rapid",
                persistent_cache_path=str(CACHE_PATH),
                backend_workers=1,
                rapid_python_bin=PYTHON_BIN,
                rapid_hardware_config_path=str(HARDWARE_CONFIG),
                rapid_model_config_path=str(run_cfg_path),
            ) as engine:
                case_names = list(case_workloads.keys())
                workloads = [case_workloads[name] for name in case_names]
                run_results = engine.run_parallel(workloads)

            for case_name, values in zip(case_names, run_results):
                runtime, gpu_temp, hbm_temp, idle_frac, nominal_ghz, hbm_bw = values
                rows.append(
                    {
                        "model": model_name,
                        "model_config_base": str(base_cfg_path.resolve()),
                        "thermal_case": case_name,
                        "system_name": case_workloads[case_name].system_name,
                        "prefill_tokens": float(prefill_tokens),
                        "decode_tokens": float(decode_tokens),
                        "runtime_seconds": float(runtime),
                        "gpu_peak_temperature_c": float(gpu_temp),
                        "hbm_peak_temperature_c": float(hbm_temp),
                        "gpu_time_frac_idle": float(idle_frac),
                        "nominal_frequency_ghz": float(nominal_ghz),
                        "hbm_bandwidth_gbps": float(hbm_bw),
                        "run_error": "",
                    }
                )
        except Exception as exc:
            for case_name in case_workloads:
                rows.append(
                    {
                        "model": model_name,
                        "model_config_base": str(base_cfg_path.resolve()),
                        "thermal_case": case_name,
                        "system_name": case_workloads[case_name].system_name,
                        "prefill_tokens": float(prefill_tokens),
                        "decode_tokens": float(decode_tokens),
                        "runtime_seconds": None,
                        "gpu_peak_temperature_c": None,
                        "hbm_peak_temperature_c": None,
                        "gpu_time_frac_idle": None,
                        "nominal_frequency_ghz": None,
                        "hbm_bandwidth_gbps": None,
                        "run_error": str(exc),
                    }
                )
        finally:
            run_cfg_path.unlink(missing_ok=True)

    return rows


def _compute_normalized(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out[out["run_error"].fillna("") == ""].copy()

    out["prefill_tokens"] = pd.to_numeric(out["prefill_tokens"], errors="coerce")
    out["decode_tokens"] = pd.to_numeric(out["decode_tokens"], errors="coerce")
    out["runtime_seconds"] = pd.to_numeric(out["runtime_seconds"], errors="coerce")
    out = out.dropna(subset=["prefill_tokens", "decode_tokens", "runtime_seconds"]).copy()

    out["prefill_tokens"] = out["prefill_tokens"].astype(int)
    out["decode_tokens"] = out["decode_tokens"].astype(int)
    out["prefill_decode_ratio"] = out["prefill_tokens"] / out["decode_tokens"]

    out["scenario_id"] = out.apply(
        lambda r: f"{r['model']}|prefill={int(r['prefill_tokens'])}|decode={int(r['decode_tokens'])}",
        axis=1,
    )

    ideal_df = out[out["thermal_case"].isin(["ideal_2p5D", "ideal_3D"])][
        ["model", "prefill_tokens", "decode_tokens", "thermal_case", "runtime_seconds"]
    ].rename(columns={"runtime_seconds": "ideal_runtime_seconds", "thermal_case": "ideal_case"})

    ideal_lookup: Dict[Tuple[str, int, int, str], float] = {
        (str(row.model), int(row.prefill_tokens), int(row.decode_tokens), str(row.ideal_case)): float(row.ideal_runtime_seconds)
        for row in ideal_df.itertuples(index=False)
    }

    ideal_case_col: List[str] = []
    ideal_runtime_col: List[float] = []
    norm_col: List[float] = []

    for row in out.itertuples(index=False):
        case_name = str(row.thermal_case)
        ideal_case = IDEAL_CASE_BY_CASE[case_name]
        key = (str(row.model), int(row.prefill_tokens), int(row.decode_tokens), ideal_case)
        ideal_runtime = ideal_lookup[key]
        runtime = float(row.runtime_seconds)
        norm_col.append(float(ideal_runtime / runtime))
        ideal_case_col.append(ideal_case)
        ideal_runtime_col.append(float(ideal_runtime))

    out["ideal_case"] = ideal_case_col
    out["ideal_runtime_seconds"] = ideal_runtime_col
    out["normalized_performance"] = norm_col
    out["ideal_normalized_performance"] = 1.0
    out["gap_to_ideal"] = 1.0 - out["normalized_performance"]
    return out


def main() -> None:
    tmp_dir = _tmp_dir()
    case_workloads = _load_case_workloads()

    all_rows: List[Dict[str, object]] = []
    for model_name, model_path in MODEL_SOURCES:
        all_rows.extend(_run_one_model(model_name, model_path, case_workloads))

    raw_csv = tmp_dir / "decode_prefill_ratio_sweep_ideal_and_baselines_raw.csv"
    with open(raw_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model",
                "model_config_base",
                "thermal_case",
                "system_name",
                "prefill_tokens",
                "decode_tokens",
                "runtime_seconds",
                "gpu_peak_temperature_c",
                "hbm_peak_temperature_c",
                "gpu_time_frac_idle",
                "nominal_frequency_ghz",
                "hbm_bandwidth_gbps",
                "run_error",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    df = pd.DataFrame(all_rows)
    normalized = _compute_normalized(df)
    normalized_csv = tmp_dir / "decode_prefill_ratio_sweep_ideal_and_baselines_normalized.csv"
    normalized.to_csv(normalized_csv, index=False)

    display_cols = [
        "model",
        "prefill_tokens",
        "decode_tokens",
        "thermal_case",
        "runtime_seconds",
        "ideal_case",
        "ideal_runtime_seconds",
        "normalized_performance",
    ]
    preview = normalized[display_cols].sort_values(
        ["model", "decode_tokens", "thermal_case"], ascending=[True, False, True]
    )
    print(f"Wrote raw data: {raw_csv}")
    print(f"Wrote normalized data: {normalized_csv}")
    print("\nPreview:")
    print(preview.to_string(index=False))


if __name__ == "__main__":
    main()
