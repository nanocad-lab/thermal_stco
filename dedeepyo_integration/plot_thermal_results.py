#!/usr/bin/env python3
from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Tuple

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import yaml

try:
    from .thermal_analysis_george import ThermalAnalysisGeorge, WorkloadConfig
except ImportError:  # pragma: no cover - CLI execution path
    from thermal_analysis_george import ThermalAnalysisGeorge, WorkloadConfig

matplotlib.use("Agg")
sns.set()

_RAPID_PYTHON = os.environ.get("RAPID_PYTHON_BIN", sys.executable or "python3")
_RAPID_HW_CONFIG = "dedeepyo_integration/Rapid-LLM/configs/hardware-config/a100_80GB_legacy_thermal_port.yaml"
_CACHE_PATH = "dedeepyo_integration/state_cache.sqlite"
_MODEL_SWEEP_SOURCES = (
    (
        "decode_prefill_ratio_sweep_llama2_7b.csv",
        "Llama2-7B",
        "dedeepyo_integration/Rapid-LLM/configs/model-config/Llama2-7B_inf_2048_1792_thermal.yaml",
    ),
    (
        "decode_prefill_ratio_sweep_llama3p1_8b.csv",
        "Llama3.1-8B",
        "dedeepyo_integration/Rapid-LLM/configs/model-config/Llama3.1-8B_inf_2048_1792_thermal.yaml",
    ),
)
_THERMAL_CASE_CONFIGS = {
    "2.5D_baseline": "dedeepyo_integration/configs/thermal/2.5D_baseline.yaml",
    "3D_baseline": "dedeepyo_integration/configs/thermal/3D_baseline.yaml",
}


def _model_label_from_path(path_value: str) -> str:
    name = Path(path_value).name
    return name.replace(".yaml", "")


def _run_type_from_model_label(model_label: str) -> str:
    return "inference" if "_inf_" in model_label else "training"


def _load_workloads_by_thermal_case(repo_root: Path) -> Dict[str, WorkloadConfig]:
    workloads: Dict[str, WorkloadConfig] = {}
    for thermal_case, rel_path in _THERMAL_CASE_CONFIGS.items():
        cfg_path = repo_root / rel_path
        with open(cfg_path, "r", encoding="utf-8") as handle:
            cfg = yaml.safe_load(handle)
        workloads[thermal_case] = WorkloadConfig(
            system_name=str(cfg["system_name"]),
            htc=float(cfg["htc"]),
            tim_cond=float(cfg["tim_cond"]),
            infill_cond=float(cfg["infill_cond"]),
            underfill_cond=float(cfg["underfill_cond"]),
            hbm_stack_height=int(cfg["hbm_stack_height"]),
            dummy_si=bool(cfg["dummy_si"]),
        )
    return workloads


def _render_model_cfg_for_decode(base_model_cfg_path: Path, decode_tokens: int) -> str:
    with open(base_model_cfg_path, "r", encoding="utf-8") as handle:
        base_cfg = yaml.safe_load(handle)
    run_cfg = copy.deepcopy(base_cfg)
    run_cfg["model_param"]["global_batch_size"] = 32
    run_cfg["model_param"]["seq_len"] = 4096
    run_cfg["model_param"]["decode_len"] = int(decode_tokens)
    return yaml.safe_dump(run_cfg, sort_keys=False)


def _lookup_iteration0_runtime(
    *,
    model_config_text: str,
    workload: WorkloadConfig,
) -> float:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False) as handle:
        handle.write(model_config_text)
        temp_model_cfg = Path(handle.name)

    try:
        with ThermalAnalysisGeorge(
            backend_kind="rapid",
            persistent_cache_path=_CACHE_PATH,
            backend_workers=1,
            rapid_python_bin=_RAPID_PYTHON,
            rapid_hardware_config_path=_RAPID_HW_CONFIG,
            rapid_model_config_path=str(temp_model_cfg),
        ) as engine:
            profile = engine._resolve_profile(workload.system_name, workload.hbm_stack_height)
            state = engine._throttle_model.make_initial_state(workload, engine._thermal_model)
            transition = engine._throttle_model.build_transition_query(state, profile)
            key = engine._backend_runner.make_key(profile, transition.backend_input)
            result = engine._backend_runner.lookup(key)
            if result is None:
                task = engine._backend_runner.build_task(profile, transition.backend_input, key)
                engine._backend_runner.prefetch([task])
                result = engine._backend_runner.lookup(key)
            if result is None or result.runtime_seconds is None:
                raise RuntimeError(f"Failed to read ideal runtime for {workload.system_name}.")
            return float(result.runtime_seconds)
    finally:
        temp_model_cfg.unlink(missing_ok=True)


def _compute_ideal_runtime_map(sweep_df: pd.DataFrame, repo_root: Path) -> Dict[Tuple[str, int, str], float]:
    workloads_by_case = _load_workloads_by_thermal_case(repo_root)
    ideal_runtime: Dict[Tuple[str, int, str], float] = {}

    unique_model_decode = (
        sweep_df[["model_config_base", "decode_tokens"]].drop_duplicates().sort_values(["model_config_base", "decode_tokens"])
    )
    for _, entry in unique_model_decode.iterrows():
        base_model_cfg = Path(str(entry["model_config_base"]))
        decode_tokens = int(entry["decode_tokens"])
        rendered_cfg = _render_model_cfg_for_decode(base_model_cfg, decode_tokens)
        for thermal_case, workload in workloads_by_case.items():
            ideal_runtime[(str(base_model_cfg), decode_tokens, thermal_case)] = _lookup_iteration0_runtime(
                model_config_text=rendered_cfg,
                workload=workload,
            )

    return ideal_runtime


def _plot_normalized_runtime_vs_decode_tokens(
    sweep_df: pd.DataFrame,
    *,
    thermal_case: str,
    output_path: Path,
) -> None:
    case_df = sweep_df[sweep_df["thermal_case"] == thermal_case].copy()
    case_df = case_df.sort_values(["model", "decode_tokens"])

    fig = plt.figure(figsize=(9, 5))
    ax = sns.lineplot(
        data=case_df,
        x="decode_tokens",
        y="normalized_performance",
        hue="model",
        marker="o",
    )
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Ideal baseline")
    ax.set_title(f"Achieved vs Ideal Performance vs Decode Length ({thermal_case})")
    ax.set_xlabel("Decode Tokens")
    ax.set_ylabel("Normalized Performance (Ideal = 1.0)")
    ticks = sorted(case_df["decode_tokens"].unique())
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{int(tick)}" for tick in ticks], rotation=20, ha="right")

    y_min = float(case_df["normalized_performance"].min())
    y_max = float(case_df["normalized_performance"].max())
    y_span = y_max - y_min
    if y_span <= 1e-9:
        pad = max(0.02, abs(y_max) * 0.03)
    else:
        pad = y_span * 0.12
    y_lower = max(0.0, y_min - pad)
    y_upper = max(y_max + pad, 1.01)
    if (y_upper - y_lower) < 0.05:
        y_mid = (y_lower + y_upper) / 2.0
        y_lower = max(0.0, y_mid - 0.025)
        y_upper = y_mid + 0.025
    ax.set_ylim(bottom=y_lower, top=y_upper)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    tmp_dir = repo_root / "dedeepyo_integration" / "tmp"
    plots_dir = tmp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    sweep_frames = []
    for csv_name, model_label, model_cfg_relpath in _MODEL_SWEEP_SOURCES:
        frame = pd.read_csv(tmp_dir / csv_name)
        frame["model"] = model_label
        frame["model_config_base"] = str((repo_root / model_cfg_relpath).resolve())
        sweep_frames.append(frame)
    sweep_df = pd.concat(sweep_frames, ignore_index=True)
    sweep_df = sweep_df[sweep_df["run_error"].fillna("") == ""].copy()
    for column in (
        "prefill_tokens",
        "decode_tokens",
        "runtime_seconds",
        "gpu_peak_temperature_c",
        "gpu_time_frac_idle",
    ):
        sweep_df[column] = pd.to_numeric(sweep_df[column], errors="coerce")
    sweep_df = sweep_df.dropna(
        subset=[
            "prefill_tokens",
            "decode_tokens",
            "runtime_seconds",
            "gpu_peak_temperature_c",
            "gpu_time_frac_idle",
        ]
    ).copy()
    sweep_df["decode_tokens"] = sweep_df["decode_tokens"].astype(int)
    sweep_df["prefill_decode_ratio"] = sweep_df["prefill_tokens"] / sweep_df["decode_tokens"]
    ideal_runtime_map = _compute_ideal_runtime_map(sweep_df, repo_root)
    sweep_df["ideal_runtime_seconds"] = sweep_df.apply(
        lambda row: ideal_runtime_map[(str(row["model_config_base"]), int(row["decode_tokens"]), str(row["thermal_case"]))],
        axis=1,
    )
    sweep_df["normalized_performance"] = sweep_df["ideal_runtime_seconds"] / sweep_df["runtime_seconds"]
    sweep_df.to_csv(tmp_dir / "decode_prefill_ratio_sweep_with_normalized_perf.csv", index=False)

    for thermal_case, out_name in (
        ("2.5D_baseline", "sweep_2p5D_gpu_temp.png"),
        ("3D_baseline", "sweep_3D_gpu_temp.png"),
    ):
        case_df = sweep_df[sweep_df["thermal_case"] == thermal_case].copy()
        case_df = case_df.sort_values(["model", "prefill_tokens"])
        fig = plt.figure(figsize=(9, 5))
        ax = sns.lineplot(
            data=case_df,
            x="prefill_tokens",
            y="gpu_peak_temperature_c",
            hue="model",
            marker="o",
        )
        ax.set_title(f"Decode/Prefill Sweep ({thermal_case})")
        ax.set_xlabel("Prefill Tokens")
        ax.set_ylabel("GPU Peak Temperature (C)")
        fig.tight_layout()
        fig.savefig(plots_dir / out_name, dpi=200)
        plt.close(fig)

    for thermal_case, out_name in (
        ("2.5D_baseline", "sweep_2p5D_idle_time.png"),
        ("3D_baseline", "sweep_3D_idle_time.png"),
    ):
        case_df = sweep_df[sweep_df["thermal_case"] == thermal_case].copy()
        case_df = case_df.sort_values(["model", "prefill_tokens"])
        fig = plt.figure(figsize=(9, 5))
        ax = sns.lineplot(
            data=case_df,
            x="prefill_tokens",
            y="gpu_time_frac_idle",
            hue="model",
            marker="o",
        )
        ax.set_title(f"Decode/Prefill Sweep Idle Fraction ({thermal_case})")
        ax.set_xlabel("Prefill Tokens")
        ax.set_ylabel("GPU Time Fraction Idle")
        fig.tight_layout()
        fig.savefig(plots_dir / out_name, dpi=200)
        plt.close(fig)

    _plot_normalized_runtime_vs_decode_tokens(
        sweep_df,
        thermal_case="2.5D_baseline",
        output_path=plots_dir / "sweep_2p5D_perf_vs_decode_len.png",
    )
    _plot_normalized_runtime_vs_decode_tokens(
        sweep_df,
        thermal_case="3D_baseline",
        output_path=plots_dir / "sweep_3D_perf_vs_decode_len.png",
    )

    suite_df = pd.read_csv(repo_root / "dedeepyo_integration" / "thermal_suite_results.csv")
    suite_df["model"] = suite_df["model_config"].map(_model_label_from_path)
    suite_df["run_type"] = suite_df["model"].map(_run_type_from_model_label)
    suite_df["gpu_peak_temperature_c"] = suite_df["gpu_peak_temperature_c"].astype(float)
    suite_df["gpu_time_frac_idle"] = suite_df["gpu_time_frac_idle"].astype(float)

    for thermal_case, out_name in (
        ("2.5D_baseline", "thermal_suite_2p5D_gpu_temp.png"),
        ("3D_baseline", "thermal_suite_3D_gpu_temp.png"),
    ):
        case_df = suite_df[suite_df["thermal_case"] == thermal_case].copy()
        case_df = case_df.sort_values(["run_type", "model"])
        fig = plt.figure(figsize=(10, 5))
        ax = sns.barplot(
            data=case_df,
            x="model",
            y="gpu_peak_temperature_c",
            hue="run_type",
        )
        ax.set_title(f"Thermal Suite GPU Peak Temperature ({thermal_case})")
        ax.set_xlabel("Model Config")
        ax.set_ylabel("GPU Peak Temperature (C)")
        ax.tick_params(axis="x", rotation=20)
        fig.tight_layout()
        fig.savefig(plots_dir / out_name, dpi=200)
        plt.close(fig)

    for thermal_case, out_name in (
        ("2.5D_baseline", "thermal_suite_2p5D_idle_time.png"),
        ("3D_baseline", "thermal_suite_3D_idle_time.png"),
    ):
        case_df = suite_df[suite_df["thermal_case"] == thermal_case].copy()
        case_df = case_df.sort_values(["run_type", "model"])
        fig = plt.figure(figsize=(10, 5))
        ax = sns.barplot(
            data=case_df,
            x="model",
            y="gpu_time_frac_idle",
            hue="run_type",
        )
        ax.set_title(f"Thermal Suite Idle Fraction ({thermal_case})")
        ax.set_xlabel("Model Config")
        ax.set_ylabel("GPU Time Fraction Idle")
        ax.tick_params(axis="x", rotation=20)
        fig.tight_layout()
        fig.savefig(plots_dir / out_name, dpi=200)
        plt.close(fig)

    print(f"Wrote plots to {plots_dir}")


if __name__ == "__main__":
    main()
