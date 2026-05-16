Canonical project documentation lives in the repo-root **[`README.txt`](../README.txt)**.

## `thermal_suite.py`

Use the interpreter from your activated environment (same as the rest of DeepFlow):

```bash
python3 thermal_suite.py --config config_loader.yaml
```

**Training vs inference:** the command is unchanged. Edit only `model_configs` in `config_loader.yaml`:
comment either the training pair or the inference pair (see the labeled `model_configs` blocks in `config_loader.yaml`).

`results_csv` in the YAML selects where outputs are written.

## Decode/prefill sweep (ECTC-style)

For plots that sweep decode length vs prefill length, run (separate from `thermal_suite.py`):

```bash
python3 run_inference_decode_prefill_sweep.py
```

Output under `dedeepyo_integration/tmp/`.
