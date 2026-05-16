"""
CSV reader for calibration data.
This module provides functions to read calibration data from calibration_data.csv
and store it in an internal format for reuse.
"""

import csv
from pathlib import Path
from typing import Dict, Tuple, Optional


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
            
            if list[str](reader.fieldnames) != expected_headers:
                raise ValueError(f"CSV header mismatch. Expected: {expected_headers}")
            
            # Read all rows
            for row in reader:
                # Create key from first 8 columns
                key = (
                    row["system_name"],
                    float(row["HBM_power(W)"]),
                    float(row["HTC(W/(m2K))"]),
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
                
                self.data[key] = calibration_values
    
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


# Example usage:
if __name__ == "__main__":
    # Load calibration data once
    calibration_data = CalibrationData()
    calibration_data.load_from_csv("calibration_data.csv")
    
    print(f"Loaded {len(calibration_data)} configurations")
    
    # Example: Get calibration for a specific configuration
    config = calibration_data.get_calibration(
        system_name="2p5D_1GPU",
        HBM_power=5.0,
        HTC=7.0,
        TIM_cond=50.0,
        infill_cond=19.0,
        underfill_cond=19.0,
        HBM_stack_height=8,
        dummy_Si=False
    )
    
    if config:
        print(f"GPU slope: {config['calibrate_GPU_slope']}")
        print(f"GPU intercept: {config['calibrate_GPU_intercept']}")
        print(f"HBM slope: {config['calibrate_HBM_slope']}")
        print(f"HBM intercept: {config['calibrate_HBM_intercept']}")
    else:
        print("Configuration not found")
    
    # Example: Iterate over all configurations
    print("\nAll configurations:")
    for key, values in calibration_data.get_all_configurations().items():
        print(f"Key: {key}")
        print(f"  GPU: slope={values['calibrate_GPU_slope']}, intercept={values['calibrate_GPU_intercept']}")
        print(f"  HBM: slope={values['calibrate_HBM_slope']}, intercept={values['calibrate_HBM_intercept']}")

