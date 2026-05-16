# DeepFlow Thermal / STCO

This README.txt is the canonical plain-text readme (setup, calibration, Rapid thermal suite,
ECTC CSV tooling). Repo-root README.md mirrors the same content so GitHub's README tab can show it,
because GitHub only renders that homepage panel from README.md, not README.txt.

Minimal snapshot: retains `thermal_suite.py`, `therm.py`, Rapid-LLM timing, ECTC helpers. Upstream
`perf.py` / large layout search corpora were removed.

--------------------------------------------------------------------------------

## ECTC `therm.py` commands (reference log)


python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU_6HBM_3D_single_GPU_on_top.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_revised_3D_1GPU_top_8high_030826 --is_repeat False --hbm_stack_height 8 --system_type 3D_1GPU_top --dummy_si True --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU_6HBM_3D_single_GPU.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_revised_3D_1GPU_8high_030826 --is_repeat False --hbm_stack_height 8 --system_type 3D_1GPU --dummy_si True --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1gpu_6hbm_2p5D.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_revised_2p5D_1GPU_8high_030826 --is_repeat False --hbm_stack_height 8 --system_type 2p5D_1GPU --dummy_si False --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19

python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU_6HBM_3D_single_GPU_on_top.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled_higherHTC --project_name ECTC_revised_3D_1GPU_top_8high_030826_higherHTC --is_repeat False --hbm_stack_height 8 --system_type 3D_1GPU_top --dummy_si True --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU_6HBM_3D_single_GPU.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled_higherHTC --project_name ECTC_revised_3D_1GPU_8high_030826_higherHTC --is_repeat False --hbm_stack_height 8 --system_type 3D_1GPU --dummy_si True --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1gpu_6hbm_2p5D.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled_higherHTC --project_name ECTC_revised_2p5D_1GPU_8high_030826_higherHTC --is_repeat False --hbm_stack_height 8 --system_type 2p5D_1GPU --dummy_si False --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19

python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU6HBM_3D_16high_GPU_on_top.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_3D_1GPU_top_16high_030826_ECTC_revised --is_repeat False --hbm_stack_height 16 --system_type 3D_1GPU_top --dummy_si True --tim_cond_list 5 --infill_cond_list 1.6 --underfill_cond_list 1.6
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU6HBM_16high_2p5D.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_2p5D_1GPU_16high_030826_ECTC_revised --is_repeat False --hbm_stack_height 16 --system_type 2p5D_1GPU --dummy_si False --tim_cond_list 5 --infill_cond_list 1.6 --underfill_cond_list 1.6
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU6HBM_3D_16high.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_3D_1GPU_16high_030826_ECTC_revised --is_repeat False --hbm_stack_height 16 --system_type 3D_1GPU --dummy_si True --tim_cond_list 5 --infill_cond_list 1.6 --underfill_cond_list 1.6

python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU_6HBM_3D_single_GPU_on_top.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_revised_3D_1GPU_top_8high_030826 --is_repeat True --hbm_stack_height 8 --system_type 3D_1GPU_top --dummy_si True --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU_6HBM_3D_single_GPU.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_revised_3D_1GPU_8high_030826 --is_repeat True --hbm_stack_height 8 --system_type 3D_1GPU --dummy_si True --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1gpu_6hbm_2p5D.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_revised_2p5D_1GPU_8high_030826 --is_repeat True --hbm_stack_height 8 --system_type 2p5D_1GPU --dummy_si False --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19

python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU_6HBM_3D_single_GPU_on_top.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled_higherHTC --project_name ECTC_revised_3D_1GPU_top_8high_030826_higherHTC --is_repeat True --hbm_stack_height 8 --system_type 3D_1GPU_top --dummy_si True --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU_6HBM_3D_single_GPU.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled_higherHTC --project_name ECTC_revised_3D_1GPU_8high_030826_higherHTC --is_repeat True --hbm_stack_height 8 --system_type 3D_1GPU --dummy_si True --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1gpu_6hbm_2p5D.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled_higherHTC --project_name ECTC_revised_2p5D_1GPU_8high_030826_higherHTC --is_repeat True --hbm_stack_height 8 --system_type 2p5D_1GPU --dummy_si False --tim_cond_list 5 --tim_cond_list 50 --infill_cond_list 1.6 --infill_cond_list 19 --underfill_cond_list 1.6 --underfill_cond_list 19

python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU6HBM_3D_16high_GPU_on_top.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_3D_1GPU_top_16high_030826_ECTC_revised --is_repeat True --hbm_stack_height 16 --system_type 3D_1GPU_top --dummy_si True --tim_cond_list 5 --infill_cond_list 1.6 --underfill_cond_list 1.6
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU6HBM_16high_2p5D.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_2p5D_1GPU_16high_030826_ECTC_revised --is_repeat True --hbm_stack_height 16 --system_type 2p5D_1GPU --dummy_si False --tim_cond_list 5 --infill_cond_list 1.6 --underfill_cond_list 1.6
python3 therm.py --therm_conf configs/thermal-configs/sip_hbm_dray_030826_ECTC_revised_1GPU6HBM_3D_16high.xml --out_dir out_therm --heatsink_conf configs/thermal-configs/heatsink_definitions.xml --bonding_conf configs/thermal-configs/bonding_definitions.xml --heatsink heatsink_water_cooled --project_name ECTC_3D_1GPU_16high_030826_ECTC_revised --is_repeat True --hbm_stack_height 16 --system_type 3D_1GPU --dummy_si True --tim_cond_list 5 --infill_cond_list 1.6 --underfill_cond_list 1.6



## GitHub / fresh clone setup

0. Activate a Python 3 virtual environment with Scientific Python + Rapid toolchain packages (see
    `requirements.txt` and Rapid-LLM extras below).
1. Clone the repo and `cd` into its root (repository root — run `therm.py` from here).

        pip install -r requirements.txt
        pip install -r dedeepyo_integration/Rapid-LLM/requirements.txt

    Rapid optionally calls AstraSim; follow `dedeepyo_integration/Rapid-LLM/AGENTS.md` if the
    hardware config enables that backend. Chakra / protobuf versions must match that toolchain.

2. **Anemoi (`therm.py` + `AnemoiSim`)** — set a valid API token in the environment (the committed
    code does not embed secrets):

        setenv ANEMOI_API_TOKEN '<your token>'   # tcsh/csh
        # or: export ANEMOI_API_TOKEN='...'      # bash

    Install the vendor `danka_thermal_api` client as provided with your Anemoi subscription.

3. **Working directory** — `therm.py` and README command examples assume the current working directory
    is this repository root (paths like `configs/thermal-configs/...`).

4. **`calibration_data.csv`** — `therm.py` appends calibration rows when the relevant block is enabled
    in that script. Point `thermal_analysis_gui.py` / `CalibrationData()` at this file **after**
    calibration runs (`calibration_csv_reader.py` mirrors the CSV layout).

---

## Thermal + LLM runtime (`thermal_suite.py`)

Training and inference use the **same** command. Only `dedeepyo_integration/config_loader.yaml`
`model_configs` changes: comment the inference pair and uncomment the training pair (or the reverse).
See the two labeled pairs under `model_configs` in `config_loader.yaml`.

    cd dedeepyo_integration
    python3 thermal_suite.py --config config_loader.yaml

Output path is whatever you set as `results_csv` in `config_loader.yaml` (currently
`thermal_suite_results_no_throttle_2cases.csv`). The CSV has raw columns through `runtime_seconds`;
normalized columns come from `generate_ectc_revised_csvs.py` (below).

Decode/prefill axis sweeps for ECTC14-style plots still need **`run_inference_decode_prefill_sweep.py`**
because that script edits `decode_len` per sweep point; `thermal_suite.py` reads fixed decode length
from each model YAML.

---

## Regenerating `ECTC*_revised.csv` from raw CSVs

Archived copies of the paper tables live under `reference/paper_tables/`.

From a **full** `thermal_suite` CSV (including the ideal thermal rows listed in
`generate_ectc_revised_csvs.py`):

    python3 generate_ectc_revised_csvs.py --train-csv dedeepyo_integration/thermal_suite_results_no_throttle_2cases.csv

(Use whatever path matches your `results_csv` in `config_loader.yaml`.)

If you only export a **subset** (for example 16-HBM rows) but still have a fuller CSV with the ideal
cases, add:

    --ideal-anchor-csv path/to/full_thermal_suite.csv

To also rewrite `ECTC14_revised.csv` after the inference sweep:

    python3 generate_ectc_revised_csvs.py \
      --train-csv dedeepyo_integration/thermal_suite_results_no_throttle_2cases.csv \
      --infer-raw-csv dedeepyo_integration/tmp/decode_prefill_ratio_sweep_ideal_and_baselines_raw.csv \
      --ectc14

**Note.** `normalization_constant` in the archived CSVs occasionally differs by ~10^-3 seconds from the
canonical ideal YAML row rerun (solver / cache jitter). The generator uses measured
`runtime_seconds` from that ideal YAML row unless you overlay an anchor CSV with your own reference.

