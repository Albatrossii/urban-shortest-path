"""Generate the deterministic city40 and scale-experiment road networks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SPACING_M = 200
BASE_SEED = 20261124
SPEEDS_KMH = (20, 30, 40, 50, 60)


@dataclass(frozen=True)
class GridSpec:
    graph_id: str
    rows: int
    cols: int
    seed: int
    node_id_width: int
    road_id_width: int

    @property
    def node_count(self) -> int:
        return self.rows * self.cols

    @property
    def road_count(self) -> int:
        return self.rows * (self.cols - 1) + self.cols * (self.rows - 1)


CITY40 = GridSpec("city40", 5, 8, BASE_SEED, 2, 3)
SCALE_SPECS = {
    size * size: GridSpec(
        graph_id=f"grid{size * size}",
        rows=size,
        cols=size,
        seed=BASE_SEED + size * size,
        node_id_width=4,
        road_id_width=4,
    )
    for size in (10, 20, 30, 40)
}


def node_id(spec: GridSpec, row: int, col: int) -> str:
    return f"N{row * spec.cols + col:0{spec.node_id_width}d}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_existing_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def generate(spec: GridSpec, output_dir: Path) -> None:
    """Generate one grid without changing an existing scenario configuration."""
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = output_dir / "nodes.csv"
    roads_path = output_dir / "roads.csv"
    scenarios_path = output_dir / "scenarios.json"
    manifest_path = output_dir / "manifest.json"
    previous_manifest = _read_existing_manifest(manifest_path)

    with nodes_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("node_id", "x_m", "y_m"))
        for row in range(spec.rows):
            for col in range(spec.cols):
                writer.writerow(
                    (node_id(spec, row, col), col * SPACING_M, row * SPACING_M)
                )

    rng = random.Random(spec.seed)
    road_number = 0
    with roads_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("road_id", "u", "v", "length_m", "speed_kmh"))
        for row in range(spec.rows):
            for col in range(spec.cols):
                start = node_id(spec, row, col)
                neighbors: list[tuple[int, int]] = []
                if col + 1 < spec.cols:
                    neighbors.append((row, col + 1))
                if row + 1 < spec.rows:
                    neighbors.append((row + 1, col))
                for next_row, next_col in neighbors:
                    writer.writerow(
                        (
                            f"R{road_number:0{spec.road_id_width}d}",
                            start,
                            node_id(spec, next_row, next_col),
                            SPACING_M,
                            rng.choice(SPEEDS_KMH),
                        )
                    )
                    road_number += 1

    # city40 already has fixed scenario files; regeneration must not replace them.
    # New scale datasets use normal only, as required by Experiment B.
    if not scenarios_path.is_file():
        scenarios_path.write_text(
            json.dumps(
                {"normal": {"speed_factors": {}, "closed_roads": []}},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    file_hashes = {
        "nodes.csv": sha256(nodes_path),
        "roads.csv": sha256(roads_path),
        "scenarios.json": sha256(scenarios_path),
    }
    scenario_basis_path = output_dir / "scenario_basis.json"
    if scenario_basis_path.is_file():
        file_hashes["scenario_basis.json"] = sha256(scenario_basis_path)

    manifest: dict[str, Any] = {
        "graph_id": spec.graph_id,
        "data_version": f"{spec.graph_id}-v1.0",
        "seed": spec.seed,
        "grid_shape": {"rows": spec.rows, "cols": spec.cols},
        "node_count": spec.node_count,
        "road_count": road_number,
        "units": {
            "coordinates": "m",
            "length": "m",
            "speed": "km/h",
            "time": "s",
        },
        "generation": {
            "spacing_m": SPACING_M,
            "topology": "orthogonal grid; bidirectional physical roads; no diagonals",
            "road_order": "nodes sorted by ID; right neighbor before upward neighbor",
            "node_id_width": spec.node_id_width,
            "road_id_width": spec.road_id_width,
            "speed_choices_kmh": list(SPEEDS_KMH),
            "speed_sampling": "uniform with random.Random(seed)",
        },
        "sha256": file_hashes,
    }
    if spec.graph_id == "city40" and "scenario_generation" in previous_manifest:
        manifest["scenario_generation"] = previous_manifest["scenario_generation"]

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Generated {spec.graph_id}: {spec.node_count} nodes, "
        f"{road_number} physical roads in {output_dir}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--scale",
        type=int,
        choices=sorted(SCALE_SPECS),
        help="generate one scale-experiment graph",
    )
    group.add_argument(
        "--all-scales",
        action="store_true",
        help="generate grid100, grid400, grid900, and grid1600",
    )
    group.add_argument(
        "--city40",
        action="store_true",
        help="regenerate the 5x8 city40 graph while preserving its scenarios",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "output directory for one graph, or base directory with --all-scales; "
            "defaults to data or data/scales"
        ),
    )
    args = parser.parse_args()

    if args.all_scales:
        base = args.output_dir or Path("data/scales")
        for spec in SCALE_SPECS.values():
            generate(spec, base / spec.graph_id)
    elif args.scale is not None:
        spec = SCALE_SPECS[args.scale]
        generate(spec, args.output_dir or Path("data/scales") / spec.graph_id)
    else:
        generate(CITY40, args.output_dir or Path("data"))


if __name__ == "__main__":
    main()
