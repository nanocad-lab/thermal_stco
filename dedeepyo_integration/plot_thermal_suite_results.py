#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set()


def _model_label(path_value: object) -> str:
    raw = str(path_value)
    name = Path(raw).name
    if name.endswith(".yaml"):
        name = name[:-5]
    if name.endswith("_thermal"):
        name = name[:-8]
    return name


def _load_results(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = {
        "model_config",
        "thermal_case",
        "runtime_seconds",
        "gpu_peak_temperature_c",
        "hbm_peak_temperature_c",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing columns in {csv_path}: {', '.join(missing)}")

    df = df.copy()
    df["model_label"] = df["model_config"].map(_model_label)
    for column in ("runtime_seconds", "gpu_peak_temperature_c", "hbm_peak_temperature_c"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _plot_runtime_for_thermal(df: pd.DataFrame, thermal_case: str, title_prefix: str, output_path: Path) -> None:
    subset = df[df["thermal_case"] == thermal_case].copy()
    if subset.empty:
        raise ValueError(f"No rows found for thermal_case={thermal_case}")
    subset = subset.sort_values("model_label")

    plt.figure(figsize=(10, 5))
    sns.barplot(data=subset, x="model_label", y="runtime_seconds")
    plt.title(f"{title_prefix} | {thermal_case} Runtime")
    plt.xlabel("Model")
    plt.ylabel("Runtime (s)")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def _plot_runtime_compare(df: pd.DataFrame, title: str, output_path: Path) -> None:
    subset = df[df["thermal_case"].isin(["2.5D_baseline", "3D_baseline"])].copy()
    if subset.empty:
        raise ValueError("No baseline thermal rows found for runtime comparison.")
    subset = subset.sort_values(["model_label", "thermal_case"])

    plt.figure(figsize=(10, 5))
    sns.barplot(data=subset, x="model_label", y="runtime_seconds", hue="thermal_case")
    plt.title(title)
    plt.xlabel("Model")
    plt.ylabel("Runtime (s)")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def _plot_temperature_compare(df: pd.DataFrame, title: str, output_path: Path) -> None:
    subset = df[df["thermal_case"].isin(["2.5D_baseline", "3D_baseline"])].copy()
    if subset.empty:
        raise ValueError("No baseline thermal rows found for temperature comparison.")
    subset = subset.sort_values(["model_label", "thermal_case"])
    melted = subset.melt(
        id_vars=["model_label", "thermal_case"],
        value_vars=["gpu_peak_temperature_c", "hbm_peak_temperature_c"],
        var_name="component",
        value_name="temperature_c",
    )
    melted["component"] = melted["component"].map(
        {
            "gpu_peak_temperature_c": "GPU Peak Temp",
            "hbm_peak_temperature_c": "HBM Peak Temp",
        }
    )

    grid = sns.catplot(
        data=melted,
        x="model_label",
        y="temperature_c",
        hue="thermal_case",
        col="component",
        kind="bar",
        height=5,
        aspect=1.2,
        sharey=False,
    )
    grid.set_axis_labels("Model", "Temperature (C)")
    grid.set_titles("{col_name}")
    grid.fig.subplots_adjust(top=0.86, bottom=0.24)
    for ax in grid.axes.flat:
        ax.tick_params(axis="x", rotation=25)
    grid.fig.suptitle(title)
    grid.savefig(output_path, dpi=160)
    plt.close(grid.fig)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate thermal suite plots.")
    parser.add_argument(
        "--sweep-csv",
        default="dedeepyo_integration/thermal_suite_results_old.csv",
        help="CSV for the existing sweep (used for separate 2.5D and 3D plots).",
    )
    parser.add_argument(
        "--rerun-csv",
        default="dedeepyo_integration/thermal_suite_results.csv",
        help="CSV from baseline rerun (used for 2.5D/3D comparison plots).",
    )
    parser.add_argument(
        "--output-dir",
        default="dedeepyo_integration/plots",
        help="Directory where plot PNG files are written.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    sweep_csv = (repo_root / args.sweep_csv).resolve()
    rerun_csv = (repo_root / args.rerun_csv).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not sweep_csv.exists():
        raise FileNotFoundError(sweep_csv)
    if not rerun_csv.exists():
        raise FileNotFoundError(rerun_csv)

    sweep_df = _load_results(sweep_csv)
    rerun_df = _load_results(rerun_csv)

    output_paths = {
        "sweep_2p5d_runtime": output_dir / "sweep_2p5d_runtime.png",
        "sweep_3d_runtime": output_dir / "sweep_3d_runtime.png",
        "rerun_2p5d_3d_runtime": output_dir / "rerun_2p5d_3d_runtime.png",
        "rerun_2p5d_3d_temperature": output_dir / "rerun_2p5d_3d_temperature.png",
    }

    _plot_runtime_for_thermal(
        sweep_df,
        thermal_case="2.5D_baseline",
        title_prefix=f"Sweep ({sweep_csv.name})",
        output_path=output_paths["sweep_2p5d_runtime"],
    )
    _plot_runtime_for_thermal(
        sweep_df,
        thermal_case="3D_baseline",
        title_prefix=f"Sweep ({sweep_csv.name})",
        output_path=output_paths["sweep_3d_runtime"],
    )
    _plot_runtime_compare(
        rerun_df,
        title=f"2.5D vs 3D Runtime ({rerun_csv.name})",
        output_path=output_paths["rerun_2p5d_3d_runtime"],
    )
    _plot_temperature_compare(
        rerun_df,
        title=f"2.5D vs 3D Temperatures ({rerun_csv.name})",
        output_path=output_paths["rerun_2p5d_3d_temperature"],
    )

    print("Wrote plots:")
    for key in (
        "sweep_2p5d_runtime",
        "sweep_3d_runtime",
        "rerun_2p5d_3d_runtime",
        "rerun_2p5d_3d_temperature",
    ):
        print(output_paths[key])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
