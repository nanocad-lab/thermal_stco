"""
CSV writer for calibration data.
This module provides functions to write calibration data to calibration_data.csv.
"""

import csv
import os
from pathlib import Path


def write_calibration_to_csv(
    system_name,
    HBM_power,
    HTC,
    TIM_cond,
    infill_cond,
    underfill_cond,
    HBM_stack_height,
    dummy_Si,
    calibrate_GPU_slope,
    calibrate_GPU_intercept,
    calibrate_HBM_slope,
    calibrate_HBM_intercept,
    csv_file_path="calibration_data.csv"
):
    """
    Write calibration data to CSV file.
    
    Args:
        system_name: Name of the system (e.g., "2p5D_1GPU")
        HBM_power: HBM power in Watts
        HTC: Heat Transfer Coefficient in W/(m^2*K)
        TIM_cond: TIM conductivity in W/(m*K)
        infill_cond: Infill conductivity in W/(m*K)
        underfill_cond: Underfill conductivity in W/(m*K)
        HBM_stack_height: HBM stack height (number of dies)
        dummy_Si: Boolean indicating if dummy Si is present
        calibrate_GPU_slope: GPU calibration slope
        calibrate_GPU_intercept: GPU calibration intercept
        calibrate_HBM_slope: HBM calibration slope
        calibrate_HBM_intercept: HBM calibration intercept
        csv_file_path: Path to the CSV file (default: "calibration_data.csv")
    """
    # Ensure dummy_Si is a boolean and convert to string for CSV
    dummy_Si_str = str(bool(dummy_Si))
    
    # Prepare the row data
    row_data = [
        system_name,
        str(HBM_power),
        str(HTC),
        str(TIM_cond),
        str(infill_cond),
        str(underfill_cond),
        str(HBM_stack_height),
        dummy_Si_str,
        str(calibrate_GPU_slope),
        str(calibrate_GPU_intercept),
        str(calibrate_HBM_slope),
        str(calibrate_HBM_intercept)
    ]
    
    # Check if file exists to determine if we need to write header
    file_exists = os.path.exists(csv_file_path)
    
    # Open file in append mode
    with open(csv_file_path, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header if file doesn't exist
        if not file_exists:
            header = [
                "system_name",
                "HBM_power(W)",
                "HTC(W/(m2K))",
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
            writer.writerow(header)
        
        # Write the data row
        writer.writerow(row_data)


def extract_calibration_from_interpolate(data, col2_values):
    """
    Extract calibration slopes and intercepts from data.
    This is a modified version of interpolate_and_report that returns values instead of writing.
    
    Args:
        data: numpy array with columns [GPU_power, HBM_power, GPU_temp, HBM_temp]
        col2_values: List of HBM_power values to process
        
    Returns:
        dict: Dictionary with HBM_power as keys and calibration values as values
        Format: {HBM_power: {'GPU': (slope, intercept), 'HBM': (slope, intercept)}}
    """
    import numpy as np
    from sklearn.linear_model import LinearRegression
    
    slope_intercept_dict = {}
    for val in col2_values:
        slope_intercept_dict[val] = {'GPU': (0.0, 0.0), 'HBM': (0.0, 0.0)}
        mask = np.isclose(data[:, 1], val)
        subset = data[mask]
        if subset.shape[0] < 2:
            continue  # Need at least 2 points for regression
        
        x = subset[:, 0].reshape(-1, 1)
        
        # GPU calibration
        y_gpu = subset[:, 2]
        model_gpu = LinearRegression()
        model_gpu.fit(x, y_gpu)
        slope_intercept_dict[val]['GPU'] = (float(model_gpu.coef_[0]), float(model_gpu.intercept_))
        
        # HBM calibration
        y_hbm = subset[:, 3]
        model_hbm = LinearRegression()
        model_hbm.fit(x, y_hbm)
        slope_intercept_dict[val]['HBM'] = (float(model_hbm.coef_[0]), float(model_hbm.intercept_))
    
    return slope_intercept_dict


# Example usage code that would replace the file writing at line 1606 in therm.py:
"""
# At line 1606, replace the file writing code with:
from calibration_csv_writer import write_calibration_to_csv, extract_calibration_from_interpolate

# Extract calibration values instead of writing to file
calibration_dict = extract_calibration_from_interpolate(data, col2_values)

# Use the first HBM_power value's calibration (or you can choose another strategy)
# You may want to use the last value, or average across all values
first_hbm_power = col2_values[0] if col2_values else None
if first_hbm_power and first_hbm_power in calibration_dict:
    gpu_slope, gpu_intercept = calibration_dict[first_hbm_power]['GPU']
    hbm_slope, hbm_intercept = calibration_dict[first_hbm_power]['HBM']
    
    # Get HTC value (assuming it's available from heatsinks[0].get_hc() or similar)
    hc = heatsinks[0].get_hc() if heatsinks else 7.0  # Default or get from context
    HTC = hc  # Adjust conversion if needed
    
    # Get system_name (you'll need to determine this from your context)
    system_name = project_name  # or determine from config
    
    # Get dummy_Si (you'll need to determine this from your context)
    dummy_Si = False  # or determine from context
    
    # Write to CSV
    write_calibration_to_csv(
        system_name=system_name,
        HBM_power=first_hbm_power,  # or use a representative value
        HTC=HTC,
        TIM_cond=TIM_cond,
        infill_cond=infill_cond,
        underfill_cond=underfill_cond,
        HBM_stack_height=hbm_stack_height,
        dummy_Si=dummy_Si,
        calibrate_GPU_slope=gpu_slope,
        calibrate_GPU_intercept=gpu_intercept,
        calibrate_HBM_slope=hbm_slope,
        calibrate_HBM_intercept=hbm_intercept
    )
"""

