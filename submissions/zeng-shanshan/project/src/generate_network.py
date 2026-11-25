"""Generate the deterministic 8-column by 5-row demonstration road network."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path


ROWS = 5
COLS = 8
SPACING_M = 200
SEED = 20261124
SPEEDS_KMH = (20, 30, 40, 50, 60)


def node_id(row: int, col: int) -> str:
    return f"N{row * COLS + col:02d}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = output_dir / "nodes.csv"
    roads_path = output_dir / "roads.csv"

    with nodes_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("node_id", "x_m", "y_m"))
        for row in range(ROWS):
            for col in range(COLS):
                writer.writerow((node_id(row, col), col * SPACING_M, row * SPACING_M))

    rng = random.Random(SEED)
    road_number = 0
    with roads_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("road_id", "u", "v", "length_m", "speed_kmh"))
        for row in range(ROWS):
            for col in range(COLS):
                # The order is part of the data contract: right edge, then upward edge.
                neighbors = []
                if col + 1 < COLS:
                    neighbors.append((row, col + 1))
                if row + 1 < ROWS:
                    neighbors.append((row + 1, col))
                for next_row, next_col in neighbors:
                    writer.writerow(
                        (
                            f"R{road_number:03d}",
                            node_id(row, col),
                            node_id(next_row, next_col),
                            SPACING_M,
                            rng.choice(SPEEDS_KMH),
                        )
                    )
                    road_number += 1

    file_hashes = {
        "nodes.csv": sha256(nodes_path),
        "roads.csv": sha256(roads_path),
    }
    scenarios_path = output_dir / "scenarios.json"
    if scenarios_path.is_file():
        file_hashes["scenarios.json"] = sha256(scenarios_path)

    manifest = {
        "data_version": "city40-v1.0",
        "seed": SEED,
        "grid_shape": {"rows": ROWS, "cols": COLS},
        "node_count": ROWS * COLS,
        "road_count": road_number,
        "units": {"coordinates": "m", "length": "m", "speed": "km/h", "time": "s"},
        "generation": {
            "spacing_m": SPACING_M,
            "topology": "orthogonal grid; bidirectional physical roads; no diagonals",
            "road_order": "nodes sorted by ID; right neighbor before upward neighbor",
            "speed_choices_kmh": list(SPEEDS_KMH),
            "speed_sampling": "uniform with random.Random(seed)",
        },
        "sha256": file_hashes,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Generated {ROWS * COLS} nodes and {road_number} physical roads in {output_dir}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data"),
        help="output directory (default: data)",
    )
    args = parser.parse_args()
    generate(args.output_dir)


if __name__ == "__main__":
    main()
