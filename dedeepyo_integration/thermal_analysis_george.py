from __future__ import annotations

# THIS FILE ONLY LAUNCHES 1 RUN. FOR A SUITE OF RUNS, USE THERMAL_SUITE.PY

import argparse
import copy
import contextlib
import csv
import hashlib
import itertools
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Union
import yaml

try:
    from thermal_analysis_gui import GPU_FLOPs_throttled, GPU_throttling, HBM_throttled_performance
except ModuleNotFoundError:  # pragma: no cover - CLI execution path
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    try:
        from thermal_analysis_gui import GPU_FLOPs_throttled, GPU_throttling, HBM_throttled_performance
    except ModuleNotFoundError:
        _REPO_ROOT_ROOT = _REPO_ROOT.parents[1]
        if str(_REPO_ROOT_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT_ROOT))
        from thermal_analysis_gui import GPU_FLOPs_throttled, GPU_throttling, HBM_throttled_performance
try:
    from DeepFlow_llm_dev.run_perf import run_LLM
except ImportError:  # pragma: no cover - runtime environment dependent
    run_LLM = None  # type: ignore[assignment]

_DEFAULT_RAPID_PYTHON = sys.executable or "python3"


@dataclass(frozen=True)
class WorkloadConfig:
    system_name: str
    htc: float
    tim_cond: float
    infill_cond: float
    underfill_cond: float
    hbm_stack_height: int
    dummy_si: bool
    no_throttle: bool = False

    def signature(self) -> Tuple:
        return (
            self.system_name,
            float(self.htc),
            float(self.tim_cond),
            float(self.infill_cond),
            float(self.underfill_cond),
            int(self.hbm_stack_height),
            bool(self.dummy_si),
            bool(self.no_throttle),
        )


@dataclass(frozen=True)
class SystemProfile:
    profile_id: str
    hardware_config_path: Path
    hardware_hash: str
    hbm_bandwidth_reference: float
    hbm_size_gb: int
    hbm_stack_height: int


@dataclass(frozen=True)
class BackendInput:
    nominal_frequency_ghz: float
    hbm_latency_ns: float
    hbm_bandwidth_gbps: float
    l2_bandwidth_gbps: float
    l1_bandwidth_gbps: float
    register_bandwidth_gbps: float


@dataclass(frozen=True)
class BackendCacheKey:
    cache_signature: str
    profile_id: str
    hardware_hash: str
    frequency_centi_ghz: int
    hbm_latency_ns: int
    hbm_bandwidth_gbps: int
    l2_bandwidth_gbps: int
    l1_bandwidth_gbps: int
    register_bandwidth_gbps: int

    def as_tuple(self) -> Tuple:
        return (
            self.cache_signature,
            self.profile_id,
            self.hardware_hash,
            self.frequency_centi_ghz,
            self.hbm_latency_ns,
            self.hbm_bandwidth_gbps,
            self.l2_bandwidth_gbps,
            self.l1_bandwidth_gbps,
            self.register_bandwidth_gbps,
        )


@dataclass(frozen=True)
class BackendResult:
    runtime_seconds: Optional[float]
    gpu_time_frac_idle: Optional[float]
    error: Optional[str] = None


@dataclass(frozen=True)
class TransitionQuery:
    backend_input: BackendInput
    hbm_power_next: float
    gpu_flops_power_next: float
    hbm_bandwidth_return_value: float


@dataclass
class IterationState:
    iteration_index: int
    gpu_power: float
    hbm_power: float
    gpu_flops_power: float
    current_gpu_peak_temperature: float
    current_hbm_peak_temperature: float
    old_gpu_peak_temperature: float = -10.0
    old_hbm_peak_temperature: float = -10.0
    old_old_gpu_peak_temperature: float = -20.0
    old_old_hbm_peak_temperature: float = -20.0


@dataclass
class IterationResult:
    workload: WorkloadConfig
    runtime_seconds: Optional[float]
    gpu_peak_temperature: Optional[float]
    hbm_peak_temperature: Optional[float]
    gpu_time_frac_idle: Optional[float]
    nominal_frequency_ghz: Optional[float]
    hbm_bandwidth_gbps: Optional[float]
    error: Optional[str] = None

    def as_tuple(self) -> Tuple[float, float, float, float, float, float]:
        if self.error:
            raise RuntimeError(self.error)
        if (
            self.runtime_seconds is None
            or self.gpu_peak_temperature is None
            or self.hbm_peak_temperature is None
            or self.gpu_time_frac_idle is None
            or self.nominal_frequency_ghz is None
            or self.hbm_bandwidth_gbps is None
        ):
            raise RuntimeError("IterationResult is incomplete.")
        return (
            self.runtime_seconds,
            self.gpu_peak_temperature,
            self.hbm_peak_temperature,
            self.gpu_time_frac_idle,
            self.nominal_frequency_ghz,
            self.hbm_bandwidth_gbps,
        )


@dataclass(frozen=True)
class LegacyBackendTask:
    key: BackendCacheKey
    rendered_config: str
    model_config_path: str
    output_root: str


@dataclass(frozen=True)
class RapidBackendTask:
    key: BackendCacheKey
    rendered_config: str
    model_config_path: str
    run_perf_path: str
    python_bin: str
    model_run_type: str
    num_layers: int


BackendTask = Union[LegacyBackendTask, RapidBackendTask]
IterationProgressCallback = Callable[[WorkloadConfig, int, int, str], None]


@dataclass
class WorkloadProgress:
    workload: WorkloadConfig
    profile: SystemProfile
    state: IterationState
    runtimes: List[float] = field(default_factory=list)
    gpu_time_frac_idle_list: List[float] = field(default_factory=list)
    gpu_peak_temperature_list: List[float] = field(default_factory=list)
    hbm_peak_temperature_list: List[float] = field(default_factory=list)
    reti: int = -1
    last_nominal_frequency_ghz: float = 1.41
    last_hbm_bandwidth: float = 0.0
    completed: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class TransitionEdge:
    backend_key: BackendCacheKey
    next_state_key: Tuple
    next_state: IterationState
    nominal_frequency_ghz: float
    hbm_bandwidth_gbps: float


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        return "unknown"
    return "unknown"


def _state_key(workload: WorkloadConfig, state: IterationState) -> Tuple:
    return (
        workload.signature(),
        state.iteration_index,
        round(state.gpu_power, 12),
        round(state.hbm_power, 12),
        round(state.gpu_flops_power, 12),
        round(state.current_gpu_peak_temperature, 12),
        round(state.current_hbm_peak_temperature, 12),
        round(state.old_gpu_peak_temperature, 12),
        round(state.old_hbm_peak_temperature, 12),
        round(state.old_old_gpu_peak_temperature, 12),
        round(state.old_old_hbm_peak_temperature, 12),
    )


def _legacy_backend_worker(
    task: LegacyBackendTask,
) -> Tuple[BackendCacheKey, Optional[float], Optional[float], Optional[str]]:
    if run_LLM is None:
        return task.key, None, None, "DeepFlow_llm_dev.run_perf.run_LLM is not available."

    safe_profile_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", task.key.profile_id)
    key_blob = "|".join(map(str, task.key.as_tuple())).encode("utf-8")
    run_id = hashlib.sha1(key_blob).hexdigest()[:12]
    exp_dir = Path(task.output_root) / f"{safe_profile_id}_{run_id}"
    exp_dir.mkdir(parents=True, exist_ok=True)

    fd, temp_path_str = tempfile.mkstemp(prefix=f"{safe_profile_id}_", suffix=".yaml")
    os.close(fd)
    temp_path = Path(temp_path_str)
    run_dir = Path(tempfile.mkdtemp(prefix=f"{safe_profile_id}_run_"))

    try:
        temp_path.write_text(task.rendered_config, encoding="utf-8")
        old_cwd = os.getcwd()
        try:
            os.chdir(run_dir)
            with contextlib.redirect_stdout(None):
                runtime, gpu_time_frac_idle = run_LLM(  # type: ignore[misc]
                    mode="LLM",
                    exp_hw_config_path=str(temp_path),
                    exp_model_config_path=task.model_config_path,
                    exp_dir=str(exp_dir),
                )
        finally:
            os.chdir(old_cwd)
        return task.key, float(runtime), float(gpu_time_frac_idle), None
    except Exception as exc:  # pragma: no cover - backend failures depend on environment.
        return task.key, None, None, str(exc)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp_path.unlink()
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(run_dir)


def _parse_rapid_result_files(
    run_dir: Path,
    *,
    model_run_type: str,
    num_layers: int,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    output_dir = run_dir / "output" / "LLM"
    training_file = output_dir / "LLM_training_results.txt"
    inference_file = output_dir / "LLM_inference_results.txt"
    result_file = inference_file if inference_file.exists() else training_file if training_file.exists() else None
    if result_file is None:
        return None, None, f"Rapid output file not found in {output_dir}."

    text = result_file.read_text(encoding="utf-8", errors="ignore")
    number = r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"

    thermal_idle_matches = re.findall(rf"GPU_time_frac_idle_thermal:\s*{number}", text)
    idle_matches = re.findall(rf"GPU_time_frac_idle:\s*{number}", text)

    runtime_matches = []
    runtime_matches.extend(re.findall(rf"Total Time:\s*{number}", text))
    runtime_matches.extend(re.findall(rf"Inference Time for batch:\s*{number}s", text))
    runtime_matches.extend(re.findall(rf"Total Inference Time:\s*{number}s", text))
    if not runtime_matches:
        return None, None, f"Runtime missing in {result_file}."

    try:
        runtime = float(runtime_matches[-1])
    except ValueError as exc:
        return None, None, f"Failed to parse Rapid metrics from {result_file}: {exc}"

    run_type_normalized = str(model_run_type).strip().lower()
    if thermal_idle_matches:
        try:
            return runtime, float(thermal_idle_matches[-1]), None
        except ValueError as exc:
            return None, None, f"Failed to parse GPU_time_frac_idle_thermal from {result_file}: {exc}"

    if run_type_normalized == "inference":
        # Fallback for older result files that do not emit GPU_time_frac_idle_thermal.
        # Without layer/global idle split, we conservatively scale prefill by layers and
        # keep decode as emitted to avoid severe over-scaling artifacts.
        prefill_time_matches = re.findall(rf"Prefill Time:\s*{number}s", text)
        decode_time_matches = re.findall(rf"Decode Time:\s*{number}s", text)
        prefill_idle_matches = re.findall(rf"Prefill Idle Time:\s*{number}s", text)
        decode_idle_matches = re.findall(rf"Decode Idle Time:\s*{number}s", text)
        if not prefill_time_matches:
            return None, None, f"Prefill Time missing in {result_file}."
        if not decode_time_matches:
            return None, None, f"Decode Time missing in {result_file}."
        if not prefill_idle_matches:
            return None, None, f"Prefill Idle Time missing in {result_file}."
        if not decode_idle_matches:
            return None, None, f"Decode Idle Time missing in {result_file}."
        try:
            prefill_time = float(prefill_time_matches[-1])
            decode_time = float(decode_time_matches[-1])
            prefill_idle = float(prefill_idle_matches[-1])
            decode_idle = float(decode_idle_matches[-1])
        except ValueError as exc:
            return None, None, f"Failed to parse Rapid inference idle components from {result_file}: {exc}"
        total_time = prefill_time + decode_time
        if total_time <= 0.0:
            return None, None, f"Invalid prefill/decode timing in {result_file}."
        layers = max(1, int(num_layers))
        runtime = total_time
        idle = ((prefill_idle * layers) + decode_idle) / total_time
        return runtime, idle, None

    if not idle_matches:
        return None, None, f"GPU_time_frac_idle missing in {result_file}."
    try:
        idle = float(idle_matches[-1])
    except ValueError as exc:
        return None, None, f"Failed to parse GPU_time_frac_idle from {result_file}: {exc}"

    return runtime, idle, None


def _rapid_backend_worker(
    task: RapidBackendTask,
) -> Tuple[BackendCacheKey, Optional[float], Optional[float], Optional[str]]:
    safe_profile_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", task.key.profile_id)
    fd, temp_path_str = tempfile.mkstemp(prefix=f"{safe_profile_id}_", suffix=".yaml")
    os.close(fd)
    temp_path = Path(temp_path_str)
    run_dir = Path(tempfile.mkdtemp(prefix=f"{safe_profile_id}_rapid_run_"))

    try:
        temp_path.write_text(task.rendered_config, encoding="utf-8")
        cmd = [
            task.python_bin,
            task.run_perf_path,
            "--hardware_config",
            str(temp_path),
            "--model_config",
            task.model_config_path,
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            if detail:
                detail = detail.splitlines()[-1]
            return (
                task.key,
                None,
                None,
                f"Rapid run_perf failed (code={proc.returncode}): {detail or 'unknown error'}",
            )

        runtime, idle, parse_error = _parse_rapid_result_files(
            run_dir,
            model_run_type=task.model_run_type,
            num_layers=task.num_layers,
        )
        if parse_error is not None:
            return task.key, None, None, parse_error
        return task.key, float(runtime), float(idle), None
    except Exception as exc:  # pragma: no cover - backend failures depend on environment.
        return task.key, None, None, str(exc)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp_path.unlink()
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(run_dir)


class CalibrationTable:
    """Thermal calibration lookup table keyed by the first 8 CSV columns."""

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path
        self._table: Dict[Tuple, Dict[str, float]] = {}
        self._load()

    def _load(self) -> None:
        with open(self._csv_path, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                key = (
                    row["system_name"],
                    float(row["HBM_power(W)"]),
                    float(row["HTC(kW/(m2K))"]),
                    float(row["TIM_conductivity(W/(mK))"]),
                    float(row["infill_conductivity(W/(mK))"]),
                    float(row["underfill_conductivity(W/(mK))"]),
                    int(row["HBM_stack_height"]),
                    row["dummy_Si"].lower() == "true",
                )
                self._table[key] = {
                    "gpu_slope": float(row["calibrate_GPU_slope"]),
                    "gpu_intercept": float(row["calibrate_GPU_intercept"]),
                    "hbm_slope": float(row["calibrate_HBM_slope"]),
                    "hbm_intercept": float(row["calibrate_HBM_intercept"]),
                }

    def get(self, workload: WorkloadConfig, hbm_power: float) -> Dict[str, float]:
        key = (
            workload.system_name,
            float(hbm_power),
            float(workload.htc),
            float(workload.tim_cond),
            float(workload.infill_cond),
            float(workload.underfill_cond),
            int(workload.hbm_stack_height),
            bool(workload.dummy_si),
        )
        values = self._table.get(key)
        if values is not None:
            return values

        for candidate in (5.0, 5.6, 6.8024, 9.0, 9.4, 10.1218):
            if abs(float(hbm_power) - candidate) > 1e-6:
                continue
            alt_key = (
                workload.system_name,
                candidate,
                float(workload.htc),
                float(workload.tim_cond),
                float(workload.infill_cond),
                float(workload.underfill_cond),
                int(workload.hbm_stack_height),
                bool(workload.dummy_si),
            )
            values = self._table.get(alt_key)
            if values is not None:
                return values

        raise KeyError(f"Calibration entry not found for key: {key}")


class ThermalModel:
    """Calibration-driven thermal predictor."""

    def __init__(self, calibration_table: CalibrationTable) -> None:
        self._calibration_table = calibration_table
        self._temperature_cache: Dict[Tuple, Tuple[float, float]] = {}
        self._cache_lock = threading.Lock()

    def predict_temperatures(
        self,
        workload: WorkloadConfig,
        gpu_power: float,
        hbm_power: float,
    ) -> Tuple[float, float]:
        cache_key = (
            workload.signature(),
            float(hbm_power),
            float(gpu_power),
        )
        with self._cache_lock:
            cached = self._temperature_cache.get(cache_key)
            if cached is not None:
                return cached

        calibration = self._calibration_table.get(workload, hbm_power)
        gpu_temp = float(calibration["gpu_slope"]) * gpu_power + float(calibration["gpu_intercept"])
        hbm_temp = float(calibration["hbm_slope"]) * gpu_power + float(calibration["hbm_intercept"])
        result = (
            ThrottleModel.quantize_temperature(gpu_temp),
            ThrottleModel.quantize_temperature(hbm_temp),
        )

        with self._cache_lock:
            self._temperature_cache[cache_key] = result
        return result


class ThrottleModel:
    """Deterministic legacy throttle/state update logic."""

    GPU_SAFE_TEMPERATURE = 95.0
    BASE_FREQUENCY_HZ = 1.41e9
    BASE_GPU_POWER = 370.0
    BASE_HBM_LATENCY_SEC = 100e-9
    BASE_L2_BW = 7050.0
    BASE_L1_BW = float(18 * 1024)
    BASE_REG_BW = float(122 * 1024)
    GPU_IDLE_POWER = 42.0
    DEFAULT_NUM_LAYERS = 32
    MAX_ITERATIONS = 101

    def __init__(self, num_layers: int = DEFAULT_NUM_LAYERS) -> None:
        self.num_layers = max(1, int(num_layers))

    @staticmethod
    def quantize_temperature(value: float) -> float:
        return round(float(value), 1)

    @staticmethod
    def quantize_hbm_bandwidth(value: float) -> float:
        return float(int(round(float(value) / 10.0) * 10))

    @staticmethod
    def initial_hbm_power(hbm_stack_height: int) -> float:
        if hbm_stack_height == 8:
            return 5.0
        if hbm_stack_height == 16:
            return 9.0
        return 0.0

    def make_initial_state(
        self,
        workload: WorkloadConfig,
        thermal_model: ThermalModel,
    ) -> IterationState:
        initial_hbm_power = self.initial_hbm_power(workload.hbm_stack_height)
        initial_gpu_temp, initial_hbm_temp = thermal_model.predict_temperatures(
            workload=workload,
            gpu_power=self.BASE_GPU_POWER,
            hbm_power=initial_hbm_power,
        )
        return IterationState(
            iteration_index=0,
            gpu_power=self.BASE_GPU_POWER,
            hbm_power=initial_hbm_power,
            gpu_flops_power=self.BASE_GPU_POWER,
            current_gpu_peak_temperature=initial_gpu_temp,
            current_hbm_peak_temperature=initial_hbm_temp,
        )

    def should_continue(self, state: IterationState) -> bool:
        return (
            abs(state.old_hbm_peak_temperature - state.current_hbm_peak_temperature) > 0.1
            or state.current_gpu_peak_temperature > self.GPU_SAFE_TEMPERATURE
        )

    def build_transition_query(
        self,
        state: IterationState,
        profile: SystemProfile,
    ) -> TransitionQuery:
        gpu_temp_q = self.quantize_temperature(state.current_gpu_peak_temperature)
        hbm_temp_q = self.quantize_temperature(state.current_hbm_peak_temperature)
        nominal_frequency_hz, gpu_flops_power_next, register_bw, l1_bw, l2_bw = GPU_FLOPs_throttled(
            GPU_peak_temperature=gpu_temp_q,
            GPU_safe_temperature=self.GPU_SAFE_TEMPERATURE,
            GPU_peak_power=state.gpu_flops_power,
            GPU_average_power=state.gpu_power,
        )
        hbm_bandwidth, hbm_latency, hbm_power_watt = HBM_throttled_performance(
            bandwidth=profile.hbm_bandwidth_reference,
            latency=self.BASE_HBM_LATENCY_SEC,
            HBM_peak_temperature=hbm_temp_q,
            HBM_stack_height=profile.hbm_stack_height,
        )
        hbm_bandwidth = self.quantize_hbm_bandwidth(hbm_bandwidth)

        if state.iteration_index == 0:
            nominal_frequency_hz = self.BASE_FREQUENCY_HZ
            gpu_flops_power_next = self.BASE_GPU_POWER
            hbm_bandwidth = profile.hbm_bandwidth_reference
            hbm_latency = self.BASE_HBM_LATENCY_SEC
            l2_bw = self.BASE_L2_BW
            l1_bw = self.BASE_L1_BW
            register_bw = self.BASE_REG_BW

        backend_input = BackendInput(
            nominal_frequency_ghz=nominal_frequency_hz / 1e9,
            hbm_latency_ns=hbm_latency * 1e9,
            hbm_bandwidth_gbps=hbm_bandwidth,
            l2_bandwidth_gbps=l2_bw,
            l1_bandwidth_gbps=l1_bw,
            register_bandwidth_gbps=register_bw,
        )
        return TransitionQuery(
            backend_input=backend_input,
            hbm_power_next=hbm_power_watt,
            gpu_flops_power_next=gpu_flops_power_next,
            hbm_bandwidth_return_value=hbm_bandwidth,
        )

    def advance_state(
        self,
        state: IterationState,
        workload: WorkloadConfig,
        transition_query: TransitionQuery,
        gpu_time_frac_idle_scaled: float,
        thermal_model: ThermalModel,
    ) -> IterationState:
        gpu_power_next = GPU_throttling(
            GPU_power=transition_query.gpu_flops_power_next,
            GPU_time_frac_idle=gpu_time_frac_idle_scaled,
            GPU_idle_power=self.GPU_IDLE_POWER,
        )
        hbm_power_next = transition_query.hbm_power_next
        gpu_temp_next, hbm_temp_next = thermal_model.predict_temperatures(
            workload=workload,
            gpu_power=gpu_power_next,
            hbm_power=hbm_power_next,
        )
        return IterationState(
            iteration_index=state.iteration_index + 1,
            gpu_power=gpu_power_next,
            hbm_power=hbm_power_next,
            gpu_flops_power=transition_query.gpu_flops_power_next,
            current_gpu_peak_temperature=gpu_temp_next,
            current_hbm_peak_temperature=hbm_temp_next,
            old_gpu_peak_temperature=state.current_gpu_peak_temperature,
            old_hbm_peak_temperature=state.current_hbm_peak_temperature,
            old_old_gpu_peak_temperature=state.old_gpu_peak_temperature,
            old_old_hbm_peak_temperature=state.old_hbm_peak_temperature,
        )


class HardwareConfigRenderer:
    """Renders temporary hardware YAML files without mutating source templates."""

    _PATH_CORE_FREQ = ("tech_param", "core", "operating_frequency")
    _PATH_DRAM_SIZE = ("tech_param", "DRAM", "size")
    _PATH_DRAM_BW = ("tech_param", "DRAM", "bandwidth")
    _PATH_DRAM_LAT = ("tech_param", "DRAM", "latency")
    _PATH_L2_BW = ("tech_param", "SRAM-L2", "bandwidth")
    _PATH_L1_BW = ("tech_param", "SRAM-L1", "bandwidth")
    _PATH_REG_BW = ("tech_param", "SRAM-R", "bandwidth")

    def __init__(self) -> None:
        self._template_cache: Dict[Path, Dict] = {}
        self._cache_lock = threading.Lock()

    def render(self, profile: SystemProfile, backend_input: BackendInput) -> str:
        working = self._get_template_copy(profile.hardware_config_path)
        self._set_path(working, self._PATH_DRAM_SIZE, f"{profile.hbm_size_gb} GB")
        self._set_path(working, self._PATH_CORE_FREQ, float(f"{backend_input.nominal_frequency_ghz:.2f}e9"))
        self._set_path(working, self._PATH_DRAM_BW, f"{math.ceil(backend_input.hbm_bandwidth_gbps)} GB")
        self._set_path(working, self._PATH_DRAM_LAT, float(f"{backend_input.hbm_latency_ns:.1f}e-9"))
        self._set_path(working, self._PATH_L2_BW, f"{math.ceil(backend_input.l2_bandwidth_gbps)} GB")
        self._set_path(working, self._PATH_L1_BW, f"{math.ceil(backend_input.l1_bandwidth_gbps)} GB")
        self._set_path(working, self._PATH_REG_BW, f"{math.ceil(backend_input.register_bandwidth_gbps)} GB")
        rendered = yaml.safe_dump(working, sort_keys=False)
        if not rendered.endswith("\n"):
            rendered += "\n"
        return rendered

    def _get_template_copy(self, path: Path) -> Dict:
        with self._cache_lock:
            cached = self._template_cache.get(path)
            if cached is None:
                with open(path, "r", encoding="utf-8") as handle:
                    loaded = yaml.safe_load(handle)
                if not isinstance(loaded, dict):
                    raise ValueError(f"Hardware template at {path} did not parse into a mapping.")
                self._template_cache[path] = loaded
                cached = loaded
            return copy.deepcopy(cached)

    @staticmethod
    def _set_path(mapping: Dict, path: Tuple[str, ...], value) -> None:
        current = mapping
        for key in path[:-1]:
            next_value = current.get(key)
            if not isinstance(next_value, dict):
                dotted = ".".join(path[:-1])
                raise ValueError(f"Missing mapping path '{dotted}' in hardware template.")
            current = next_value
        leaf = path[-1]
        if leaf not in current:
            dotted = ".".join(path)
            raise ValueError(f"Missing field '{dotted}' in hardware template.")
        current[leaf] = value


class RapidHardwareConfigRenderer(HardwareConfigRenderer):
    """Renderer for Rapid-LLM single-GPU thermal template."""


class PersistentBackendCache:
    """Optional sqlite-backed cache for backend state evaluations."""

    _CORRUPTION_MARKERS = (
        "database disk image is malformed",
        "file is not a database",
        "file is encrypted or is not a database",
        "malformed",
    )

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = self._connect()
        try:
            self._init_schema()
        except sqlite3.DatabaseError as exc:
            if not self._is_corruption_error(exc):
                with contextlib.suppress(sqlite3.Error):
                    self._conn.close()
                raise
            with self._lock:
                self._recover_from_corruption_locked(exc, operation="init")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=60.0)

    def _init_schema(self) -> None:
        with self._lock:
            self._init_schema_locked()

    def _init_schema_locked(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=60000")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backend_cache (
                cache_signature TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                hardware_hash TEXT NOT NULL,
                frequency_centi_ghz INTEGER NOT NULL,
                hbm_latency_ns INTEGER NOT NULL,
                hbm_bandwidth_gbps INTEGER NOT NULL,
                l2_bandwidth_gbps INTEGER NOT NULL,
                l1_bandwidth_gbps INTEGER NOT NULL,
                register_bandwidth_gbps INTEGER NOT NULL,
                runtime_seconds REAL,
                gpu_time_frac_idle REAL,
                error TEXT,
                updated_at_utc TEXT NOT NULL,
                PRIMARY KEY (
                    cache_signature,
                    profile_id,
                    hardware_hash,
                    frequency_centi_ghz,
                    hbm_latency_ns,
                    hbm_bandwidth_gbps,
                    l2_bandwidth_gbps,
                    l1_bandwidth_gbps,
                    register_bandwidth_gbps
                )
            )
            """
        )
        self._conn.commit()

    @classmethod
    def _is_corruption_error(cls, exc: sqlite3.DatabaseError) -> bool:
        message = str(exc).lower()
        return any(marker in message for marker in cls._CORRUPTION_MARKERS)

    def _recover_from_corruption_locked(self, exc: sqlite3.DatabaseError, operation: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        with contextlib.suppress(sqlite3.Error):
            self._conn.close()

        rotated_paths: List[Path] = []
        candidates = [
            self._db_path,
            Path(f"{self._db_path}-wal"),
            Path(f"{self._db_path}-shm"),
            Path(f"{self._db_path}-journal"),
        ]
        for path in candidates:
            if not path.exists():
                continue
            destination = Path(f"{path}.corrupt_{timestamp}")
            suffix_index = 1
            while destination.exists():
                destination = Path(f"{path}.corrupt_{timestamp}_{suffix_index}")
                suffix_index += 1
            with contextlib.suppress(OSError):
                path.replace(destination)
                rotated_paths.append(destination)

        self._conn = self._connect()
        self._init_schema_locked()

        rotated_desc = ", ".join(str(path) for path in rotated_paths) if rotated_paths else str(self._db_path)
        print(
            f"[PersistentBackendCache] Recovered from sqlite corruption during '{operation}': {exc}. "
            f"Rotated files: {rotated_desc}",
            file=sys.stderr,
        )

    def _recover_or_raise_locked(self, exc: sqlite3.DatabaseError, operation: str) -> bool:
        if not self._is_corruption_error(exc):
            return False
        self._recover_from_corruption_locked(exc, operation=operation)
        return True

    def _fetch_row_locked(self, key: BackendCacheKey):
        return self._conn.execute(
            """
            SELECT runtime_seconds, gpu_time_frac_idle, error
            FROM backend_cache
            WHERE cache_signature = ?
              AND profile_id = ?
              AND hardware_hash = ?
              AND frequency_centi_ghz = ?
              AND hbm_latency_ns = ?
              AND hbm_bandwidth_gbps = ?
              AND l2_bandwidth_gbps = ?
              AND l1_bandwidth_gbps = ?
              AND register_bandwidth_gbps = ?
            """,
            key.as_tuple(),
        ).fetchone()

    def get(self, key: BackendCacheKey) -> Optional[BackendResult]:
        with self._lock:
            try:
                row = self._fetch_row_locked(key)
            except sqlite3.DatabaseError as exc:
                if not self._recover_or_raise_locked(exc, operation="get"):
                    raise
                return None
        if row is None:
            return None
        return BackendResult(
            runtime_seconds=float(row[0]) if row[0] is not None else None,
            gpu_time_frac_idle=float(row[1]) if row[1] is not None else None,
            error=row[2],
        )

    def put_many(self, values: Dict[BackendCacheKey, BackendResult]) -> None:
        if not values:
            return
        timestamp = datetime.now(timezone.utc).isoformat()
        rows = []
        for key, result in values.items():
            rows.append(
                key.as_tuple()
                + (
                    result.runtime_seconds,
                    result.gpu_time_frac_idle,
                    result.error,
                    timestamp,
                )
            )
        with self._lock:
            for attempt in range(2):
                try:
                    self._conn.executemany(
                        """
                        INSERT INTO backend_cache (
                            cache_signature,
                            profile_id,
                            hardware_hash,
                            frequency_centi_ghz,
                            hbm_latency_ns,
                            hbm_bandwidth_gbps,
                            l2_bandwidth_gbps,
                            l1_bandwidth_gbps,
                            register_bandwidth_gbps,
                            runtime_seconds,
                            gpu_time_frac_idle,
                            error,
                            updated_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (
                            cache_signature,
                            profile_id,
                            hardware_hash,
                            frequency_centi_ghz,
                            hbm_latency_ns,
                            hbm_bandwidth_gbps,
                            l2_bandwidth_gbps,
                            l1_bandwidth_gbps,
                            register_bandwidth_gbps
                        ) DO UPDATE SET
                            runtime_seconds = excluded.runtime_seconds,
                            gpu_time_frac_idle = excluded.gpu_time_frac_idle,
                            error = excluded.error,
                            updated_at_utc = excluded.updated_at_utc
                        """,
                        rows,
                    )
                    self._conn.commit()
                    return
                except sqlite3.DatabaseError as exc:
                    if attempt == 1 or not self._recover_or_raise_locked(exc, operation="put_many"):
                        raise

    def close(self) -> None:
        with self._lock:
            with contextlib.suppress(sqlite3.Error):
                self._conn.close()


class LegacyBackendRunner:
    """Parallel legacy backend evaluator with in-memory + sqlite caching."""

    def __init__(
        self,
        model_config_path: Path,
        output_root: Path,
        renderer: HardwareConfigRenderer,
        cache_signature: str,
        persistent_cache_path: Optional[Path] = None,
        max_workers: int = 100,
    ) -> None:
        if run_LLM is None:
            raise RuntimeError("DeepFlow_llm_dev.run_perf.run_LLM is not available.")

        self._model_config_path = model_config_path
        self._output_root = output_root
        self._output_root.mkdir(parents=True, exist_ok=True)
        self._renderer = renderer
        self._cache_signature = cache_signature

        self._max_workers = max(1, min(max_workers, os.cpu_count() or 1))
        self._executor = ProcessPoolExecutor(max_workers=self._max_workers)

        self._memory_cache: Dict[BackendCacheKey, BackendResult] = {}
        self._lock = threading.Lock()

        self._persistent_cache = (
            PersistentBackendCache(persistent_cache_path)
            if persistent_cache_path is not None
            else None
        )

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        if self._persistent_cache is not None:
            self._persistent_cache.close()

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def make_key(self, profile: SystemProfile, backend_input: BackendInput) -> BackendCacheKey:
        rounded_freq = round(backend_input.nominal_frequency_ghz, 2)
        return BackendCacheKey(
            cache_signature=self._cache_signature,
            profile_id=profile.profile_id,
            hardware_hash=profile.hardware_hash,
            frequency_centi_ghz=int(round(rounded_freq * 100)),
            hbm_latency_ns=int(backend_input.hbm_latency_ns),
            hbm_bandwidth_gbps=int(ThrottleModel.quantize_hbm_bandwidth(backend_input.hbm_bandwidth_gbps)),
            l2_bandwidth_gbps=int(backend_input.l2_bandwidth_gbps),
            l1_bandwidth_gbps=int(backend_input.l1_bandwidth_gbps),
            register_bandwidth_gbps=int(backend_input.register_bandwidth_gbps),
        )

    def lookup(self, key: BackendCacheKey) -> Optional[BackendResult]:
        with self._lock:
            cached = self._memory_cache.get(key)
            if cached is not None:
                return cached

        if self._persistent_cache is not None:
            persistent = self._persistent_cache.get(key)
            if persistent is not None:
                with self._lock:
                    self._memory_cache[key] = persistent
                return persistent
        return None

    def build_task(self, profile: SystemProfile, backend_input: BackendInput, key: BackendCacheKey) -> LegacyBackendTask:
        rendered_config = self._renderer.render(profile, backend_input)
        return LegacyBackendTask(
            key=key,
            rendered_config=rendered_config,
            model_config_path=str(self._model_config_path),
            output_root=str(self._output_root),
        )

    def prefetch(self, tasks: Iterable[LegacyBackendTask]) -> Dict[BackendCacheKey, BackendResult]:
        task_map: Dict[BackendCacheKey, LegacyBackendTask] = {}
        for task in tasks:
            if task.key not in task_map:
                task_map[task.key] = task

        unresolved: Dict[BackendCacheKey, LegacyBackendTask] = {}
        for key, task in task_map.items():
            if self.lookup(key) is None:
                unresolved[key] = task

        if not unresolved:
            return {}

        results: Dict[BackendCacheKey, BackendResult] = {}
        for attempt in range(2):
            if not unresolved:
                break

            future_to_key = {
                self._executor.submit(_legacy_backend_worker, task): key
                for key, task in unresolved.items()
            }
            failed_next_attempt: Dict[BackendCacheKey, LegacyBackendTask] = {}

            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    result_key, runtime, idle, error = future.result()
                except Exception as exc:  # pragma: no cover - process pool errors are environment dependent.
                    result = BackendResult(runtime_seconds=None, gpu_time_frac_idle=None, error=str(exc))
                    results[key] = result
                    if attempt == 0:
                        failed_next_attempt[key] = unresolved[key]
                    continue

                if result_key != key:
                    result = BackendResult(
                        runtime_seconds=None,
                        gpu_time_frac_idle=None,
                        error="Backend worker returned mismatched cache key.",
                    )
                    results[key] = result
                    if attempt == 0:
                        failed_next_attempt[key] = unresolved[key]
                    continue

                result = BackendResult(runtime_seconds=runtime, gpu_time_frac_idle=idle, error=error)
                results[key] = result
                if error is not None and attempt == 0:
                    failed_next_attempt[key] = unresolved[key]

            unresolved = failed_next_attempt

        with self._lock:
            self._memory_cache.update(results)
        if self._persistent_cache is not None:
            self._persistent_cache.put_many(results)
        return results


class RapidBackendRunner:
    """Parallel Rapid backend evaluator with in-memory + sqlite caching."""

    def __init__(
        self,
        model_config_path: Path,
        run_perf_path: Path,
        python_bin: str,
        renderer: HardwareConfigRenderer,
        cache_signature: str,
        model_run_type: str,
        num_layers: int,
        persistent_cache_path: Optional[Path] = None,
        max_workers: int = 100,
    ) -> None:
        if not run_perf_path.exists():
            raise FileNotFoundError(run_perf_path)

        self._model_config_path = model_config_path
        self._run_perf_path = run_perf_path
        self._python_bin = python_bin
        self._renderer = renderer
        self._cache_signature = cache_signature
        self._model_run_type = str(model_run_type).strip().lower()
        self._num_layers = max(1, int(num_layers))

        self._max_workers = max(1, min(max_workers, os.cpu_count() or 1))
        self._executor = ProcessPoolExecutor(max_workers=self._max_workers)

        self._memory_cache: Dict[BackendCacheKey, BackendResult] = {}
        self._lock = threading.Lock()
        self._persistent_cache = (
            PersistentBackendCache(persistent_cache_path)
            if persistent_cache_path is not None
            else None
        )

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        if self._persistent_cache is not None:
            self._persistent_cache.close()

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def make_key(self, profile: SystemProfile, backend_input: BackendInput) -> BackendCacheKey:
        rounded_freq = round(backend_input.nominal_frequency_ghz, 2)
        return BackendCacheKey(
            cache_signature=self._cache_signature,
            profile_id=profile.profile_id,
            hardware_hash=profile.hardware_hash,
            frequency_centi_ghz=int(round(rounded_freq * 100)),
            hbm_latency_ns=int(backend_input.hbm_latency_ns),
            hbm_bandwidth_gbps=int(ThrottleModel.quantize_hbm_bandwidth(backend_input.hbm_bandwidth_gbps)),
            l2_bandwidth_gbps=int(backend_input.l2_bandwidth_gbps),
            l1_bandwidth_gbps=int(backend_input.l1_bandwidth_gbps),
            register_bandwidth_gbps=int(backend_input.register_bandwidth_gbps),
        )

    def lookup(self, key: BackendCacheKey) -> Optional[BackendResult]:
        with self._lock:
            cached = self._memory_cache.get(key)
            if cached is not None:
                return cached

        if self._persistent_cache is not None:
            persistent = self._persistent_cache.get(key)
            if persistent is not None:
                with self._lock:
                    self._memory_cache[key] = persistent
                return persistent
        return None

    def build_task(self, profile: SystemProfile, backend_input: BackendInput, key: BackendCacheKey) -> RapidBackendTask:
        rendered_config = self._renderer.render(profile, backend_input)
        return RapidBackendTask(
            key=key,
            rendered_config=rendered_config,
            model_config_path=str(self._model_config_path),
            run_perf_path=str(self._run_perf_path),
            python_bin=self._python_bin,
            model_run_type=self._model_run_type,
            num_layers=self._num_layers,
        )

    def prefetch(self, tasks: Iterable[RapidBackendTask]) -> Dict[BackendCacheKey, BackendResult]:
        task_map: Dict[BackendCacheKey, RapidBackendTask] = {}
        for task in tasks:
            if task.key not in task_map:
                task_map[task.key] = task

        unresolved: Dict[BackendCacheKey, RapidBackendTask] = {}
        for key, task in task_map.items():
            if self.lookup(key) is None:
                unresolved[key] = task

        if not unresolved:
            return {}

        results: Dict[BackendCacheKey, BackendResult] = {}
        for attempt in range(2):
            if not unresolved:
                break

            future_to_key = {
                self._executor.submit(_rapid_backend_worker, task): key
                for key, task in unresolved.items()
            }
            failed_next_attempt: Dict[BackendCacheKey, RapidBackendTask] = {}

            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    result_key, runtime, idle, error = future.result()
                except Exception as exc:  # pragma: no cover - process pool errors are environment dependent.
                    result = BackendResult(runtime_seconds=None, gpu_time_frac_idle=None, error=str(exc))
                    results[key] = result
                    if attempt == 0:
                        failed_next_attempt[key] = unresolved[key]
                    continue

                if result_key != key:
                    result = BackendResult(
                        runtime_seconds=None,
                        gpu_time_frac_idle=None,
                        error="Backend worker returned mismatched cache key.",
                    )
                    results[key] = result
                    if attempt == 0:
                        failed_next_attempt[key] = unresolved[key]
                    continue

                result = BackendResult(runtime_seconds=runtime, gpu_time_frac_idle=idle, error=error)
                results[key] = result
                if error is not None and attempt == 0:
                    failed_next_attempt[key] = unresolved[key]

            unresolved = failed_next_attempt

        with self._lock:
            self._memory_cache.update(results)
        if self._persistent_cache is not None:
            self._persistent_cache.put_many(results)
        return results


class StateSpaceEngine:
    """Parallel state discovery + deterministic in-memory convergence solver."""

    def __init__(
        self,
        thermal_model: ThermalModel,
        throttle_model: ThrottleModel,
        backend_runner: Union[LegacyBackendRunner, RapidBackendRunner],
        idle_scale: float = 1.0,
        speculative_misses: int = 0,
        progress_callback: Optional[IterationProgressCallback] = None,
    ) -> None:
        self._thermal_model = thermal_model
        self._throttle_model = throttle_model
        self._backend_runner = backend_runner
        self._idle_scale = float(idle_scale)
        self._speculative_misses = max(0, int(speculative_misses))
        self._progress_callback = progress_callback
        self.transition_map: Dict[Tuple, TransitionEdge] = {}
        self._progress_by_signature: Dict[Tuple, WorkloadProgress] = {}

    @staticmethod
    def _clamp_idle_fraction(value: float) -> float:
        try:
            parsed = float(value)
        except Exception:
            return 0.0
        if not math.isfinite(parsed):
            return 0.0
        if parsed < 0.0:
            return 0.0
        if parsed > 1.0:
            return 1.0
        return parsed

    def _emit_iteration_progress(
        self,
        workload: WorkloadConfig,
        iteration_index: int,
        phase: str,
    ) -> None:
        callback = self._progress_callback
        if callback is None:
            return
        max_iterations_display = max(1, int(self._throttle_model.MAX_ITERATIONS) - 1)
        try:
            callback(workload, int(iteration_index), max_iterations_display, phase)
        except Exception:
            # Progress reporting must never affect execution.
            return

    def run_workloads(self, workloads: Sequence[WorkloadConfig], profiles: Dict[Tuple, SystemProfile]) -> List[IterationResult]:
        if not workloads:
            return []

        unique_workloads = self._dedupe_workloads(workloads)
        self.precompute_table(unique_workloads, profiles)

        result_by_signature: Dict[Tuple, IterationResult] = {}
        for workload in unique_workloads:
            profile = profiles[workload.signature()]
            if workload.no_throttle:
                result_by_signature[workload.signature()] = self._run_no_throttle_workload(workload, profile)
            else:
                result_by_signature[workload.signature()] = self._solve_workload_from_transition_map(workload, profile)

        return [result_by_signature[workload.signature()] for workload in workloads]

    def precompute_table(self, workloads: Sequence[WorkloadConfig], profiles: Dict[Tuple, SystemProfile]) -> None:
        self.transition_map = {}
        throttle_workloads = [workload for workload in workloads if not workload.no_throttle]
        if not throttle_workloads:
            self._progress_by_signature = {}
            return
        progresses = [self._make_progress(workload, profiles[workload.signature()]) for workload in throttle_workloads]
        self._precompute_reachable_states(progresses)
        self._progress_by_signature = {progress.workload.signature(): progress for progress in progresses}

    def _baseline_backend_input(self, profile: SystemProfile) -> BackendInput:
        return BackendInput(
            nominal_frequency_ghz=self._throttle_model.BASE_FREQUENCY_HZ / 1e9,
            hbm_latency_ns=self._throttle_model.BASE_HBM_LATENCY_SEC * 1e9,
            hbm_bandwidth_gbps=profile.hbm_bandwidth_reference,
            l2_bandwidth_gbps=self._throttle_model.BASE_L2_BW,
            l1_bandwidth_gbps=self._throttle_model.BASE_L1_BW,
            register_bandwidth_gbps=self._throttle_model.BASE_REG_BW,
        )

    def _run_no_throttle_workload(self, workload: WorkloadConfig, profile: SystemProfile) -> IterationResult:
        initial_state = self._throttle_model.make_initial_state(workload, self._thermal_model)
        backend_input = self._baseline_backend_input(profile)
        backend_key = self._backend_runner.make_key(profile, backend_input)
        backend_result = self._backend_runner.lookup(backend_key)
        if backend_result is None:
            task = self._backend_runner.build_task(profile, backend_input, backend_key)
            self._backend_runner.prefetch([task])
            backend_result = self._backend_runner.lookup(backend_key)

        if backend_result is None:
            return IterationResult(
                workload=workload,
                runtime_seconds=None,
                gpu_peak_temperature=None,
                hbm_peak_temperature=None,
                gpu_time_frac_idle=None,
                nominal_frequency_ghz=None,
                hbm_bandwidth_gbps=None,
                error=f"Missing baseline backend state: {backend_key}",
            )
        if backend_result.error:
            return IterationResult(
                workload=workload,
                runtime_seconds=None,
                gpu_peak_temperature=None,
                hbm_peak_temperature=None,
                gpu_time_frac_idle=None,
                nominal_frequency_ghz=None,
                hbm_bandwidth_gbps=None,
                error=f"Backend error for baseline state {backend_key}: {backend_result.error}",
            )
        if backend_result.runtime_seconds is None or backend_result.gpu_time_frac_idle is None:
            return IterationResult(
                workload=workload,
                runtime_seconds=None,
                gpu_peak_temperature=None,
                hbm_peak_temperature=None,
                gpu_time_frac_idle=None,
                nominal_frequency_ghz=None,
                hbm_bandwidth_gbps=None,
                error=f"Incomplete baseline backend result for state {backend_key}.",
            )

        scaled_idle = self._clamp_idle_fraction(backend_result.gpu_time_frac_idle * self._idle_scale)
        return IterationResult(
            workload=workload,
            runtime_seconds=float(backend_result.runtime_seconds),
            gpu_peak_temperature=initial_state.current_gpu_peak_temperature,
            hbm_peak_temperature=initial_state.current_hbm_peak_temperature,
            gpu_time_frac_idle=scaled_idle,
            nominal_frequency_ghz=backend_input.nominal_frequency_ghz,
            hbm_bandwidth_gbps=backend_input.hbm_bandwidth_gbps,
            error=None,
        )

    @staticmethod
    def _dedupe_workloads(workloads: Sequence[WorkloadConfig]) -> List[WorkloadConfig]:
        seen: Dict[Tuple, WorkloadConfig] = {}
        for workload in workloads:
            seen.setdefault(workload.signature(), workload)
        return list(seen.values())

    def _make_progress(self, workload: WorkloadConfig, profile: SystemProfile) -> WorkloadProgress:
        initial_state = self._throttle_model.make_initial_state(workload, self._thermal_model)
        return WorkloadProgress(
            workload=workload,
            profile=profile,
            state=initial_state,
            gpu_peak_temperature_list=[initial_state.current_gpu_peak_temperature],
            hbm_peak_temperature_list=[initial_state.current_hbm_peak_temperature],
            last_hbm_bandwidth=profile.hbm_bandwidth_reference,
            last_nominal_frequency_ghz=self._throttle_model.BASE_FREQUENCY_HZ / 1e9,
        )

    def _precompute_reachable_states(self, progresses: Sequence[WorkloadProgress]) -> None:
        # Discover all backend states needed by the workload set, evaluating unknown states in parallel.
        # After this phase, convergence can run in-memory with no backend calls.
        rounds = 0
        while True:
            rounds += 1
            active_count = 0
            pending_tasks: Dict[BackendCacheKey, BackendTask] = {}

            for progress in progresses:
                if progress.completed or progress.error:
                    continue
                active_count += 1
                maybe_tasks = self._advance_progress_until_blocked(progress)
                if maybe_tasks:
                    for task in maybe_tasks:
                        pending_tasks.setdefault(task.key, task)

            if active_count == 0:
                break
            if not pending_tasks:
                if rounds > 10000:
                    raise RuntimeError("State-space discovery exceeded safety round limit.")
                continue

            self._backend_runner.prefetch(pending_tasks.values())

    def _advance_progress_until_blocked(self, progress: WorkloadProgress) -> Optional[List[BackendTask]]:
        while True:
            if not self._throttle_model.should_continue(progress.state):
                progress.completed = True
                return None

            transition_query = self._throttle_model.build_transition_query(progress.state, progress.profile)
            progress.last_nominal_frequency_ghz = transition_query.backend_input.nominal_frequency_ghz
            progress.last_hbm_bandwidth = transition_query.hbm_bandwidth_return_value

            key = self._backend_runner.make_key(progress.profile, transition_query.backend_input)
            backend_result = self._backend_runner.lookup(key)
            if backend_result is None:
                return self._build_prefetch_batch(progress, transition_query, key)
            if backend_result.error:
                progress.error = backend_result.error
                progress.completed = True
                return None
            if backend_result.runtime_seconds is None or backend_result.gpu_time_frac_idle is None:
                progress.error = "Backend result missing runtime/idle values."
                progress.completed = True
                return None

            scaled_idle = self._clamp_idle_fraction(backend_result.gpu_time_frac_idle * self._idle_scale)
            progress.runtimes.append(backend_result.runtime_seconds)
            progress.gpu_time_frac_idle_list.append(scaled_idle)

            previous_state = progress.state
            next_state = self._throttle_model.advance_state(
                state=previous_state,
                workload=progress.workload,
                transition_query=transition_query,
                gpu_time_frac_idle_scaled=scaled_idle,
                thermal_model=self._thermal_model,
            )
            self._record_transition(
                progress.workload,
                previous_state,
                transition_query,
                key,
                next_state,
            )
            progress.state = next_state
            self._emit_iteration_progress(
                progress.workload,
                progress.state.iteration_index,
                phase="precompute",
            )
            progress.gpu_peak_temperature_list.append(next_state.current_gpu_peak_temperature)
            progress.hbm_peak_temperature_list.append(next_state.current_hbm_peak_temperature)

            if progress.state.iteration_index >= self._throttle_model.MAX_ITERATIONS:
                progress.completed = True
                return None
            if progress.state.current_gpu_peak_temperature == progress.state.old_old_gpu_peak_temperature:
                if len(progress.runtimes) > 1 and progress.runtimes[-1] < progress.runtimes[-2]:
                    progress.reti = -2
                progress.completed = True
                return None

    def _build_prefetch_batch(
        self,
        progress: WorkloadProgress,
        mandatory_query: TransitionQuery,
        mandatory_key: BackendCacheKey,
    ) -> List[BackendTask]:
        # One mandatory key + speculative keys around target.
        tasks: Dict[BackendCacheKey, BackendTask] = {}
        target_input = mandatory_query.backend_input
        tasks[mandatory_key] = self._backend_runner.build_task(progress.profile, target_input, mandatory_key)

        seen = set(tasks.keys())
        target_bw = ThrottleModel.quantize_hbm_bandwidth(target_input.hbm_bandwidth_gbps)
        low_bw = ThrottleModel.quantize_hbm_bandwidth(progress.profile.hbm_bandwidth_reference * 0.732)
        high_bw = ThrottleModel.quantize_hbm_bandwidth(progress.profile.hbm_bandwidth_reference)

        target_freq_centi = int(round(round(target_input.nominal_frequency_ghz, 2) * 100))
        target_latency_ns = float(target_input.hbm_latency_ns)

        def _build_candidate(step: int, sign: int) -> BackendInput:
            # Non-linear spacing by polynomial growth.
            bw_mag = max(1, int(round(step ** 1.32)))
            fr_mag = max(1, int(round(step ** 1.18)))

            candidate_bw = target_bw + float(sign * bw_mag * 10)
            candidate_bw = max(low_bw, min(high_bw, ThrottleModel.quantize_hbm_bandwidth(candidate_bw)))

            freq_centi = max(0, target_freq_centi + sign * fr_mag)
            freq_ghz = freq_centi / 100.0

            if target_freq_centi > 0:
                scale = freq_centi / float(target_freq_centi)
            else:
                scale = 1.0

            l2_bw = max(1.0, round(target_input.l2_bandwidth_gbps * scale))
            l1_bw = max(1.0, round(target_input.l1_bandwidth_gbps * scale))
            reg_bw = max(1.0, round(target_input.register_bandwidth_gbps * scale))

            # Keep latency on quantized legacy levels.
            if target_latency_ns >= 171.4:
                latency_ns = 171.4
            elif target_latency_ns >= 123.8:
                latency_ns = 123.8
            else:
                latency_ns = 100.0

            return BackendInput(
                nominal_frequency_ghz=freq_ghz,
                hbm_latency_ns=latency_ns,
                hbm_bandwidth_gbps=candidate_bw,
                l2_bandwidth_gbps=l2_bw,
                l1_bandwidth_gbps=l1_bw,
                register_bandwidth_gbps=reg_bw,
            )

        # Speculation is explicitly controlled; disabled by default.
        # 1 mandatory + N speculative, where N = speculative_misses.
        speculative_target = self._speculative_misses
        max_total = 1 + speculative_target
        step = 1
        while len(tasks) < max_total and step <= 2000:
            for sign in (-1, 1):
                if len(tasks) >= max_total:
                    break
                candidate = _build_candidate(step, sign)
                key = self._backend_runner.make_key(progress.profile, candidate)
                if key in seen:
                    continue
                seen.add(key)
                tasks[key] = self._backend_runner.build_task(progress.profile, candidate, key)
            step += 1

        return list(tasks.values())

    def _solve_workload_from_transition_map(self, workload: WorkloadConfig, profile: SystemProfile) -> IterationResult:
        progress = self._progress_by_signature.get(workload.signature())
        if progress is not None and progress.error:
            return IterationResult(
                workload=workload,
                runtime_seconds=None,
                gpu_peak_temperature=None,
                hbm_peak_temperature=None,
                gpu_time_frac_idle=None,
                nominal_frequency_ghz=None,
                hbm_bandwidth_gbps=None,
                error=progress.error,
            )

        state = self._throttle_model.make_initial_state(workload, self._thermal_model)
        runtimes: List[float] = []
        gpu_time_frac_idle_list: List[float] = []
        gpu_peak_temperature_list: List[float] = [state.current_gpu_peak_temperature]
        hbm_peak_temperature_list: List[float] = [state.current_hbm_peak_temperature]

        last_nominal_frequency_ghz = self._throttle_model.BASE_FREQUENCY_HZ / 1e9
        last_hbm_bandwidth = profile.hbm_bandwidth_reference
        reti = -1

        while self._throttle_model.should_continue(state):
            edge = self.transition_map.get(_state_key(workload, state))
            if edge is None:
                return IterationResult(
                    workload=workload,
                    runtime_seconds=None,
                    gpu_peak_temperature=None,
                    hbm_peak_temperature=None,
                    gpu_time_frac_idle=None,
                    nominal_frequency_ghz=None,
                    hbm_bandwidth_gbps=None,
                    error=f"Missing transition edge for state {_state_key(workload, state)}.",
                )

            last_nominal_frequency_ghz = edge.nominal_frequency_ghz
            last_hbm_bandwidth = edge.hbm_bandwidth_gbps

            backend_result = self._backend_runner.lookup(edge.backend_key)
            if backend_result is None:
                return IterationResult(
                    workload=workload,
                    runtime_seconds=None,
                    gpu_peak_temperature=None,
                    hbm_peak_temperature=None,
                    gpu_time_frac_idle=None,
                    nominal_frequency_ghz=None,
                    hbm_bandwidth_gbps=None,
                    error=f"Missing precomputed backend state: {edge.backend_key}",
                )
            if backend_result.error:
                return IterationResult(
                    workload=workload,
                    runtime_seconds=None,
                    gpu_peak_temperature=None,
                    hbm_peak_temperature=None,
                    gpu_time_frac_idle=None,
                    nominal_frequency_ghz=None,
                    hbm_bandwidth_gbps=None,
                    error=f"Backend error for state {edge.backend_key}: {backend_result.error}",
                )
            if backend_result.runtime_seconds is None or backend_result.gpu_time_frac_idle is None:
                return IterationResult(
                    workload=workload,
                    runtime_seconds=None,
                    gpu_peak_temperature=None,
                    hbm_peak_temperature=None,
                    gpu_time_frac_idle=None,
                    nominal_frequency_ghz=None,
                    hbm_bandwidth_gbps=None,
                    error=f"Incomplete backend result for state {edge.backend_key}.",
                )

            scaled_idle = self._clamp_idle_fraction(backend_result.gpu_time_frac_idle * self._idle_scale)
            runtimes.append(backend_result.runtime_seconds)
            gpu_time_frac_idle_list.append(scaled_idle)

            state = edge.next_state
            self._emit_iteration_progress(
                workload,
                state.iteration_index,
                phase="solve",
            )
            gpu_peak_temperature_list.append(state.current_gpu_peak_temperature)
            hbm_peak_temperature_list.append(state.current_hbm_peak_temperature)

            if state.iteration_index >= self._throttle_model.MAX_ITERATIONS:
                break
            if state.current_gpu_peak_temperature == state.old_old_gpu_peak_temperature:
                if len(runtimes) > 1 and runtimes[-1] < runtimes[-2]:
                    reti = -2
                break

        if not runtimes:
            return IterationResult(
                workload=workload,
                runtime_seconds=None,
                gpu_peak_temperature=None,
                hbm_peak_temperature=None,
                gpu_time_frac_idle=None,
                nominal_frequency_ghz=None,
                hbm_bandwidth_gbps=None,
                error="No iterations were executed for this workload.",
            )

        return IterationResult(
            workload=workload,
            runtime_seconds=runtimes[reti],
            gpu_peak_temperature=gpu_peak_temperature_list[reti],
            hbm_peak_temperature=hbm_peak_temperature_list[reti],
            gpu_time_frac_idle=gpu_time_frac_idle_list[reti],
            nominal_frequency_ghz=last_nominal_frequency_ghz,
            hbm_bandwidth_gbps=last_hbm_bandwidth,
            error=None,
        )

    def _record_transition(
        self,
        workload: WorkloadConfig,
        current_state: IterationState,
        transition_query: TransitionQuery,
        backend_key: BackendCacheKey,
        next_state: IterationState,
    ) -> None:
        from_key = _state_key(workload, current_state)
        to_key = _state_key(workload, next_state)
        self.transition_map[from_key] = TransitionEdge(
            backend_key=backend_key,
            next_state_key=to_key,
            next_state=next_state,
            nominal_frequency_ghz=transition_query.backend_input.nominal_frequency_ghz,
            hbm_bandwidth_gbps=transition_query.hbm_bandwidth_return_value,
        )


class ThermalAnalysisGeorge:
    """Legacy-compatible API with state-space precompute + in-memory convergence solve."""

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        calibration_csv_path: str = "calibration_data.csv",
        persistent_cache_path: Optional[str] = "dedeepyo_integration/state_cache.sqlite",
        backend_workers: int = 1,
        speculative_misses: int = 0,
        backend_kind: Literal["legacy", "rapid"] = "legacy",
        rapid_python_bin: str = _DEFAULT_RAPID_PYTHON,
        rapid_hardware_config_path: str = "dedeepyo_integration/Rapid-LLM/configs/hardware-config/a100_80GB_legacy_thermal_port.yaml",
        legacy_model_config_path: str = "DeepFlow_llm_dev/configs/model-config/LLM_thermal.yaml",
        rapid_model_config_path: str = "dedeepyo_integration/Rapid-LLM/configs/model-config/Llama2-7B_train_2048_thermal.yaml",
        progress_callback: Optional[IterationProgressCallback] = None,
    ) -> None:
        self._repo_root = repo_root or Path(__file__).resolve().parents[1]
        self._backend_kind = backend_kind.strip().lower()
        if self._backend_kind not in {"legacy", "rapid"}:
            raise ValueError(f"Unsupported backend_kind: {backend_kind}")

        self._legacy_hardware_config_dir = self._repo_root / "DeepFlow_llm_dev" / "configs" / "hardware-config"
        legacy_model_path = Path(legacy_model_config_path)
        if not legacy_model_path.is_absolute():
            legacy_model_path = self._repo_root / legacy_model_path
        self._legacy_model_config_path = legacy_model_path
        self._legacy_run_perf_path = self._repo_root / "DeepFlow_llm_dev" / "run_perf.py"

        rapid_hardware_path = Path(rapid_hardware_config_path)
        if not rapid_hardware_path.is_absolute():
            rapid_hardware_path = self._repo_root / rapid_hardware_path
        self._rapid_hardware_template_path = rapid_hardware_path
        rapid_model_path = Path(rapid_model_config_path)
        if not rapid_model_path.is_absolute():
            rapid_model_path = self._repo_root / rapid_model_path
        self._rapid_model_config_path = rapid_model_path
        self._rapid_run_perf_path = self._repo_root / "dedeepyo_integration" / "Rapid-LLM" / "run_perf.py"
        self._rapid_python_bin = self._resolve_python_bin(rapid_python_bin)

        if self._backend_kind == "legacy":
            self._model_config_path = self._legacy_model_config_path
            self._run_perf_path = self._legacy_run_perf_path
            self._renderer: Union[HardwareConfigRenderer, RapidHardwareConfigRenderer] = HardwareConfigRenderer()
        else:
            self._model_config_path = self._rapid_model_config_path
            self._run_perf_path = self._rapid_run_perf_path
            self._renderer = RapidHardwareConfigRenderer()

        calibration_path = Path(calibration_csv_path)
        if not calibration_path.is_absolute():
            calibration_path = self._repo_root / calibration_path

        if not calibration_path.exists():
            raise FileNotFoundError(calibration_path)
        if self._backend_kind == "rapid" and not self._rapid_hardware_template_path.exists():
            raise FileNotFoundError(self._rapid_hardware_template_path)
        if not self._model_config_path.exists():
            raise FileNotFoundError(self._model_config_path)
        if not self._run_perf_path.exists():
            raise FileNotFoundError(self._run_perf_path)

        self._num_layers = self._read_model_num_layers(self._model_config_path)
        self._model_run_type = self._read_model_run_type(self._model_config_path)
        if self._backend_kind == "rapid":
            # Rapid backend now emits run-level thermal-ready idle fractions.
            self._idle_scale = 1.0
        else:
            self._idle_scale = float(self._num_layers if self._model_run_type != "inference" else 1.0)
        self._cache_signature = self._build_cache_signature()
        self._thermal_model = ThermalModel(CalibrationTable(calibration_path))
        self._throttle_model = ThrottleModel(num_layers=self._num_layers)

        persistent_db_path = None
        if persistent_cache_path:
            persistent_db_path = Path(persistent_cache_path)
            if not persistent_db_path.is_absolute():
                persistent_db_path = self._repo_root / persistent_db_path

        if self._backend_kind == "legacy":
            self._backend_runner: Union[LegacyBackendRunner, RapidBackendRunner] = LegacyBackendRunner(
                model_config_path=self._model_config_path,
                output_root=self._repo_root / "output_george_legacy",
                renderer=self._renderer,
                cache_signature=self._cache_signature,
                persistent_cache_path=persistent_db_path,
                max_workers=backend_workers,
            )
        else:
            self._backend_runner = RapidBackendRunner(
                model_config_path=self._model_config_path,
                run_perf_path=self._run_perf_path,
                python_bin=self._rapid_python_bin,
                renderer=self._renderer,
                cache_signature=self._cache_signature,
                model_run_type=self._model_run_type,
                num_layers=self._num_layers,
                persistent_cache_path=persistent_db_path,
                max_workers=backend_workers,
            )
        self._state_space_engine = StateSpaceEngine(
            thermal_model=self._thermal_model,
            throttle_model=self._throttle_model,
            backend_runner=self._backend_runner,
            idle_scale=self._idle_scale,
            speculative_misses=speculative_misses,
            progress_callback=progress_callback,
        )

    def close(self) -> None:
        self._backend_runner.close()

    def __enter__(self) -> "ThermalAnalysisGeorge":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def iterations(
        self,
        system_name: str,
        HTC: float,
        TIM_cond: float,
        infill_cond: float,
        underfill_cond: float,
        HBM_stack_height: int,
        dummy_Si: bool,
        no_throttle: bool = False,
    ) -> Tuple[float, float, float, float, float, float]:
        workload = WorkloadConfig(
            system_name=system_name,
            htc=HTC,
            tim_cond=TIM_cond,
            infill_cond=infill_cond,
            underfill_cond=underfill_cond,
            hbm_stack_height=HBM_stack_height,
            dummy_si=dummy_Si,
            no_throttle=no_throttle,
        )
        profile = self._resolve_profile(system_name, HBM_stack_height)
        result = self._state_space_engine.run_workloads([workload], {workload.signature(): profile})[0]
        return result.as_tuple()

    def run_parallel(
        self,
        workloads: Sequence[WorkloadConfig],
    ) -> List[Tuple[float, float, float, float, float, float]]:
        profiles = {workload.signature(): self._resolve_profile(workload.system_name, workload.hbm_stack_height) for workload in workloads}
        results = self._state_space_engine.run_workloads(workloads, profiles)
        return [result.as_tuple() for result in results]

    def precompute_table(self, workloads: Sequence[WorkloadConfig]) -> int:
        profiles = {workload.signature(): self._resolve_profile(workload.system_name, workload.hbm_stack_height) for workload in workloads}
        unique_workloads: Dict[Tuple, WorkloadConfig] = {}
        for workload in workloads:
            unique_workloads.setdefault(workload.signature(), workload)
        self._state_space_engine.precompute_table(list(unique_workloads.values()), profiles)
        return self.get_transition_map_size()

    def get_transition_map_size(self) -> int:
        return len(self._state_space_engine.transition_map)

    @property
    def backend_kind(self) -> str:
        return self._backend_kind

    @staticmethod
    def _resolve_python_bin(raw_python_bin: str) -> str:
        candidate = Path(raw_python_bin)
        if candidate.is_absolute():
            if not candidate.exists():
                raise FileNotFoundError(candidate)
            return str(candidate)
        resolved = shutil.which(raw_python_bin)
        if resolved is None:
            raise FileNotFoundError(f"Python binary not found: {raw_python_bin}")
        return resolved

    def _resolve_profile(self, system_name: str, hbm_stack_height: int) -> SystemProfile:
        if system_name == "3D_waferscale":
            config_name = "testing_thermal_A100.yaml"
            hbm_reference = 7944.0
            hbm_size = 80
        elif system_name == "2p5D_1GPU":
            config_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
            hbm_reference = 3972.0 if hbm_stack_height == 16 else 1986.0 if hbm_stack_height == 8 else 0.0
            hbm_size = 80 if hbm_stack_height == 8 else 160 if hbm_stack_height == 16 else 0
        elif system_name in {"3D_1GPU", "3D_1GPU_top"}:
            config_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
            hbm_reference = 7944.0 if hbm_stack_height == 8 else 15888.0 if hbm_stack_height == 16 else 0.0
            hbm_size = 80 if hbm_stack_height == 8 else 160 if hbm_stack_height == 16 else 0
        else:
            raise ValueError(f"Unsupported system_name: {system_name}")

        if self._backend_kind == "legacy":
            config_path = self._legacy_hardware_config_dir / config_name
        else:
            config_path = self._rapid_hardware_template_path
        if not config_path.exists():
            raise FileNotFoundError(config_path)

        profile_id = f"{self._backend_kind}:{system_name}_stack{hbm_stack_height}"
        return SystemProfile(
            profile_id=profile_id,
            hardware_config_path=config_path,
            hardware_hash=_file_sha256(config_path),
            hbm_bandwidth_reference=hbm_reference,
            hbm_size_gb=hbm_size,
            hbm_stack_height=hbm_stack_height,
        )

    def _build_cache_signature(self) -> str:
        if self._backend_kind == "rapid":
            inference_idle_policy = "rapid_backend_reported_thermal_idle"
        else:
            inference_idle_policy = (
                "legacy_inference_raw"
                if self._model_run_type == "inference"
                else "training_layer_scale_only"
            )
        components = [
                f"{self._backend_kind}-backend-state-space-v6",
                _git_head(self._repo_root),
                _file_sha256(self._model_config_path),
                _file_sha256(self._run_perf_path),
                f"num_layers:{self._num_layers}",
                f"run_type:{self._model_run_type}",
                f"idle_scale:{self._idle_scale}",
                f"inference_idle_policy:{inference_idle_policy}",
            ]
        if self._backend_kind == "rapid":
            rapid_root = self._repo_root / "dedeepyo_integration" / "Rapid-LLM"
            components.extend(
                [
                    _file_sha256(self._rapid_hardware_template_path),
                    _file_sha256(rapid_root / "base_timing.py"),
                    _file_sha256(rapid_root / "train_timing.py"),
                    _file_sha256(rapid_root / "inference_timing.py"),
                    _file_sha256(rapid_root / "simulate_inference_graph.py"),
                    self._rapid_python_bin,
                ]
            )
        else:
            components.extend(
                [
                    _file_sha256(self._legacy_model_config_path),
                    _file_sha256(self._legacy_run_perf_path),
                ]
            )
        payload = "|".join(components).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()

    @staticmethod
    def _read_model_num_layers(model_config_path: Path) -> int:
        with open(model_config_path, "r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if not isinstance(loaded, dict):
            return ThrottleModel.DEFAULT_NUM_LAYERS
        model_param = loaded.get("model_param")
        if not isinstance(model_param, dict):
            return ThrottleModel.DEFAULT_NUM_LAYERS
        raw = model_param.get("num_layers", ThrottleModel.DEFAULT_NUM_LAYERS)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return ThrottleModel.DEFAULT_NUM_LAYERS
        return max(1, value)

    @staticmethod
    def _read_model_run_type(model_config_path: Path) -> str:
        with open(model_config_path, "r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if not isinstance(loaded, dict):
            return "training"
        model_param = loaded.get("model_param")
        if not isinstance(model_param, dict):
            return "training"
        raw = model_param.get("run_type", "training")
        return str(raw).strip().lower() or "training"


_DEFAULT_ENGINE: Optional[ThermalAnalysisGeorge] = None
_DEFAULT_ENGINE_LOCK = threading.Lock()


def get_default_engine() -> ThermalAnalysisGeorge:
    global _DEFAULT_ENGINE
    with _DEFAULT_ENGINE_LOCK:
        if _DEFAULT_ENGINE is None:
            _DEFAULT_ENGINE = ThermalAnalysisGeorge()
        return _DEFAULT_ENGINE


def iterations(
    system_name: str,
    HTC: float,
    TIM_cond: float,
    infill_cond: float,
    underfill_cond: float,
    HBM_stack_height: int,
    dummy_Si: bool,
    no_throttle: bool = False,
) -> Tuple[float, float, float, float, float, float]:
    """Legacy-compatible wrapper for drop-in replacement."""
    return get_default_engine().iterations(
        system_name=system_name,
        HTC=HTC,
        TIM_cond=TIM_cond,
        infill_cond=infill_cond,
        underfill_cond=underfill_cond,
        HBM_stack_height=HBM_stack_height,
        dummy_Si=dummy_Si,
        no_throttle=no_throttle,
    )


def _parse_list(raw: str, cast) -> List:
    values = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(cast(token))
    return values


def _bool_from_token(token: str) -> bool:
    lowered = token.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Invalid bool token: {token}")


def _build_workloads_from_args(args: argparse.Namespace) -> List[WorkloadConfig]:
    system_names = _parse_list(args.system_name, str)
    htc_values = _parse_list(args.htc, float)
    tim_values = _parse_list(args.tim_cond, float)
    infill_values = _parse_list(args.infill_cond, float)
    underfill_values = _parse_list(args.underfill_cond, float)
    stack_values = _parse_list(args.hbm_stack_height, int)
    dummy_values = _parse_list(args.dummy_si, _bool_from_token)

    workloads = []
    for values in itertools.product(
        system_names,
        htc_values,
        tim_values,
        infill_values,
        underfill_values,
        stack_values,
        dummy_values,
    ):
        workloads.append(
            WorkloadConfig(
                system_name=values[0],
                htc=values[1],
                tim_cond=values[2],
                infill_cond=values[3],
                underfill_cond=values[4],
                hbm_stack_height=values[5],
                dummy_si=values[6],
            )
        )
    return workloads


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="State-space thermal analysis (legacy or Rapid backend).")
    parser.add_argument("--system-name", default="2p5D_1GPU")
    parser.add_argument("--htc", default="7")
    parser.add_argument("--tim-cond", default="10")
    parser.add_argument("--infill-cond", default="19")
    parser.add_argument("--underfill-cond", default="19")
    parser.add_argument("--hbm-stack-height", default="8")
    parser.add_argument("--dummy-si", default="false")
    parser.add_argument("--backend-workers", type=int, default=1)
    parser.add_argument("--speculative-misses", type=int, default=0)
    parser.add_argument("--backend-kind", choices=["legacy", "rapid"], default="legacy")
    parser.add_argument(
        "--legacy-model-config",
        default="DeepFlow_llm_dev/configs/model-config/LLM_thermal.yaml",
    )
    parser.add_argument(
        "--rapid-python-bin",
        default=_DEFAULT_RAPID_PYTHON,
    )
    parser.add_argument(
        "--rapid-model-config",
        default="dedeepyo_integration/Rapid-LLM/configs/model-config/Llama2-7B_train_2048_thermal.yaml",
    )
    parser.add_argument(
        "--rapid-hardware-config",
        default="dedeepyo_integration/Rapid-LLM/configs/hardware-config/a100_80GB_legacy_thermal_port.yaml",
    )
    parser.add_argument("--persistent-cache", default="dedeepyo_integration/state_cache.sqlite")
    return parser


def _main() -> int:
    args = _build_cli_parser().parse_args()
    workloads = _build_workloads_from_args(args)
    if not workloads:
        print("No workloads requested.")
        return 0

    with ThermalAnalysisGeorge(
        backend_workers=args.backend_workers,
        speculative_misses=args.speculative_misses,
        persistent_cache_path=args.persistent_cache,
        backend_kind=args.backend_kind,
        rapid_python_bin=args.rapid_python_bin,
        rapid_hardware_config_path=args.rapid_hardware_config,
        legacy_model_config_path=args.legacy_model_config,
        rapid_model_config_path=args.rapid_model_config,
    ) as engine:
        results = engine.run_parallel(workloads)
        for workload, result in zip(workloads, results):
            print(
                f"{workload.system_name},HTC={workload.htc},TIM={workload.tim_cond},"
                f"infill={workload.infill_cond},underfill={workload.underfill_cond},"
                f"stack={workload.hbm_stack_height},dummy={workload.dummy_si} -> {result}"
            )
        print(f"transition_map_entries={engine.get_transition_map_size()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "WorkloadConfig",
    "IterationResult",
    "ThermalAnalysisGeorge",
    "iterations",
    "get_default_engine",
]
