import contextlib
import subprocess
import os
import re
import threading
import time
from datetime import datetime
import sys
import traceback
import csv
from pathlib import Path
from typing import Dict, Tuple, Optional
from functools import lru_cache
try:
    from DeepFlow_llm_dev.run_perf import run_LLM
except ImportError:
    run_LLM = None  # type: ignore[misc, assignment]
    print("Warning: DeepFlow_llm_dev.run_perf not found (legacy GUI path disabled).")

CURRENT_DEEPFLOW_CONFIG_PATH = None
_REPO_ROOT = Path(__file__).resolve().parent
DEEPFLOW_MODEL_CONFIG_DIR = str(_REPO_ROOT / "DeepFlow_llm_dev" / "configs" / "model-config")
DEEPFLOW_MODEL_CONFIG_TARGET = "LLM_thermal.yaml"


@lru_cache(maxsize=None)
def cached_llm_runtime(operating_frequency, hbm_latency, hbm_bandwidth, l2_bandwidth, l1_bandwidth, register_bandwidth):
    """Return runtime and idle fraction for DeepFlow runs keyed by critical bandwidth parameters."""
    cache_key = (
        round(operating_frequency,2),
        int(hbm_latency),
        int(hbm_bandwidth),
        int(l2_bandwidth),
        int(l1_bandwidth),
        int(register_bandwidth),
    )
    return _cached_llm_runtime_core(cache_key)


def _cached_llm_runtime_core(cache_key):
    if run_LLM is None:
        raise RuntimeError(
            "cached_llm_runtime requires DeepFlow_llm_dev (legacy); this minimal repo uses Rapid backend only."
        )
    if CURRENT_DEEPFLOW_CONFIG_PATH is None:
        raise RuntimeError("DeepFlow config path not set before invoking cached_llm_runtime.")

    model_config_path = os.path.join(DEEPFLOW_MODEL_CONFIG_DIR, DEEPFLOW_MODEL_CONFIG_TARGET)

    with contextlib.redirect_stdout(None):
        runtime, GPU_time_frac_idle = run_LLM(
            mode="LLM",
            exp_hw_config_path=CURRENT_DEEPFLOW_CONFIG_PATH,
            exp_model_config_path=model_config_path,
            exp_dir="./output",
        )

    return float(runtime), float(GPU_time_frac_idle)

# dedeepyo : 3-Jul-25 : Implementing calibration-informed iterations
from ast import Not
import math

class CalibrationData:
    """
    Internal representation of calibration data.
    Stores calibration data keyed by the first 8 columns (system configuration).
    """
    
    def __init__(self):
        self.data: Dict[Tuple, Dict[str, float]] = {}
        self.file_path: Optional[Path] = None
    
    def load_from_csv(self, csv_file_path: str = "calibration_data.csv"):
        """
        Load calibration data from CSV file.
        
        Args:
            csv_file_path: Path to the CSV file
        """
        self.file_path = Path(csv_file_path)
        
        if not self.file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file_path}")
        
        with open(self.file_path, 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # Verify header
            expected_headers = [
                "system_name",
                "HBM_power(W)",
                "HTC(kW/(m2K))",
                "TIM_conductivity(W/(mK))",
                "infill_conductivity(W/(mK))",
                "underfill_conductivity(W/(mK))",
                "HBM_stack_height",
                "dummy_Si",
                "calibrate_GPU_slope",
                "calibrate_GPU_intercept",
                "calibrate_HBM_slope",
                "calibrate_HBM_intercept"
            ]
            
            if list[str](reader.fieldnames) != expected_headers:
                raise ValueError(f"CSV header mismatch. Expected: {expected_headers}")
            
            # Read all rows
            for row in reader:
                # Create key from first 8 columns
                key = (
                    row["system_name"],
                    float(row["HBM_power(W)"]),
                    float(row["HTC(kW/(m2K))"]),
                    float(row["TIM_conductivity(W/(mK))"]),
                    float(row["infill_conductivity(W/(mK))"]),
                    float(row["underfill_conductivity(W/(mK))"]),
                    int(row["HBM_stack_height"]),
                    row["dummy_Si"].lower() == "true"
                )
                
                # Store calibration values
                calibration_values = {
                    "calibrate_GPU_slope": float(row["calibrate_GPU_slope"]),
                    "calibrate_GPU_intercept": float(row["calibrate_GPU_intercept"]),
                    "calibrate_HBM_slope": float(row["calibrate_HBM_slope"]),
                    "calibrate_HBM_intercept": float(row["calibrate_HBM_intercept"])
                }
                
                # print("{} in load_from_csv".format(key))
                self.data[key] = calibration_values
                # print(f"Loaded calibration for key: {key} -> {calibration_values}")
    
    def get_calibration(
        self,
        system_name: str,
        HBM_power: float,
        HTC: float,
        TIM_cond: float,
        infill_cond: float,
        underfill_cond: float,
        HBM_stack_height: int,
        dummy_Si: bool
    ) -> Optional[Dict[str, float]]:
        """
        Get calibration values for a specific system configuration.
        
        Args:
            system_name: Name of the system
            HBM_power: HBM power in Watts
            HTC: Heat Transfer Coefficient
            TIM_cond: TIM conductivity
            infill_cond: Infill conductivity
            underfill_cond: Underfill conductivity
            HBM_stack_height: HBM stack height
            dummy_Si: Whether dummy Si is present
            
        Returns:
            Dictionary with calibration values, or None if not found
        """
        key = (
            system_name,
            float(HBM_power),
            float(HTC),
            float(TIM_cond),
            float(infill_cond),
            float(underfill_cond),
            int(HBM_stack_height),
            bool(dummy_Si)
        )
        
        # print(dummy_Si)
        # print(key)
        # print(self.data.get(key))
        return self.data.get(key)
    
    def has_configuration(
        self,
        system_name: str,
        HBM_power: float,
        HTC: float,
        TIM_cond: float,
        infill_cond: float,
        underfill_cond: float,
        HBM_stack_height: int,
        dummy_Si: bool
    ) -> bool:
        """
        Check if a configuration exists in the loaded data.
        
        Args:
            Same as get_calibration
            
        Returns:
            True if configuration exists, False otherwise
        """
        key = (
            system_name,
            float(HBM_power),
            float(HTC),
            float(TIM_cond),
            float(infill_cond),
            float(underfill_cond),
            int(HBM_stack_height),
            bool(dummy_Si)
        )
        
        return key in self.data
    
    def get_all_keys(self):
        """
        Get all configuration keys in the loaded data.
        
        Returns:
            List of tuples representing all keys
        """
        return list(self.data.keys())
    
    def get_all_configurations(self):
        """
        Get all configurations with their calibration values.
        
        Returns:
            Dictionary mapping configuration keys to calibration values
        """
        return self.data.copy()
    
    def __len__(self):
        """Return the number of configurations loaded."""
        return len(self.data)
    
    def __repr__(self):
        return f"CalibrationData(file_path={self.file_path}, num_configurations={len(self.data)})"

# core:
    # nominal_frequency: 2.82e9
# SRAM-R:
#     bandwidth: 244 TB # Line 79, element 78.
# SRAM-L1:
#     bandwidth: 36 TB # Line 66, element 65.
# SRAM-L2:
#     bandwidth: 14100 GB # source: GTC 2021 # Line 53, element 52.

# Only for 3D wafer-scale
# Assume linear frequency voltage scaling. Assume safe temperature is 80C for the GPU. That is 220 W for the GPU. Peak FLOPs of 312 at 270 W. So 312 * 220 / 270 = 254.22 FLOPs. This corresponds to nominal_flop_rate_per_mcu of 417. Replace in line 20 / index 19 of config yaml.
# With HTC of 20 kW / (m^2 * K), safe temperature of 95 C is attained at 650 W, which is 750 TFLOPs, not considered here. Our peak is 624 TFLOPs.
def GPU_FLOPs_throttled(GPU_peak_temperature, GPU_safe_temperature, GPU_peak_power = 540.0, GPU_average_power = 540.0): # W
    nominal_frequency = 1.41e9 # 1.41e9 # Hz
    GPU_FLOPs_power = 370.0
    register_bandwidth = 122 * 1024 # GB/s # 122 TB
    l1_bandwidth = 18 * 1024 # GB/s # 18 TB
    l2_bandwidth = 7050 # GB/s # 7050 GB
    step_size = 5.0 # W # 5.0, 30.0, 20.0

    if(GPU_peak_temperature > GPU_safe_temperature):
        # Reduce GPU_peak_power by 20W per iteration.
        # Assume linear frequency scaling.
        # Assume quadratic frequency power scaling.
        nominal_frequency *= math.sqrt((GPU_peak_power - step_size) / GPU_FLOPs_power)
        GPU_FLOPs_power = GPU_peak_power - step_size
        # nominal_frequency = 1.67e9 # 1.15e9 # Hz
        # GPU_FLOPs_power = 320.0
    # elif(GPU_peak_power == GPU_average_power):
    #     nominal_frequency = 2.82e9 # 1.41e9 # Hz
    #     GPU_FLOPs_power = 540.0
    else:
        nominal_frequency *= math.sqrt(GPU_peak_power / GPU_FLOPs_power)
        GPU_FLOPs_power = GPU_peak_power
    
    register_bandwidth *= nominal_frequency / 1.41e9
    l1_bandwidth *= nominal_frequency / 1.41e9
    l2_bandwidth *= nominal_frequency / 1.41e9

    return nominal_frequency, GPU_FLOPs_power, register_bandwidth, l1_bandwidth, l2_bandwidth

# def calibrate_GPU(system_name = "2p5D_1GPU", HBM_power = 5.0, HTC = 10, TIM_cond = 1, infill_cond = 237, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False): # W # TIM_thickness = 10, 
#     # Load calibration data from JSON file
#     import json
#     try:
#         with open('dray_calibration.json', 'r') as f:
#             calibration_data = json.load(f)
#     except FileNotFoundError:
#         print("Warning: dray_calibration.json not found, using default calibration values")
#         calibration_data = {}
    
#     # Create the lookup key based on the current conditions
#     conditions_key = f"{system_name}_{TIM_cond}_{infill_cond}_{underfill_cond}_{HTC}_{HBM_stack_height}_{dummy_Si}"
    
#     # Try to get calibration values from JSON data first
#     if system_name in calibration_data and conditions_key in calibration_data[system_name]:
#         power_map = calibration_data[system_name][conditions_key]["HBM_power_map"]
#         if str(HBM_power) in power_map:
#             return (power_map[str(HBM_power)]["slope"], power_map[str(HBM_power)]["intercept"])

# def calibrate_HBM(system_name = "2p5D_1GPU", HBM_power = 5.0, HTC = 10, TIM_cond = 1, infill_cond = 237, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False): # W
#     # Load calibration data from JSON file
#     import json
#     try:
#         with open('dray_calibration.json', 'r') as f:
#             calibration_data = json.load(f)
#     except FileNotFoundError:
#         print("Warning: dray_calibration.json not found, using default calibration values")
#         calibration_data = {}
    
#     # Create the lookup key based on the current conditions
#     conditions_key = f"{system_name}_{TIM_cond}_{infill_cond}_{underfill_cond}_{HTC}_{HBM_stack_height}_{dummy_Si}"
    
#     # Try to get calibration values from JSON data first
#     if system_name in calibration_data and conditions_key in calibration_data[system_name]:
#         power_map = calibration_data[system_name][conditions_key]["HBM_power_map"]
#         if str(HBM_power) in power_map:
#             return (power_map[str(HBM_power)]["slope"], power_map[str(HBM_power)]["intercept"])

# def predict_temperature(system_name = "2p5D_1GPU", GPU_power = 540.0, HBM_power = 5.0):
#     if(system_name == "3D_waferscale"):
#         a = 0.065
#         b = 0.813
#         c = 45.0
#         d = 0.064
#         e = 0.822
#         f = 45.0
#         return a * GPU_power + b * HBM_power + c, d * GPU_power + e * HBM_power + f
#     else:
#         raise NotImplementedError(f"System {system_name} is not defined for temperature prediction.")

# def step(calibration_data, system_name = "2p5D_1GPU", GPU_power = 270.0, HBM_power = 5.0, HTC = 10, TIM_cond = 1, infill_cond = 237, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False):
def step(calibration_data, system_name, GPU_power, HBM_power, HTC, TIM_cond, infill_cond, underfill_cond, HBM_stack_height, dummy_Si):
    # print("dummy_Si: {}".format(dummy_Si))  
    returned_values = calibration_data.get_calibration(system_name = system_name, HBM_power = HBM_power, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)
    GPU_slope = returned_values["calibrate_GPU_slope"]
    GPU_intercept = returned_values["calibrate_GPU_intercept"]
    HBM_slope = returned_values["calibrate_HBM_slope"]
    HBM_intercept = returned_values["calibrate_HBM_intercept"]
    # slope, intercept = calibrate_HBM(system_name = system_name, HBM_power = HBM_power, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)
    # print("".format())
    HBM_peak_temperature = float(HBM_slope) * GPU_power + float(HBM_intercept)
    # slope, intercept = calibrate_GPU(system_name = system_name, HBM_power = HBM_power, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)
    GPU_peak_temperature = float(GPU_slope) * GPU_power + float(GPU_intercept)
    # GPU_peak_temperature, HBM_peak_temperature = predict_temperature(system_name = system_name, GPU_power = GPU_power, HBM_power = HBM_power) #TODO: Only used for 20 kW / (m^2 * K). Comment for 10 kW / (m^2 * K) cooling.
    return GPU_peak_temperature, HBM_peak_temperature

# def iterations(system_name = "2p5D_1GPU", HTC = 10, TIM_cond = 1, infill_cond = 237, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False):
def iterations(system_name, HTC, TIM_cond, infill_cond, underfill_cond, HBM_stack_height, dummy_Si):
    HBM_bandwidth_reference = 7944 # 1986 # GB/s # 1986 for 2.5D, 7944 for 3D
    GPU_safe_temperature = 95 # dedeepyo : 29-Jul-25
    HBM_size = 80 # GB

    # if system_name == "2p5D_1GPU" or system_name == "2p5D_waferscale":
    #     HBM_bandwidth_reference = 1986
    #     file_name = "testing_thermal_A100_2p5D.yaml" # testing_thermal_A100_2p5D.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name.
        # file_name = "testing_thermal_A100_1GPU.yaml"
    if system_name == "3D_waferscale":
        HBM_bandwidth_reference = 7944
        file_name = "testing_thermal_A100.yaml" # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. # testing_thermal_A100_1GPU.yaml for 1 GPU.
        # file_name = "testing_thermal_A100_1GPU.yaml"

    if(system_name == "2p5D_1GPU"):
        HBM_bandwidth_reference = 3972 if HBM_stack_height == 16 else 1986 if HBM_stack_height == 8 else 0 # 1986, 3972
        HBM_size = 80 if HBM_stack_height == 8 else 160 if HBM_stack_height == 16 else 0 # 80, 160 GB
        file_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"

    if(system_name == "3D_1GPU" or system_name == "3D_1GPU_top"):
        HBM_bandwidth_reference = 7944 if HBM_stack_height == 8 else 15888 if HBM_stack_height == 16 else 0 # 15888, 7944 #TODO: Update for 8-high vs 16-high.
        HBM_size = 80 if HBM_stack_height == 8 else 160 if HBM_stack_height == 16 else 0 # 80, 160 GB
        file_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
        # HBM_bandwidth_reference = 11916 # 2 cases, BW 7944 or 11916. #TODO: Only if 12-high HBM.
        # file_name = "testing_thermal_A100_3D_1GPU_ECTC_12stack.yaml" #TODO: Only if 12-high HBM.

    GPU_power = 370.0 # 270.0 # W # GPU_power is actually GPU_averaged_power, not peak power.
    HBM_power = 5.0 if HBM_stack_height == 8 else 9.0 if HBM_stack_height == 16 else 0.0 # W # For 12-high HBM stack, the thermal simulation is fed the correct power but it is marked as 5, 5.6, 6.8024 here for ease.
    # print(f"Initial HBM power is {HBM_power} W")
    GPU_FLOPs_power = GPU_power

    GPU_power_list = []
    HBM_power_list = []
    GPU_power_list.append(GPU_power)
    HBM_power_list.append(HBM_power)

    calibration_data = CalibrationData()
    calibration_data.load_from_csv("calibration_data.csv") #TODO: Uncomment in general.
    # calibration_data.load_from_csv("calibration_data_largerHeatSpreader.csv") #TODO: Comment in general.
    # calibration_data.load_from_csv("calibration_data_2xHeatSpreader.csv") #TODO: Comment in general.

     # 237 is the default value for infill_cond.
    # print("dummy_Si: {}".format(dummy_Si))
    results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si, calibration_data = calibration_data)
    # results = 0, 0
    GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
    
    GPU_peak_temperature_list = [GPU_peak_temperature]
    HBM_peak_temperature_list = [HBM_peak_temperature]
    GPU_time_frac_idle_list = []
    
    current_GPU_peak_temperature = GPU_peak_temperature
    current_HBM_peak_temperature = HBM_peak_temperature
    
    old_GPU_peak_temperature = -10.00 # 0
    old_HBM_peak_temperature = -10.00 # 0
    old_GPU_min_peak_temperature = -10.00 # 0
    old_HBM_min_peak_temperature = -10.00 # 0

    GPU_count_sqrt = 1 # 7 #TODO: Update everytime.
    kp1 = GPU_count_sqrt
    kp2 = GPU_count_sqrt
    # run_file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/run.sh"
    # with open(run_file_path, "r") as f:
    #     content = f.read()

    # content = re.sub(r"--kp1\s+\d+", f"--kp1 {kp1}", content)
    # content = re.sub(r"--kp2\s+\d+", f"--kp2 {kp2}", content)

    # new_content = content # .replace("--kp1 7 --kp2 7 --m", f"--kp1 {kp1} --kp2 {kp2} --m")
    # with open(run_file_path, "w") as f:
    #     f.write(new_content)

    runtimes = []
    # file_path = "÷/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/configs/new-configs/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    file_path = str(_REPO_ROOT / "DeepFlow_llm_dev" / "configs" / "hardware-config" / file_name)  # testing_thermal_A100_2p5D.yaml ... 
    with open(file_path, "r") as f:
        lines = f.readlines()

    parts = lines[23].split("size:")
    lines[23] = f"{parts[0]}size: {HBM_size} GB\n" # HBM size
    # print(f"lines[92]: {lines[92].rstrip()}")

    old_old_GPU_peak_temperature = -20.00
    old_old_HBM_peak_temperature = -20.00

    nominal_frequency = 1.41e9 # 2.82e9
    GPU_FLOPs_power = GPU_power
    i = 0
    reti = (-1)
    HBM_bandwidth = HBM_bandwidth_reference
    while((abs(old_HBM_peak_temperature - current_HBM_peak_temperature) > 0.1) or (current_GPU_peak_temperature > GPU_safe_temperature)):
        nominal_frequency, GPU_FLOPs_power, register_bandwidth, l1_bandwidth, l2_bandwidth = GPU_FLOPs_throttled(GPU_peak_temperature = current_GPU_peak_temperature, GPU_safe_temperature = GPU_safe_temperature, GPU_peak_power = GPU_FLOPs_power, GPU_average_power = GPU_power) # 80C / 95C is the safe temperature for the GPU.
        HBM_bandwidth, HBM_latency, HBM_power_Watt = HBM_throttled_performance(bandwidth = HBM_bandwidth_reference, latency = 100e-9, HBM_peak_temperature = current_HBM_peak_temperature, HBM_stack_height = HBM_stack_height) # bandwidth = 7944 for 3D, 1986 for 2.5D
        
        if(i == 0):
            nominal_frequency = 1.41e9 # 2.82e9
            GPU_FLOPs_power = 370.0
            HBM_bandwidth = HBM_bandwidth_reference
            HBM_latency = 100e-9
            l2_bandwidth = 7050
            l1_bandwidth = 18 * 1024
            register_bandwidth = 122 * 1024
        
        # HBM_power_Watt = HBM_throttled_power(bandwidth_throttled = HBM_bandwidth, HBM_power = 5, bandwidth_reference = HBM_bandwidth_reference, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth_reference = 7944 for 3D, 1986 for 2.5D
        nominal_frequency /= 1e9 # Convert to GHz
        HBM_latency *= 1e9
        # # print(f"HBM latency is {HBM_latency:.1f} ns, HBM bandwidth is {HBM_bandwidth} GB/s, HBM power is {HBM_power_Watt} W")
        for idx in [9, 24, 32]:
            if "operating_frequency:" in lines[idx]:
                parts = lines[idx].split("operating_frequency:")
                lines[idx] = f"{parts[0]}operating_frequency: {nominal_frequency:.2f}e9\n"
            elif "bandwidth:" in lines[idx]:
                parts = lines[idx].split("bandwidth:")
                lines[idx] = f"{parts[0]}bandwidth: {math.ceil(HBM_bandwidth)} GB\n"
            elif "latency:" in lines[idx]:
                parts = lines[idx].split("latency:")
                lines[idx] = f"{parts[0]}latency: {HBM_latency:.1f}e-9\n"

        for idx, value in ((43, l2_bandwidth), (55, l1_bandwidth), (67, register_bandwidth)):
            if "bandwidth:" in lines[idx]:
                parts = lines[idx].split("bandwidth:")
                lines[idx] = f"{parts[0]}bandwidth: {math.ceil(value)} GB\n"

        with open(file_path, "w") as f:
            f.writelines(lines)

        global CURRENT_DEEPFLOW_CONFIG_PATH
        CURRENT_DEEPFLOW_CONFIG_PATH = file_path

        # with open(file_path, "r") as f:
        #     lines = f.readlines()
        # print(f"{lines[21].rstrip()} and {lines[33].rstrip()} and {lines[40].rstrip()}")

        #TODO: Run DeepFlow. GPU_time_frac_idle depends on DeepFlow.
        scripts_dir = str(_REPO_ROOT / "DeepFlow_llm_dev" / "DeepFlow" / "scripts")
        base_dir = str(_REPO_ROOT)
        buildRun_path = str(_REPO_ROOT / "DeepFlow_llm_dev" / "DeepFlow" / "scripts" / "buildRun.sh")

        # try:
        #     # print("Starting DeepFlow run...")
        #     deepflow_result = subprocess.run([buildRun_path], cwd = scripts_dir, capture_output = True, text = True) # , env = os.environ.copy())
        #     # print(f"DeepFlow run completed with return code {deepflow_result.returncode}")
        #     if deepflow_result.returncode == 0:
        #         a = deepflow_result.stdout.split()
        #         runtimes.append(float(a[0]))
        #         GPU_time_frac_idle = float(a[1])
        #         GPU_time_frac_idle_list.append(GPU_time_frac_idle)
        #     else:
        #         print(f"Error: Command failed with return code {deepflow_result.returncode}")
        #         # print(deepflow_result.stderr)
        #         return None, None, None, None
        # except subprocess.TimeoutExpired:
        #     return None, None, None, None
        # except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
        #     return None, None, None, None
        # except Exception as e:
        #     # print("Error: File found and not timed out, still failed {}".format(e))
        #     return None, None, None, None
        #     # print(f"Error: Command failed with return code {deepflow_result.returncode}")
        #     # print(deepflow_result.stderr)
        # # DeepFlow ran.

        # print("Starting DeepFlow run...")
        # suppress prints for the next line          
        target = "LLM_thermal.yaml"
        # target = "LLM_thermal.yaml"
        runtime, GPU_time_frac_idle = cached_llm_runtime(
            nominal_frequency,
            HBM_latency,
            HBM_bandwidth,
            l2_bandwidth,
            l1_bandwidth,
            register_bandwidth,
        )
        # print(f"DeepFlow run completed for {system_name} with {HBM_stack_height}. Runtime: {runtime:.2f} s, GPU_time_frac_idle: {GPU_time_frac_idle:.2f}")
        # return runtime, None, None, [GPU_time_frac_idle], nominal_frequency, HBM_bandwidth
        runtimes.append(float(runtime))

        num_layers = 32 #llama 2 7b
        GPU_time_frac_idle = GPU_time_frac_idle * num_layers
        GPU_time_frac_idle_list.append(GPU_time_frac_idle)

        # print(f"operating_frequency = {nominal_frequency:.2f} GHz")
        # print(f"Iteration {i}: Runtime = {runtime:.2f} s, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")

        GPU_power_throttled = GPU_throttling(GPU_power = GPU_FLOPs_power, GPU_time_frac_idle = GPU_time_frac_idle, GPU_idle_power = 42)
        GPU_power = GPU_power_throttled # power in W
        # print(f"GPU_power throttled to {GPU_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        HBM_power = HBM_power_Watt # power in W
        old_old_GPU_peak_temperature = old_GPU_peak_temperature
        old_old_HBM_peak_temperature = old_HBM_peak_temperature
        old_GPU_peak_temperature = current_GPU_peak_temperature
        old_HBM_peak_temperature = current_HBM_peak_temperature

        GPU_power_list.append(GPU_power)
        HBM_power_list.append(HBM_power)

        # print(f"GPU_power = {GPU_power}, HBM_power = {HBM_power}")
        # print("dummy_Si: {}".format(dummy_Si))  
        results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si, calibration_data = calibration_data) # 237 is the default value for infill_cond.
        GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
        
        GPU_peak_temperature_list.append(GPU_peak_temperature)
        HBM_peak_temperature_list.append(HBM_peak_temperature)
        current_GPU_peak_temperature = GPU_peak_temperature
        current_HBM_peak_temperature = HBM_peak_temperature
        
        # print(f"Iteration {i}: GPU_peak_temperature = {current_GPU_peak_temperature:.2f} C, HBM_peak_temperature = {current_HBM_peak_temperature:.2f} C, GPU_power = {GPU_power:.2f} W, HBM_power = {HBM_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        i += 1
        if i > 100: # 101 iterations
            print("Reached maximum iterations. Exiting.") # dedeepyo : 25-Jul-25
            break
        if current_GPU_peak_temperature == old_old_GPU_peak_temperature:
            print("No change in temperatures. Exiting.") # dedeepyo : 25-Jul-25
            if len(runtimes) > 1:
                if runtimes[-1] < runtimes[-2]:
                    reti = -2
            break

    # print(f"Runtimes: {runtimes}")
    # print(f"GPU_peak_temperatures: {GPU_peak_temperature_list}")
    # print(f"HBM_peak_temperatures: {HBM_peak_temperature_list}")
    # print(f"GPU_time_frac_idle_list: {GPU_time_frac_idle_list}")
    # print(f"GPU Power : {GPU_power_list}")
    # print(f"HBM Power : {HBM_power_list}")
    # print(f"GPU_power: {GPU_power} W")
    # print(runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti])
    return runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti], nominal_frequency, HBM_bandwidth

def GPU_throttling(GPU_power = 275, GPU_time_frac_idle = 0.2, GPU_idle_power = 47):
  GPU_power_throttled = GPU_power * (1 - GPU_time_frac_idle) + GPU_idle_power * GPU_time_frac_idle
  return GPU_power_throttled

def HBM_throttled_performance(bandwidth, latency, HBM_peak_temperature = 74, HBM_stack_height = 8): # Trip points 85 C and 95 C or 75 C and 85 C
    HBM_power_Watt = 5.0 # W
    trip1 = 85 # 75, 85
    trip2 = 95 # 85, 95
    if(((HBM_peak_temperature > (trip1 - 1))) and (HBM_peak_temperature < (trip2 + 1))):
        if((trip1 == 75) and (trip2 == 85)):
            bandwidth *= (2.28 - 0.018 * HBM_peak_temperature) # Linear interpolation between (75, 0.912) and (85, 0.732)
        elif((trip1 == 85) and (trip2 == 95)):
            bandwidth *= (2.442 - 0.018 * HBM_peak_temperature) # Linear interpolation between (85, 0.912) and (95, 0.732)
    elif(HBM_peak_temperature >= (trip2 + 1)):
        bandwidth *= 0.732 # At 95C and above, bandwidth is 73.2% of nominal
    if((HBM_peak_temperature > trip2)):
        # bandwidth *= 0.732
        latency *= 1.714
        HBM_power_Watt = 6.8024 # W
    elif((HBM_peak_temperature > trip1) and (HBM_peak_temperature <= trip2)):
        # bandwidth *= 0.912
        latency *= 1.238
        HBM_power_Watt = 5.6 # W

    if(HBM_stack_height == 16):
        if((HBM_peak_temperature > trip1) and (HBM_peak_temperature <= trip2)):
            HBM_power_Watt = 9.4 # W
        elif((HBM_peak_temperature > trip2)):
            HBM_power_Watt = 10.1218 # W
        else:
            HBM_power_Watt = 9.0 # W
    
    return bandwidth, latency, HBM_power_Watt

def HBM_throttled_power(bandwidth_throttled, HBM_power, bandwidth_reference = 1986, HBM_peak_temperature = 74):
    refresh_energy = 0.12 * HBM_power
    non_refresh_energy = HBM_power - refresh_energy
    if(bandwidth_throttled < bandwidth_reference):
        non_refresh_energy *= (bandwidth_throttled / bandwidth_reference)
    if(HBM_peak_temperature > 85):
        refresh_energy *= 4.004
    elif(HBM_peak_temperature > 75 and HBM_peak_temperature <= 85):
        refresh_energy *= 2.0
    return refresh_energy + non_refresh_energy

def run_thermal_performance_stco(system_name):
    # system_name = "3D_1GPU" # "2p5D_1GPU", "3D_1GPU"

    x_axis = []
    y_axis = []
    return x_axis, y_axis

    dummy_Si = False
    if(system_name == "3D_1GPU"):
        dummy_Si = True
    elif(system_name == "2p5D_1GPU"):
        dummy_Si = False
    # print(f"System name is {system_name}, dummy_Si is {dummy_Si}")

    # Delete the test_output.txt file if it exists
    if os.path.exists("test_output.txt"):
        os.remove("test_output.txt")

    x_axis = ["TIM 5 W/(m K) & epoxy infill & epoxy underfill", "TIM 5 W/(m K) & epoxy infill & AlN underfill", "TIM 5 W/(m K) & AlN infill & epoxy underfill", "TIM 5 W/(m K) & AlN infill & AlN underfill", "TIM 10 W/(m K) & epoxy infill & epoxy underfill", "TIM 10 W/(m K) & epoxy infill & AlN underfill", "TIM 10 W/(m K) & AlN infill & epoxy underfill", "TIM 10 W/(m K) & AlN infill & AlN underfill", "TIM 50 W/(m K) & epoxy infill & epoxy underfill", "TIM 50 W/(m K) & epoxy infill & AlN underfill", "TIM 50 W/(m K) & AlN infill & epoxy underfill", "TIM 50 W/(m K) & AlN infill & AlN underfill"]
    y_axis = []
    f = open("test_output.txt", "w")
    f.write(str(x_axis) + "\n")

    for HBM_stack_height in [8, 16]: # [8, 16]: # [16]: # 
        y_axis.append([])
        f.write("HBM stack height: {}\n".format(HBM_stack_height))
        for TIM_cond in [5, 10, 50]: # [5, 10]:
            for infill_cond in [1, 19]:
                for underfill_cond in [1, 19]:
                    run_iter = iterations(system_name = system_name, HTC = 7, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si) #TODO: Uncomment for 3D, comment for 2.5D.
                    # run_iter = iterations(system_name = system_name, HTC = 7, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height) #TODO: Uncomment for 2.5D, comment for 3D.
                    y_axis[-1].append(run_iter[0])
                    # HTC = 7 if TIM_thickness == 10 else 10
                    print("TIM_cond: {}, infill_cond: {}, underfill_cond: {}, Results: {}".format(TIM_cond, infill_cond, underfill_cond, run_iter))
                    f.write("TIM_cond: {}, infill_cond: {}, underfill_cond: {}, Results: {}\n".format(TIM_cond, infill_cond, underfill_cond, run_iter))
        
        f.write(str(y_axis[-1]) + "\n")
        
    f.close()

    return x_axis, y_axis[0], y_axis[1]

if __name__ == '__main__':

    # print(iterations(system_name = "2p5D_1GPU", HTC = 10, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = False)) # 4.61 s
    # print(iterations(system_name = "3D_1GPU", HTC = 10, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = True)) # 4.56
    # exit(0)

    # f = open("test_output_all_configs_dray1_largerHeatSpreader.txt", "a")
    # f = open("test_output_all_configs_dray1.txt", "a")
    f = open("test_output_all_configs_dray2.txt", "a")
    f.write("system_name,HTC(kW/(m2K)),TIM_conductivity(W/(mK)),infill_conductivity(W/(mK)),underfill_conductivity(W/(mK)),HBM_stack_height,dummy_Si")
    f.write("\n")
    for system_name in ["3D_1GPU", "3D_1GPU_top"]:
        for HTC in [10]: # [7, 10]:
            for TIM_cond in [5.0]: # [5, 10, 50, 675.0]:
                for infill_cond in [1.6]: # [1.6, 19]: # , 675.0]:
                    for underfill_cond in [1.6]: # [1.6, 19]: # , 675.0]:
                        for HBM_stack_height in [8, 16]:
                            dummy_Si = False
                            if(system_name == "3D_1GPU_top" or system_name == "3D_1GPU"):
                                dummy_Si = True
                            
                            # print(dummy_Si)
                            # print("{},{},{},{},{},{},{}".format(system_name, HTC, TIM_cond, infill_cond, underfill_cond, HBM_stack_height, dummy_Si))
                            f.write("{},{},{},{},{},{},{}".format(system_name, HTC, TIM_cond, infill_cond, underfill_cond, HBM_stack_height, dummy_Si))
                            f.write(str(iterations(system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)))
                            # print(str(iterations(system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)))
                            f.write("\n")
    f.close()
    exit(0)

    f = open("test_output_all_configs_3D_1GPU_top.txt", "w")
    f.write("system_name,HTC(kW/(m2K)),TIM_conductivity(W/(mK)),infill_conductivity(W/(mK)),underfill_conductivity(W/(mK)),HBM_stack_height,dummy_Si")
    f.write("\n")
    for system_name in ["3D_1GPU_top"]:
        for HTC in [7.0]: # [7, 10]:
            for TIM_cond in [5, 10, 50]:
                for infill_cond in [1.6, 19]:
                    for underfill_cond in [1.6, 19]:
                        for HBM_stack_height in [8, 16]:
                            dummy_Si = False
                            if(system_name == "3D_1GPU_top"):
                                dummy_Si = True
                            
                            # print(dummy_Si)
                            f.write("{},{},{},{},{},{},{}".format(system_name, HTC, TIM_cond, infill_cond, underfill_cond, HBM_stack_height, dummy_Si))
                            f.write(str(iterations(system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)))
                            f.write("\n")
    f.close()
    exit(0)

    # dedeepyo : 03-Dec-2025 : Should be run.
    # f = open("test_output_all_configs.txt", "w")
    # f.write("system_name,HTC(kW/(m2K)),TIM_conductivity(W/(mK)),infill_conductivity(W/(mK)),underfill_conductivity(W/(mK)),HBM_stack_height,dummy_Si")
    # f.write("\n")
    # for system_name in ["2p5D_1GPU", "3D_1GPU"]:
    #     for HTC in [7.0]: # [7, 10]:
    #         for TIM_cond in [5, 10, 50]:
    #             for infill_cond in [1.6, 19]:
    #                 for underfill_cond in [1.6, 19]:
    #                     for HBM_stack_height in [8, 16]:
    #                         dummy_Si = False
    #                         if(system_name == "3D_1GPU"):
    #                             dummy_Si = True
                            
    #                         # print(dummy_Si)
    #                         f.write("{},{},{},{},{},{},{}".format(system_name, HTC, TIM_cond, infill_cond, underfill_cond, HBM_stack_height, dummy_Si))
    #                         f.write(str(iterations(system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)))
    # f.close()
    # exit(0)
    # dedeepyo : 03-Dec-2025

    x_axis = ["Ideal", "Baseline", "Baseline + AlN infill", "Baseline + AlN underfill", "Baseline + Tflex SF-10 TIM", "Baseline + all", "Baseline + HTC10"]
    y_axis = []
    z_axis = ["2p5D_1GPU_8high", "2p5D_1GPU_16high", "3D_1GPU_8high", "3D_1GPU_16high"]
    z_axis = ["2p5D_1GPU_8high", "3D_1GPU_8high"]

    # file_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
    # file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/hardware-config/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    # with open(file_path, "r") as f:
    #     lines = f.readlines()

    # nominal_frequency = 1.41e9 # 2.82e9
    # HBM_bandwidth = 1986
    # HBM_latency = 100
    # l2_bandwidth = 7050
    # l1_bandwidth = 18432
    # register_bandwidth = 124928
    # for idx in [9, 24, 32]:
    #     if "operating_frequency:" in lines[idx]:
    #         parts = lines[idx].split("operating_frequency:")
    #         lines[idx] = f"{parts[0]}operating_frequency: {nominal_frequency:.2f}e9\n"
    #     elif "bandwidth:" in lines[idx]:
    #         parts = lines[idx].split("bandwidth:")
    #         lines[idx] = f"{parts[0]}bandwidth: {math.ceil(HBM_bandwidth)} GB\n"
    #     elif "latency:" in lines[idx]:
    #         parts = lines[idx].split("latency:")
    #         lines[idx] = f"{parts[0]}latency: {HBM_latency:.1f}e-9\n"

    # for idx, value in ((43, l2_bandwidth), (55, l1_bandwidth), (67, register_bandwidth)):
    #     if "bandwidth:" in lines[idx]:
    #         parts = lines[idx].split("bandwidth:")
    #         lines[idx] = f"{parts[0]}bandwidth: {math.ceil(value)} GB\n"

    # with open(file_path, "w") as f:
    #     f.writelines(lines)

    # model_config_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config/LLM_thermal.yaml"
    # ideal = run_LLM(
    #         mode="LLM",
    #         exp_hw_config_path=CURRENT_DEEPFLOW_CONFIG_PATH,
    #         exp_model_config_path=model_config_path,
    #         exp_dir="./output",
    #     )[0]
    ideal = 4.61
    baseline = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 1, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False)[0]
    baseline_AlN_infill = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 19, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False)[0]
    baseline_AlN_underfill = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 1, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = False)[0]
    baseline_Tflex_TIM = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 10, infill_cond = 1, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False)[0]
    baseline_all = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = False)[0]
    baseline_HTC10 = iterations(system_name = "2p5D_1GPU", HTC = 10, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = False)[0]
    y_axis.append([ideal, baseline, baseline_AlN_infill, baseline_AlN_underfill, baseline_Tflex_TIM, baseline_all, baseline_HTC10])

    # ideal = 
    # baseline = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 1, underfill_cond = 1, HBM_stack_height = 16, dummy_Si = False)
    # baseline_AlN_infill = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 19, underfill_cond = 1, HBM_stack_height = 16, dummy_Si = False)
    # baseline_AlN_underfill = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 1, underfill_cond = 19, HBM_stack_height = 16, dummy_Si = False)
    # baseline_Tflex_TIM = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 10, infill_cond = 1, underfill_cond = 1, HBM_stack_height = 16, dummy_Si = False)
    # baseline_all = iterations(system_name = "2p5D_1GPU", HTC = 7, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 16, dummy_Si = False)
    # baseline_HTC10 = float('inf')
    # y_axis.append([ideal, baseline, baseline_AlN_infill, baseline_AlN_underfill, baseline_Tflex_TIM, baseline_all, baseline_HTC10])

    # file_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
    # file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/hardware-config/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    # with open(file_path, "r") as f:
    #     lines = f.readlines()

    # nominal_frequency = 1.41e9 # 2.82e9
    # HBM_bandwidth = 1986
    # HBM_latency = 100
    # l2_bandwidth = 7050
    # l1_bandwidth = 18432
    # register_bandwidth = 124928
    # for idx in [9, 24, 32]:
    #     if "operating_frequency:" in lines[idx]:
    #         parts = lines[idx].split("operating_frequency:")
    #         lines[idx] = f"{parts[0]}operating_frequency: {nominal_frequency:.2f}e9\n"
    #     elif "bandwidth:" in lines[idx]:
    #         parts = lines[idx].split("bandwidth:")
    #         lines[idx] = f"{parts[0]}bandwidth: {math.ceil(HBM_bandwidth)} GB\n"
    #     elif "latency:" in lines[idx]:
    #         parts = lines[idx].split("latency:")
    #         lines[idx] = f"{parts[0]}latency: {HBM_latency:.1f}e-9\n"

    # for idx, value in ((43, l2_bandwidth), (55, l1_bandwidth), (67, register_bandwidth)):
    #     if "bandwidth:" in lines[idx]:
    #         parts = lines[idx].split("bandwidth:")
    #         lines[idx] = f"{parts[0]}bandwidth: {math.ceil(value)} GB\n"

    # with open(file_path, "w") as f:
    #     f.writelines(lines)

    # model_config_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config/LLM_thermal.yaml"
    # ideal = run_LLM(
    #         mode="LLM",
    #         exp_hw_config_path="/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/hardware-config/testing_thermal_A100_3D_1GPU_ECTC.yaml",
    #         exp_model_config_path=model_config_path,
    #         exp_dir="./output",
    #     )[0]

    ideal = 4.56
    baseline = iterations(system_name = "3D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 1, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = True)[0]
    baseline_AlN_infill = iterations(system_name = "3D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 19, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = True)[0]
    baseline_AlN_underfill = iterations(system_name = "3D_1GPU", HTC = 7, TIM_cond = 5, infill_cond = 1, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = True)[0]
    baseline_Tflex_TIM = iterations(system_name = "3D_1GPU", HTC = 7, TIM_cond = 10, infill_cond = 1, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = True)[0]
    baseline_all = iterations(system_name = "3D_1GPU", HTC = 7, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = True)[0]
    baseline_HTC10 = iterations(system_name = "3D_1GPU", HTC = 10, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = True)[0]
    y_axis.append([ideal, baseline, baseline_AlN_infill, baseline_AlN_underfill, baseline_Tflex_TIM, baseline_all, baseline_HTC10])

    # xs

    print(x_axis)
    print(y_axis[0])
    print(y_axis[1])
    # print(y_axis[2])
    # print(y_axis[3])
    print(z_axis)
    exit(0)

    iter_2p5D_HTC10 = iterations(system_name = "2p5D_1GPU", HTC = 10, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = False)
    iter_3D_HTC10 = iterations(system_name = "3D_1GPU", HTC = 10, TIM_cond = 10, infill_cond = 19, underfill_cond = 19, HBM_stack_height = 8, dummy_Si = True)
    print(f"2.5D Iteration results: {iter_2p5D_HTC10}")
    print(f"3D Iteration results: {iter_3D_HTC10}")
    exit(0)

    system_name = "3D_1GPU" # "2p5D_1GPU", "3D_1GPU"

    # Delete the test_output.txt file if it exists
    if os.path.exists("test_output.txt"):
        os.remove("test_output.txt")

    x_axis = ["TIM 5 W/(m K) & epoxy infill & epoxy underfill", "TIM 5 W/(m K) & epoxy infill & AlN underfill", "TIM 5 W/(m K) & AlN infill & epoxy underfill", "TIM 5 W/(m K) & AlN infill & AlN underfill", "TIM 10 W/(m K) & epoxy infill & epoxy underfill", "TIM 10 W/(m K) & epoxy infill & AlN underfill", "TIM 10 W/(m K) & AlN infill & epoxy underfill", "TIM 10 W/(m K) & AlN infill & AlN underfill"]
    y_axis = []
    f = open("test_output.txt", "w")
    f.write(str(x_axis) + "\n")

    for HBM_stack_height in [8, 16]: # [8, 16]:
        y_axis = []
        f.write("HBM stack height: {}\n".format(HBM_stack_height))
        for TIM_cond in [5, 10, 50]: # [5, 10]:
            for infill_cond in [1, 19]:
                for underfill_cond in [1, 19]:
                    run_iter = iterations(system_name = system_name, HTC = 7, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = True)
                    y_axis.append(run_iter[0])
                    # HTC = 7 if TIM_thickness == 10 else 10
                    print("TIM_cond: {}, infill_cond: {}, underfill_cond: {}, Results: {}".format(TIM_cond, infill_cond, underfill_cond, run_iter))
                    f.write("TIM_cond: {}, infill_cond: {}, underfill_cond: {}, Results: {}".format(TIM_cond, infill_cond, underfill_cond, run_iter))
        
        f.write(str(y_axis) + "\n")
        
    f.close()
