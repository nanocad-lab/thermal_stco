#!/usr/bin/env python3

# RUN THIS FILE, IT RUNS THERMAL ANALYSIS FOR YOU.
from __future__ import annotations

import argparse
import csv
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    tqdm = None

try:
    from .thermal_analysis_george import ThermalAnalysisGeorge, WorkloadConfig
except ImportError:  # pragma: no cover
    from thermal_analysis_george import ThermalAnalysisGeorge, WorkloadConfig


_DEFAULT_PYTHON = sys.executable or "/usr/bin/python3"


class _ProgressReporter:
    def __init__(self, total: int) -> None:
        self._total = max(0, int(total))
        self._done = 0
        self._lock = threading.Lock()
        self._bar = None
        self._iter_bar = None
        self._iter_counts: Dict[str, int] = {}
        self._iter_total = max(1, self._total * 100)
        if tqdm is not None:
            self._bar = tqdm(total=self._total, desc="Thermal suite", unit="run", dynamic_ncols=True)
            self._iter_bar = tqdm(
                total=self._iter_total,
                desc="Iterations (all grid cells)",
                unit="iter",
                dynamic_ncols=True,
                leave=False,
                position=1,
            )
        else:
            print("tqdm not installed; using plain progress output.")

    def task_start(self, *, index: int, total: int, model_name: str, thermal_name: str) -> None:
        message = f"Grid cell {index}/{total}: {model_name} x {thermal_name}"
        with self._lock:
            if self._bar is not None:
                self._bar.write(message)
            else:
                print(message)

    def iteration_event(self, task_name: str, iteration_index: int, max_iterations: int, phase: str) -> None:
        if phase != "precompute":
            return
        max_display = max(1, min(int(max_iterations), 100))
        iter_display = max(0, min(int(iteration_index), max_display))
        with self._lock:
            previous = self._iter_counts.get(task_name, 0)
            if iter_display > previous:
                delta = iter_display - previous
                self._iter_counts[task_name] = iter_display
                if self._iter_bar is not None:
                    self._iter_bar.update(delta)
                    self._iter_bar.set_postfix_str(f"{task_name} {iter_display}/{max_display}")

    def advance(
        self,
        *,
        model_name: str,
        thermal_name: str,
        runtime_str: str,
        gpu_str: str,
        hbm_str: str,
        idle_str: str,
    ) -> None:
        self._done += 1
        message = (
            f"{model_name} | {thermal_name}: runtime={runtime_str} "
            f"gpu={gpu_str} hbm={hbm_str} idle={idle_str}"
        )
        with self._lock:
            if self._bar is not None:
                self._bar.update(1)
                self._bar.set_postfix_str(f"model={model_name}, thermal={thermal_name}")
                self._bar.write(message)
            else:
                print(f"[{self._done}/{self._total}] {message}")

    def close(self) -> None:
        with self._lock:
            if self._iter_counts:
                summary_parts = [f"{name}={value}/100" for name, value in sorted(self._iter_counts.items())]
                summary = "Iteration summary: " + ", ".join(summary_parts)
                if self._bar is not None:
                    self._bar.write(summary)
                else:
                    print(summary)
            if self._iter_bar is not None:
                self._iter_bar.close()
                self._iter_bar = None
            if self._bar is not None:
                self._bar.close()


@dataclass(frozen=True)
class ThermalCase:
    config_path: Path
    name: str
    system_name: str
    htc: float
    tim_cond: float
    infill_cond: float
    underfill_cond: float
    hbm_stack_height: int
    dummy_si: bool
    no_throttle: bool = False

    def to_workload(self) -> WorkloadConfig:
        return WorkloadConfig(
            system_name=self.system_name,
            htc=self.htc,
            tim_cond=self.tim_cond,
            infill_cond=self.infill_cond,
            underfill_cond=self.underfill_cond,
            hbm_stack_height=self.hbm_stack_height,
            dummy_si=self.dummy_si,
            no_throttle=self.no_throttle,
        )


@dataclass(frozen=True)
class SuiteConfig:
    config_path: Path
    backend_kind: str
    backend_workers: int
    speculative_misses: int
    grid_workers: int
    persistent_cache_path: Path
    rapid_python_bin: str
    hardware_config_path: Path
    model_config_paths: List[Path]
    thermal_config_paths: List[Path]
    results_csv_path: Path
    legacy_model_config_path: Path


def _load_yaml_mapping(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return loaded


def _resolve_path(raw_path: str, *, repo_root: Path, config_dir: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    repo_relative = repo_root / candidate
    if repo_relative.exists():
        return repo_relative
    return (config_dir / candidate).resolve()


def _coerce_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    raise ValueError(f"Expected boolean value for '{field_name}', got: {value!r}")


def load_thermal_case(path: Path) -> ThermalCase:
    data = _load_yaml_mapping(path)
    required = [
        "system_name",
        "htc",
        "tim_cond",
        "infill_cond",
        "underfill_cond",
        "hbm_stack_height",
        "dummy_si",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Missing keys in thermal config {path}: {', '.join(missing)}")
    name = str(data.get("name", path.stem))
    return ThermalCase(
        config_path=path,
        name=name,
        system_name=str(data["system_name"]),
        htc=float(data["htc"]),
        tim_cond=float(data["tim_cond"]),
        infill_cond=float(data["infill_cond"]),
        underfill_cond=float(data["underfill_cond"]),
        hbm_stack_height=int(data["hbm_stack_height"]),
        dummy_si=_coerce_bool(data["dummy_si"], field_name="dummy_si"),
        no_throttle=_coerce_bool(data.get("no_throttle", False), field_name="no_throttle"),
    )


def load_suite_config(config_path: Path) -> SuiteConfig:
    resolved_config = config_path.resolve()
    data = _load_yaml_mapping(resolved_config)
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = resolved_config.parent

    backend_kind = str(data.get("backend_kind", "rapid")).strip().lower()
    if backend_kind not in {"legacy", "rapid"}:
        raise ValueError(f"Unsupported backend_kind '{backend_kind}' in {resolved_config}")

    backend_workers = int(data.get("backend_workers", 1))
    if backend_workers < 1:
        raise ValueError("backend_workers must be >= 1")
    speculative_misses = int(data.get("speculative_misses", 0))
    if speculative_misses < 0:
        raise ValueError("speculative_misses must be >= 0")
    default_grid_workers = min(8, os.cpu_count() or 1)
    grid_workers = int(data.get("grid_workers", default_grid_workers))
    if grid_workers < 1:
        raise ValueError("grid_workers must be >= 1")

    hardware_raw = data.get("hardware_config")
    if not isinstance(hardware_raw, str) or not hardware_raw.strip():
        raise ValueError("config must define non-empty 'hardware_config'")
    hardware_path = _resolve_path(hardware_raw, repo_root=repo_root, config_dir=config_dir)
    if not hardware_path.exists():
        raise FileNotFoundError(hardware_path)

    model_raw = data.get("model_configs")
    if not isinstance(model_raw, list) or not model_raw:
        raise ValueError("config must define non-empty 'model_configs' list")
    model_paths: List[Path] = []
    for entry in model_raw:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError("Each model config path must be a non-empty string")
        model_path = _resolve_path(entry, repo_root=repo_root, config_dir=config_dir)
        if not model_path.exists():
            raise FileNotFoundError(model_path)
        model_paths.append(model_path)

    thermal_raw = data.get("thermal_configs")
    if not isinstance(thermal_raw, list) or not thermal_raw:
        raise ValueError("config must define non-empty 'thermal_configs' list")
    thermal_paths: List[Path] = []
    for entry in thermal_raw:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError("Each thermal config path must be a non-empty string")
        thermal_path = _resolve_path(entry, repo_root=repo_root, config_dir=config_dir)
        if not thermal_path.exists():
            raise FileNotFoundError(thermal_path)
        thermal_paths.append(thermal_path)

    persistent_cache_raw = str(data.get("persistent_cache", "dedeepyo_integration/state_cache.sqlite"))
    persistent_cache_path = _resolve_path(persistent_cache_raw, repo_root=repo_root, config_dir=config_dir)

    results_csv_raw = str(data.get("results_csv", "dedeepyo_integration/thermal_suite_results.csv"))
    results_csv_path = _resolve_path(results_csv_raw, repo_root=repo_root, config_dir=config_dir)

    rapid_python_bin = str(data.get("rapid_python_bin", _DEFAULT_PYTHON))

    legacy_model_raw = str(data.get("legacy_model_config", "DeepFlow_llm_dev/configs/model-config/LLM_thermal.yaml"))
    legacy_model_path = _resolve_path(legacy_model_raw, repo_root=repo_root, config_dir=config_dir)
    if not legacy_model_path.exists():
        raise FileNotFoundError(legacy_model_path)

    return SuiteConfig(
        config_path=resolved_config,
        backend_kind=backend_kind,
        backend_workers=backend_workers,
        speculative_misses=speculative_misses,
        grid_workers=grid_workers,
        persistent_cache_path=persistent_cache_path,
        rapid_python_bin=rapid_python_bin,
        hardware_config_path=hardware_path,
        model_config_paths=model_paths,
        thermal_config_paths=thermal_paths,
        results_csv_path=results_csv_path,
        legacy_model_config_path=legacy_model_path,
    )


def run_suite(config: SuiteConfig) -> List[Dict[str, Any]]:
    thermal_cases = [load_thermal_case(path) for path in config.thermal_config_paths]
    rows: List[Dict[str, Any]] = []
    grid_cells: List[Tuple[int, Path, ThermalCase]] = []
    cell_index = 1
    for model_path in config.model_config_paths:
        for thermal_case in thermal_cases:
            grid_cells.append((cell_index, model_path, thermal_case))
            cell_index += 1
    total_runs = len(grid_cells)
    progress = _ProgressReporter(total_runs)

    def _run_grid_cell(index: int, model_path: Path, thermal_case: ThermalCase) -> Dict[str, Any]:
        workload = thermal_case.to_workload()
        task_name = f"{model_path.name}:{thermal_case.name}"
        progress.task_start(index=index, total=total_runs, model_name=model_path.name, thermal_name=thermal_case.name)

        def _iteration_callback(_: WorkloadConfig, iteration_index: int, max_iterations: int, phase: str) -> None:
            progress.iteration_event(
                task_name=task_name,
                iteration_index=iteration_index,
                max_iterations=max_iterations,
                phase=phase,
            )

        with ThermalAnalysisGeorge(
            backend_kind=config.backend_kind,
            backend_workers=config.backend_workers,
            speculative_misses=config.speculative_misses,
            persistent_cache_path=str(config.persistent_cache_path),
            rapid_python_bin=config.rapid_python_bin,
            rapid_hardware_config_path=str(config.hardware_config_path),
            rapid_model_config_path=str(model_path),
            legacy_model_config_path=str(config.legacy_model_config_path),
            progress_callback=_iteration_callback,
        ) as engine:
            runtime, gpu_temp, hbm_temp, idle_frac, nominal_ghz, hbm_bw = engine.iterations(
                system_name=workload.system_name,
                HTC=workload.htc,
                TIM_cond=workload.tim_cond,
                infill_cond=workload.infill_cond,
                underfill_cond=workload.underfill_cond,
                HBM_stack_height=workload.hbm_stack_height,
                dummy_Si=workload.dummy_si,
                no_throttle=workload.no_throttle,
            )
            transition_entries = engine.get_transition_map_size()

        row = {
            "backend_kind": config.backend_kind,
            "hardware_config": str(config.hardware_config_path),
            "model_config": str(model_path),
            "thermal_config": str(thermal_case.config_path),
            "thermal_case": thermal_case.name,
            "system_name": thermal_case.system_name,
            "htc": thermal_case.htc,
            "tim_cond": thermal_case.tim_cond,
            "infill_cond": thermal_case.infill_cond,
            "underfill_cond": thermal_case.underfill_cond,
            "hbm_stack_height": thermal_case.hbm_stack_height,
            "dummy_si": thermal_case.dummy_si,
            "no_throttle": thermal_case.no_throttle,
            "runtime_seconds": runtime,
            "gpu_peak_temperature_c": gpu_temp,
            "hbm_peak_temperature_c": hbm_temp,
            "gpu_time_frac_idle": idle_frac,
            "nominal_frequency_ghz": nominal_ghz,
            "hbm_bandwidth_gbps": hbm_bw,
            "iterations": transition_entries,
        }
        return row

    try:
        max_workers = max(1, min(config.grid_workers, total_runs or 1))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(_run_grid_cell, index, model_path, thermal_case): (model_path, thermal_case)
                for index, model_path, thermal_case in grid_cells
            }
            for future in as_completed(future_to_task):
                model_path, thermal_case = future_to_task[future]
                row = future.result()
                rows.append(row)
                runtime = row["runtime_seconds"]
                gpu_temp = row["gpu_peak_temperature_c"]
                hbm_temp = row["hbm_peak_temperature_c"]
                idle_frac = row["gpu_time_frac_idle"]
                runtime_str = "NA" if runtime is None else f"{runtime:.6f}s"
                gpu_str = "NA" if gpu_temp is None else f"{gpu_temp:.2f}C"
                hbm_str = "NA" if hbm_temp is None else f"{hbm_temp:.2f}C"
                idle_str = "NA" if idle_frac is None else f"{idle_frac:.6f}"
                progress.advance(
                    model_name=model_path.name,
                    thermal_name=thermal_case.name,
                    runtime_str=runtime_str,
                    gpu_str=gpu_str,
                    hbm_str=hbm_str,
                    idle_str=idle_str,
                )
    finally:
        progress.close()
    rows.sort(key=lambda row: (str(row["model_config"]), str(row["thermal_config"])))
    return rows


def write_results_csv(rows: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run thermal-analysis grid over thermal YAML configs x model YAML configs."
    )
    parser.add_argument("--config", required=True, help="Path to suite loader YAML.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    suite_config = load_suite_config(Path(args.config))
    rows = run_suite(suite_config)
    write_results_csv(rows, suite_config.results_csv_path)
    print(f"Wrote {len(rows)} rows to {suite_config.results_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
