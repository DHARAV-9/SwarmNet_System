"""
exporter.py - CSV helpers for report-ready SwarmNet metrics.

Phase 2 writes per-node metric CSV files. This module can combine those files
and filter by event type, for example gossip convergence records.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from swarmnet.core.config import METRICS_DIR

FIELDNAMES = [
    "event_type",
    "timestamp",
    "value",
    "swarm_size",
    "drone_id",
    "packet_loss",
]


def iter_metric_files(metrics_dir: str | Path) -> list[Path]:
    """Return CSV metric files in *metrics_dir*."""
    directory = Path(metrics_dir)
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.csv") if path.is_file())


def read_metric_rows(
    paths: Iterable[str | Path],
    event_type: str | None = None,
) -> list[dict[str, str]]:
    """Read metric rows from CSV files, optionally filtering by event type."""
    rows: list[dict[str, str]] = []
    for path in paths:
        with Path(path).open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                if event_type is None or row.get("event_type") == event_type:
                    rows.append({key: row.get(key, "") for key in FIELDNAMES})
    return rows


def write_metric_rows(rows: Iterable[dict[str, str]], output_path: str | Path) -> Path:
    """Write metric rows to *output_path* and return it."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})
    return target


def export_combined_metrics(
    metrics_dir: str | Path = METRICS_DIR,
    output_path: str | Path | None = None,
    event_type: str | None = "gossip",
) -> Path:
    """Combine per-node metric CSV files into one filtered CSV."""
    directory = Path(metrics_dir)
    target = (
        Path(output_path)
        if output_path is not None
        else directory / "gossip_metrics.csv"
    )
    source_files = [path for path in iter_metric_files(directory) if path != target]
    rows = read_metric_rows(source_files, event_type=event_type)
    return write_metric_rows(rows, target)


def _numeric_groups(
    rows: Iterable[dict[str, str]],
    key: str,
) -> dict[float, list[float]]:
    """Group metric values by a numeric CSV column, skipping bad rows."""
    groups: dict[float, list[float]] = defaultdict(list)
    for row in rows:
        try:
            groups[float(row[key])].append(float(row["value"]))
        except (KeyError, TypeError, ValueError):
            continue
    return dict(groups)


def generate_benchmark_plots(
    metrics_dir: str | Path = METRICS_DIR,
    benchmark: str = "all",
) -> list[Path]:
    """Generate report-ready PNG charts from exported node metric CSV files."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory = Path(metrics_dir)
    rows = read_metric_rows(iter_metric_files(directory), event_type=None)
    output: list[Path] = []

    def selected(name: str) -> bool:
        return benchmark in {"all", name}

    def save_plot(filename: str) -> Path:
        path = directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()
        output.append(path)
        return path

    election = [row for row in rows if row["event_type"] == "election"]
    if selected("election") and (groups := _numeric_groups(election, "swarm_size")):
        labels = sorted(groups)
        plt.figure(figsize=(7, 4))
        plt.boxplot([groups[label] for label in labels], tick_labels=[str(int(label)) for label in labels])
        plt.xlabel("Swarm size")
        plt.ylabel("Election time (ms)")
        plt.title("Election Time vs Swarm Size")
        save_plot("election_time_vs_swarm_size.png")

    gossip = [row for row in rows if row["event_type"] == "gossip"]
    if selected("gossip") and (groups := _numeric_groups(gossip, "swarm_size")):
        labels = sorted(groups)
        plt.figure(figsize=(7, 4))
        plt.plot(labels, [sum(groups[label]) / len(groups[label]) for label in labels], marker="o")
        plt.xlabel("Swarm size")
        plt.ylabel("Mean convergence rounds")
        plt.title("Gossip Convergence vs Swarm Size")
        save_plot("gossip_convergence_vs_swarm_size.png")

    formation = [row for row in rows if row["event_type"] == "formation"]
    if selected("formation") and (groups := _numeric_groups(formation, "packet_loss")):
        labels = sorted(groups)
        plt.figure(figsize=(7, 4))
        plt.plot([label * 100 for label in labels], [sum(groups[label]) / len(groups[label]) for label in labels], marker="o")
        plt.xlabel("Packet loss (%)")
        plt.ylabel("Mean formation error")
        plt.title("Formation Error vs Packet Loss")
        save_plot("formation_error_vs_packet_loss.png")

    throughput = [row for row in rows if row["event_type"] == "message_rate"]
    if selected("throughput") and (groups := _numeric_groups(throughput, "drone_id")):
        labels = sorted(groups)
        plt.figure(figsize=(7, 4))
        plt.bar([str(int(label)) for label in labels], [sum(groups[label]) / len(groups[label]) for label in labels])
        plt.xlabel("Drone ID")
        plt.ylabel("Messages / second")
        plt.title("Message Throughput per Node")
        save_plot("message_throughput_per_node.png")

    return output


def parse_args() -> argparse.Namespace:
    """Parse exporter CLI arguments."""
    parser = argparse.ArgumentParser(description="Export combined SwarmNet metrics")
    parser.add_argument(
        "--metrics-dir",
        default=METRICS_DIR,
        help="Metrics CSV directory",
    )
    parser.add_argument(
        "--benchmark",
        choices=["all", "election", "gossip", "formation", "throughput"],
        default=None,
        help="Generate report-ready PNG plots from collected metrics",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path (default: <metrics-dir>/gossip_metrics.csv)",
    )
    parser.add_argument(
        "--event-type",
        default="gossip",
        help="Metric event type to export (default: gossip, use all for no filter)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    event_type = None if args.event_type == "all" else args.event_type
    output = export_combined_metrics(args.metrics_dir, args.output, event_type)
    print(f"Exported metrics to {output}")
    if args.benchmark is not None:
        plots = generate_benchmark_plots(args.metrics_dir, args.benchmark)
        if plots:
            print("Generated plots:")
            for plot in plots:
                print(f"  {plot}")
        else:
            print("No matching metric records available for benchmark plots.")


if __name__ == "__main__":
    main()
