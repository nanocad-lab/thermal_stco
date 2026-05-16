#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Thermal Analysis GUI..."
echo "Python: python3 ($(command -v python3))"
echo "GUI file: thermal_analysis_gui.py"
echo "Working directory: $(pwd)"
echo "=================================="

exec python3 thermal_analysis_gui.py
