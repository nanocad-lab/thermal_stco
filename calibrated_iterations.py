# dedeepyo : 3-Jul-25 : Implementing calibration-informed iterations
from ast import Not
from pathlib import Path
import re
import os
import subprocess
import math

# Assume linear frequency voltage scaling. Assume safe temperature is 80C for the GPU. That is 220 W for the GPU. Peak FLOPs of 312 at 270 W. So 312 * 220 / 270 = 254.22 FLOPs. This corresponds to nominal_flop_rate_per_mcu of 417. Replace in line 20 / index 19 of config yaml.
# With HTC of 20 kW / (m^2 * K), safe temperature of 95 C is attained at 650 W, which is 750 TFLOPs, not considered here. Our peak is 624 TFLOPs.
def GPU_FLOPs_throttled(GPU_peak_temperature, GPU_safe_temperature):
    nominal_frequency = 2.82e9 # 1.41e9 # Hz
    GPU_FLOPs_power = 540.0

    if(GPU_peak_temperature > GPU_safe_temperature):
        nominal_frequency = 1.67e9 # 1.15e9 # Hz
        GPU_FLOPs_power = 320.0
    
    return nominal_frequency, GPU_FLOPs_power

def calibrate_GPU(system_name = "2p5D_1GPU", HBM_power = 5.0): # W
    # Define slope and intercept for the calibration
    # Assuming trends are linear (they have been observed to be linear in prior experiments).
    temperature_dict = {}
    temperature_dict["2p5D_1GPU"] = {
        5.0 : (0.0719, 47.1),
        5.6 : (0.0719, 47.3),
        6.8024 : (0.0718, 47.8)
    }
    temperature_dict["2p5D_waferscale"] = {
        5.0 : (0.0722, 47.1),
        5.6 : (0.0721, 47.4),
        6.8024 : (0.0722, 47.9)
    }
    temperature_dict["3D_1GPU"] = {
        5.0 : (0.107, 48.1),
        5.6 : (0.107, 48.5),
        6.8024 : (0.107, 49.3)
    }
    temperature_dict["3D_waferscale"] = {
        5.0 : (0.139, 49.2),
        5.6 : (0.139, 49.7),
        6.8024 : (0.139, 50.7)
    } # Below is for 20 kW / (m^2 * K) cooling.
#     temperature_dict["3D_waferscale"] = {
#         5.0 : (0.073, 47.2),
#         5.6 : (0.073, 47.2),
#         6.8024 : (0.073, 47.8)
#     } # Below is for 10 kW / (m^2 * K) cooling and TIM of 10 W / (m K).
    # temperature_dict["3D_waferscale"] = {
    #     5.0 : (0.1214, 48.522),
    #     5.6 : (0.1214, 48.952),
    #     6.8024 : (0.1214, 49.812)
    # }
    return temperature_dict.get(system_name, {}).get(HBM_power, ())

def calibrate_HBM(system_name = "2p5D_1GPU", HBM_power = 5.0): # W
    # Define slope and intercept for the calibration
    # Assuming trends are linear (they have been observed to be linear in prior experiments).
    temperature_dict = {}
    temperature_dict["2p5D_1GPU"] = {
        5.0 : (0.0697, 47.4),
        5.6 : (0.0697, 47.6),
        6.8024 : (0.0696, 48.2)
    }
    temperature_dict["2p5D_waferscale"] = {
        5.0 : (0.0703, 47.2),
        5.6 : (0.0703, 47.5),
        6.8024 : (0.0702, 48)
    }
    temperature_dict["3D_1GPU"] = {
        5.0 : (0.106, 48.2),
        5.6 : (0.106, 48.6),
        6.8024 : (0.106, 49.3)
    }
    temperature_dict["3D_waferscale"] = {
        5.0 : (0.138, 49.2),
        5.6 : (0.138, 49.7),
        6.8024 : (0.138, 50.7)
    } # Below is for 20 kW / (m^2 * K) cooling.
#     temperature_dict["3D_waferscale"] = {
#         5.0 : (0.072, 47.2),
#         5.6 : (0.072, 47.4),
#         6.8024 : (0.072, 47.9)
#     } # Below is for 10 kW / (m^2 * K) cooling and TIM of 10 W / (m K).
    # temperature_dict["3D_waferscale"] = {
    #     5.0 : (0.1202, 48.596),
    #     5.6 : (0.1204, 48.972),
    #     6.8024 : (0.1202, 49.896)
    # }
    return temperature_dict.get(system_name, {}).get(HBM_power, ())

def predict_temperature(system_name = "2p5D_1GPU", GPU_power = 540.0, HBM_power = 5.0):
    if(system_name == "3D_waferscale"):
        a = 0.065
        b = 0.813
        c = 45.0
        d = 0.064
        e = 0.822
        f = 45.0
        return a * GPU_power + b * HBM_power + c, d * GPU_power + e * HBM_power + f
    else:
        raise NotImplementedError(f"System {system_name} is not defined for temperature prediction.")

def step(system_name = "2p5D_1GPU", GPU_power = 270.0, HBM_power = 5.0):
    slope, intercept = calibrate_HBM(system_name = system_name, HBM_power = HBM_power)
    HBM_peak_temperature = slope * GPU_power + intercept
    slope, intercept = calibrate_GPU(system_name = system_name, HBM_power = HBM_power)
    GPU_peak_temperature = slope * GPU_power + intercept
    # GPU_peak_temperature, HBM_peak_temperature = predict_temperature(system_name = system_name, GPU_power = GPU_power, HBM_power = HBM_power) #TODO: Only used for 20 kW / (m^2 * K). Comment for 10 kW / (m^2 * K) cooling.
    return GPU_peak_temperature, HBM_peak_temperature

def iterations(system_name = "2p5D_1GPU"):
    HBM_bandwidth_reference = 7944 # 1986 # GB/s # 1986 for 2.5D, 7944 for 3D

    if system_name == "2p5D_1GPU" or system_name == "2p5D_waferscale":
        HBM_bandwidth_reference = 1986
        file_name = "testing_thermal_A100_2p5D.yaml" # testing_thermal_A100_2p5D.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name.
        # file_name = "testing_thermal_A100_1GPU.yaml"
    elif system_name == "3D_1GPU" or system_name == "3D_waferscale":
        HBM_bandwidth_reference = 7944
        file_name = "testing_thermal_A100.yaml" # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. # testing_thermal_A100_1GPU.yaml for 1 GPU.
        # file_name = "testing_thermal_A100_1GPU.yaml"

    GPU_power = 540.0 # 270.0 # W
    HBM_power = 5.0 # W

    results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name)
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

    GPU_count_sqrt = 7 #TODO: Update everytime.
    kp1 = GPU_count_sqrt
    kp2 = GPU_count_sqrt
    # run_file_path = "DeepFlow_llm_dev/DeepFlow/scripts/run.sh"
    # with open(run_file_path, "r") as f:
    #     content = f.read()

    # content = re.sub(r"--kp1\s+\d+", f"--kp1 {kp1}", content)
    # content = re.sub(r"--kp2\s+\d+", f"--kp2 {kp2}", content)

    # new_content = content # .replace("--kp1 7 --kp2 7 --m", f"--kp1 {kp1} --kp2 {kp2} --m")
    # with open(run_file_path, "w") as f:
    #     f.write(new_content)

    runtimes = []
    file_path = "DeepFlow_llm_dev/DeepFlow/configs/new-configs/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    with open(file_path, "r") as f:
        lines = f.readlines()

    # print(f"lines[92]: {lines[92].rstrip()}")

    old_old_GPU_peak_temperature = -20.00
    old_old_HBM_peak_temperature = -20.00

    i = 0
    reti = (-1)
    while(abs(old_HBM_peak_temperature - current_HBM_peak_temperature) > 0.1):
        nominal_frequency, GPU_FLOPs_power = GPU_FLOPs_throttled(GPU_peak_temperature = current_GPU_peak_temperature, GPU_safe_temperature = 95) # 80C / 95C is the safe temperature for the GPU.
        HBM_bandwidth, HBM_latency, HBM_power_Watt = HBM_throttled_performance(bandwidth = HBM_bandwidth_reference, latency = 100e-9, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth = 7944 for 3D, 1986 for 2.5D
        # HBM_power_Watt = HBM_throttled_power(bandwidth_throttled = HBM_bandwidth, HBM_power = 5, bandwidth_reference = HBM_bandwidth_reference, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth_reference = 7944 for 3D, 1986 for 2.5D
        nominal_frequency /= 1e9 # Convert to GHz
        HBM_latency *= 1e9
        # print(f"HBM latency is {HBM_latency:.1f} ns, HBM bandwidth is {HBM_bandwidth} GB/s, HBM power is {HBM_power_Watt} W")
        for idx in [21, 33, 40]:
            if "nominal_frequency:" in lines[idx]:
                # print(lines[idx].rstrip())
                parts = lines[idx].split("nominal_frequency:")
                lines[idx] = f"{parts[0]}nominal_frequency: {nominal_frequency:.2f}e9\n"
            elif "bandwidth:" in lines[idx]:
                # print(lines[idx].rstrip())
                parts = lines[idx].split("bandwidth:")
                lines[idx] = f"{parts[0]}bandwidth: {math.ceil(HBM_bandwidth)} GB\n"
            elif "latency:" in lines[idx]:
                # print(lines[idx].rstrip())
                parts = lines[idx].split("latency:")
                lines[idx] = f"{parts[0]}latency: {HBM_latency:.1f}e-9\n"

        with open(file_path, "w") as f:
            f.writelines(lines)

        # with open(file_path, "r") as f:
        #     lines = f.readlines()
        # print(f"{lines[21].rstrip()} and {lines[33].rstrip()} and {lines[40].rstrip()}")

        #TODO: Run DeepFlow. GPU_time_frac_idle depends on DeepFlow.
        _repo_root = Path(__file__).resolve().parent
        scripts_dir = str(_repo_root / "DeepFlow_llm_dev" / "DeepFlow" / "scripts")
        base_dir = str(_repo_root)
        buildRun_path = str(_repo_root / "DeepFlow_llm_dev" / "DeepFlow" / "scripts" / "buildRun.sh")

        try:
            # print("Starting DeepFlow run...")
            deepflow_result = subprocess.run([buildRun_path], cwd = scripts_dir, capture_output = True, text = True) # , env = os.environ.copy())
            # print(f"DeepFlow run completed with return code {deepflow_result.returncode}")
            if deepflow_result.returncode == 0:
                a = deepflow_result.stdout.split()
                runtimes.append(float(a[0]))
                GPU_time_frac_idle = float(a[1])
                GPU_time_frac_idle_list.append(GPU_time_frac_idle)
            else:
                # print(f"Error: Command failed with return code {deepflow_result.returncode}")
                # print(deepflow_result.stderr)
                return None, None, None, None
        except subprocess.TimeoutExpired:
            return None, None, None, None
        except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
            return None, None, None, None
        except Exception as e:
            # print("Error: File found and not timed out, still failed {}".format(e))
            return None, None, None, None
            # print(f"Error: Command failed with return code {deepflow_result.returncode}")
            # print(deepflow_result.stderr)
        # DeepFlow ran.

        GPU_power_throttled = GPU_throttling(GPU_power = GPU_FLOPs_power, GPU_time_frac_idle = GPU_time_frac_idle, GPU_idle_power = 42)
        GPU_power = GPU_power_throttled # power in W
        # print(f"GPU_power throttled to {GPU_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        HBM_power = HBM_power_Watt # power in W
        old_old_GPU_peak_temperature = old_GPU_peak_temperature
        old_old_HBM_peak_temperature = old_HBM_peak_temperature
        old_GPU_peak_temperature = current_GPU_peak_temperature
        old_HBM_peak_temperature = current_HBM_peak_temperature

        # print(f"GPU_power = {GPU_power}, HBM_power = {HBM_power}")
        results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name)
        GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
        
        GPU_peak_temperature_list.append(GPU_peak_temperature)
        HBM_peak_temperature_list.append(HBM_peak_temperature)
        current_GPU_peak_temperature = GPU_peak_temperature
        current_HBM_peak_temperature = HBM_peak_temperature
        
        # print(f"Iteration {i}: GPU_peak_temperature = {current_GPU_peak_temperature:.2f} C, HBM_peak_temperature = {current_HBM_peak_temperature:.2f} C, GPU_power = {GPU_power:.2f} W, HBM_power = {HBM_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        i += 1
        if i > 10: # 11 iterations
            # print("Reached maximum iterations. Exiting.") # dedeepyo : 25-Jul-25
            break
        if current_GPU_peak_temperature == old_old_GPU_peak_temperature:
            # print("No change in temperatures. Exiting.") # dedeepyo : 25-Jul-25
            if len(runtimes) > 1:
                if runtimes[-1] < runtimes[-2]:
                    reti = -2
            break

    # print(f"Runtimes: {runtimes}")
    # print(f"GPU_peak_temperatures: {GPU_peak_temperature_list}")
    # print(f"HBM_peak_temperatures: {HBM_peak_temperature_list}")
    # print(f"GPU_time_frac_idle_list: {GPU_time_frac_idle_list}")
    # print(f"GPU_power: {GPU_power} W")
    # print(runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti])
    return runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti]

def GPU_throttling(GPU_power = 275, GPU_time_frac_idle = 0.2, GPU_idle_power = 47):
  GPU_power_throttled = GPU_power * (1 - GPU_time_frac_idle) + GPU_idle_power * GPU_time_frac_idle
  return GPU_power_throttled

def HBM_throttled_performance(bandwidth, latency, HBM_peak_temperature = 74):
    HBM_power_Watt = 5.0 # W
    if((HBM_peak_temperature > 85)):
        bandwidth *= 0.732
        latency *= 1.714
        HBM_power_Watt = 6.8024 # W
    elif((HBM_peak_temperature > 75) and (HBM_peak_temperature <= 85)):
        bandwidth *= 0.912
        latency *= 1.238
        HBM_power_Watt = 5.6 # W

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

def main():
    # run_iter = iterations(system_name = "3D_waferscale") # 3D_1GPU, 3D_waferscale, 2p5D_waferscale, 2p5D_1GPU  # Change system_name as needed
    # print(run_iter)
    run_safe_iter = iterations_gui_safe(system_name = "3D_waferscale")
    print(run_safe_iter)

def iterations_gui_safe(system_name = "3D_waferscale"):
    """
    GUI-safe wrapper for iterations() function that handles all possible errors
    and provides sensible fallback values for the thermal analysis GUI.
    """
    try:
        # Call the main iterations function
        result = iterations(system_name = system_name)
        # print(f"Result from iterations: {result}")
        
        # Check if result is None (subprocess failed) or invalid
        # if result is None or (isinstance(result, tuple) and any(x is None for x in result)):
        #     # print("iterations() returned None values, using fallbacks")
        #     result = (None, None, None, None)

        return result
    except subprocess.SubprocessError as e:
        # print(f"Subprocess error in iterations_gui_safe: {e}")
        return None, None, None, None
    except subprocess.TimeoutExpired as e:
        # print(f"Timeout error in iterations_gui_safe: {e}")
        return None, None, None, None
    except (OSError, FileNotFoundError) as e:
        # print(f"File system error in iterations_gui_safe: {e}")
        return None, None, None, None
    except Exception as e:
        # print(f"Unexpected error in iterations_gui_safe: {e}")
        return None, None, None, None

if __name__ == "__main__":
    main()

# dedeepyo : 3-Jul-25