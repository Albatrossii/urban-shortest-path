"""Validate the project's node, road, and traffic-scenario data files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any


NODE_FIELDS = ["node_id", "x_m", "y_m"]
ROAD_FIELDS = ["road_id", "u", "v", "length_m", "speed_kmh"]
SCENARIO_FIELDS = {"speed_factors", "closed_roads"}
GEOMETRY_TOLERANCE_M = 1e-9
CITY40_SPEEDS_KMH = {20, 30, 40, 50, 60}
BASE_SEED = 20261124
SCALE_SIZES = {100: 10, 400: 20, 900: 30, 1600: 40}


def read_csv(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != expected_fields:
            raise ValueError(
                f"{path}: expected header {','.join(expected_fields)}, "
                f"got {reader.fieldnames}"
            )
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: file contains a header but no data rows")
    for row_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{path}:{row_number}: row has missing or extra fields")
    return rows


def parse_finite_float(value: str, field: str, location: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{location}: {field} must be a number, got {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{location}: {field} must be finite, got {value!r}")
    return number


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_grid_manifest(
    manifest_path: Path,
    nodes_path: Path,
    roads_path: Path,
    node_rows: list[dict[str, str]],
    road_rows: list[dict[str, str]],
) -> None:
    try:
        manifest: Any = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{manifest_path}: invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"{manifest_path}: expected a JSON object")

    graph_id = manifest.get("graph_id", "city40")
    if graph_id == "city40":
        rows, cols, expected_seed = 5, 8, BASE_SEED
        node_width, road_width = 2, 3
        expected_version = "city40-v1.0"
    elif graph_id in {f"grid{count}" for count in SCALE_SIZES}:
        count = int(graph_id.removeprefix("grid"))
        size = SCALE_SIZES[count]
        rows, cols = size, size
        expected_seed = BASE_SEED + count
        node_width, road_width = 4, 4
        expected_version = f"{graph_id}-v1.0"
    else:
        raise ValueError(f"{manifest_path}: unsupported graph_id {graph_id!r}")

    expected_fields = {
        "data_version": expected_version,
        "seed": expected_seed,
        "grid_shape": {"rows": rows, "cols": cols},
        "node_count": rows * cols,
        "road_count": rows * (cols - 1) + cols * (rows - 1),
        "units": {"coordinates": "m", "length": "m", "speed": "km/h", "time": "s"},
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            raise ValueError(
                f"{manifest_path}: {field} must be {expected!r}, got {manifest.get(field)!r}"
            )

    expected_hashes = manifest.get("sha256")
    if not isinstance(expected_hashes, dict):
        raise ValueError(f"{manifest_path}: sha256 must be an object")
    for data_path in (nodes_path, roads_path):
        if data_path.name not in expected_hashes:
            raise ValueError(f"{manifest_path}: missing SHA-256 for {data_path.name}")
    for filename, expected_hash in expected_hashes.items():
        if Path(filename).name != filename or not isinstance(expected_hash, str):
            raise ValueError(f"{manifest_path}: invalid SHA-256 entry for {filename!r}")
        data_path = manifest_path.parent / filename
        if not data_path.is_file() or file_sha256(data_path) != expected_hash:
            raise ValueError(f"{data_path}: SHA-256 does not match {manifest_path}")

    generation = manifest.get("generation")
    if not isinstance(generation, dict):
        raise ValueError(f"{manifest_path}: generation must be an object")
    for field, expected in {
        "spacing_m": 200,
        "node_id_width": node_width,
        "road_id_width": road_width,
        "speed_choices_kmh": [20, 30, 40, 50, 60],
        "speed_sampling": "uniform with random.Random(seed)",
    }.items():
        if generation.get(field) != expected:
            raise ValueError(
                f"{manifest_path}: generation.{field} must be {expected!r}, "
                f"got {generation.get(field)!r}"
            )

    expected_nodes = [
        (f"N{row * cols + col:0{node_width}d}", col * 200, row * 200)
        for row in range(rows)
        for col in range(cols)
    ]
    actual_nodes = []
    for row in node_rows:
        x_m = parse_finite_float(row["x_m"], "x_m", str(nodes_path))
        y_m = parse_finite_float(row["y_m"], "y_m", str(nodes_path))
        if not x_m.is_integer() or not y_m.is_integer():
            raise ValueError(f"{nodes_path}: grid coordinates must be integer meters")
        actual_nodes.append((row["node_id"], int(x_m), int(y_m)))
    if actual_nodes != expected_nodes:
        raise ValueError(f"{nodes_path}: node IDs, coordinates, or row-major order do not match {graph_id}")

    expected_edges: list[tuple[str, str]] = []
    for row in range(rows):
        for col in range(cols):
            start = f"N{row * cols + col:0{node_width}d}"
            if col + 1 < cols:
                expected_edges.append((start, f"N{row * cols + col + 1:0{node_width}d}"))
            if row + 1 < rows:
                expected_edges.append((start, f"N{(row + 1) * cols + col:0{node_width}d}"))

    actual_edges: list[tuple[str, str]] = []
    rng = random.Random(expected_seed)
    for road_number, row in enumerate(road_rows):
        expected_road_id = f"R{road_number:0{road_width}d}"
        if row["road_id"] != expected_road_id:
            raise ValueError(f"{roads_path}: expected road ID {expected_road_id}, got {row['road_id']}")
        if row["length_m"] != "200":
            raise ValueError(f"{roads_path}: {expected_road_id} must have length 200 m")
        expected_speed = rng.choice((20, 30, 40, 50, 60))
        try:
            actual_speed = int(row["speed_kmh"])
        except ValueError as exc:
            raise ValueError(f"{roads_path}: {expected_road_id} has an invalid speed") from exc
        if actual_speed != expected_speed or actual_speed not in CITY40_SPEEDS_KMH:
            raise ValueError(
                f"{roads_path}: {expected_road_id} speed does not match seed {expected_seed}"
            )
        actual_edges.append((row["u"], row["v"]))
    if actual_edges != expected_edges:
        raise ValueError(f"{roads_path}: roads or their order do not match {graph_id} rules")

    if graph_id.startswith("grid"):
        scenarios_path = manifest_path.parent / "scenarios.json"
        try:
            scenarios = json.loads(scenarios_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{scenarios_path}: scale graph must have valid scenarios.json") from exc
        if scenarios != {"normal": {"speed_factors": {}, "closed_roads": []}}:
            raise ValueError(f"{scenarios_path}: scale graph must contain normal scenario only")


def is_reachable(
    node_ids: set[str], road_rows: list[dict[str, str]], start: str, goal: str,
    closed_roads: set[str],
) -> bool:
    adjacency = {node_id: [] for node_id in node_ids}
    for road in road_rows:
        if road["road_id"] in closed_roads:
            continue
        adjacency[road["u"]].append(road["v"])
        adjacency[road["v"]].append(road["u"])
    visited = {start}
    pending = [start]
    while pending:
        node = pending.pop()
        if node == goal:
            return True
        for neighbor in adjacency[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    return False


def validate_data(
    nodes_path: Path,
    roads_path: Path,
    scenarios_path: Path,
    manifest_path: Path | None = None,
    *,
    verbose: bool = True,
) -> None:
    node_rows = read_csv(nodes_path, NODE_FIELDS)
    road_rows = read_csv(roads_path, ROAD_FIELDS)

    coords: dict[str, tuple[float, float]] = {}
    for row_number, row in enumerate(node_rows, start=2):
        node_id = row["node_id"]
        location = f"{nodes_path}:{row_number}"
        if not node_id:
            raise ValueError(f"{location}: node_id cannot be empty")
        if node_id in coords:
            raise ValueError(f"{location}: duplicate node_id {node_id!r}")
        x_m = parse_finite_float(row["x_m"], "x_m", location)
        y_m = parse_finite_float(row["y_m"], "y_m", location)
        coords[node_id] = (x_m, y_m)

    road_ids: set[str] = set()
    endpoint_pairs: set[frozenset[str]] = set()
    for row_number, row in enumerate(road_rows, start=2):
        road_id, u, v = row["road_id"], row["u"], row["v"]
        location = f"{roads_path}:{row_number}"
        if not road_id:
            raise ValueError(f"{location}: road_id cannot be empty")
        if road_id in road_ids:
            raise ValueError(f"{location}: duplicate road_id {road_id!r}")
        road_ids.add(road_id)
        if u not in coords or v not in coords:
            missing = [node for node in (u, v) if node not in coords]
            raise ValueError(f"{location}: unknown endpoint(s) {missing}")
        if u == v:
            raise ValueError(f"{location}: self-loop at node {u!r} is not allowed")

        pair = frozenset((u, v))
        if pair in endpoint_pairs:
            raise ValueError(f"{location}: duplicate undirected endpoint pair {u!r}-{v!r}")
        endpoint_pairs.add(pair)

        length_m = parse_finite_float(row["length_m"], "length_m", location)
        speed_kmh = parse_finite_float(row["speed_kmh"], "speed_kmh", location)
        if length_m <= 0:
            raise ValueError(f"{location}: length_m must be greater than zero")
        if speed_kmh <= 0:
            raise ValueError(f"{location}: speed_kmh must be greater than zero")

        x1, y1 = coords[u]
        x2, y2 = coords[v]
        straight_line_m = math.hypot(x2 - x1, y2 - y1)
        if length_m + GEOMETRY_TOLERANCE_M < straight_line_m:
            raise ValueError(
                f"{location}: length_m ({length_m}) is shorter than endpoint "
                f"distance ({straight_line_m})"
            )

    try:
        scenarios: Any = json.loads(scenarios_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{scenarios_path}: invalid JSON: {exc}") from exc
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValueError(f"{scenarios_path}: expected a non-empty JSON object of scenarios")

    for scenario_id, scenario in scenarios.items():
        location = f"{scenarios_path}, scenario {scenario_id!r}"
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError(f"{scenarios_path}: scenario IDs must be non-empty strings")
        if not isinstance(scenario, dict) or set(scenario) != SCENARIO_FIELDS:
            raise ValueError(
                f"{location}: expected exactly the fields "
                f"{sorted(SCENARIO_FIELDS)}"
            )
        factors = scenario["speed_factors"]
        closed_roads = scenario["closed_roads"]
        if not isinstance(factors, dict):
            raise ValueError(f"{location}: speed_factors must be an object")
        if not isinstance(closed_roads, list):
            raise ValueError(f"{location}: closed_roads must be an array")

        for road_id, factor in factors.items():
            if road_id not in road_ids:
                raise ValueError(f"{location}: unknown road in speed_factors: {road_id!r}")
            if isinstance(factor, bool) or not isinstance(factor, (int, float)):
                raise ValueError(f"{location}: speed factor for {road_id!r} must be numeric")
            if not math.isfinite(factor) or not 0 < factor <= 1:
                raise ValueError(f"{location}: speed factor for {road_id!r} must be in (0, 1]")

        if any(not isinstance(road_id, str) for road_id in closed_roads):
            raise ValueError(f"{location}: closed_roads must contain road ID strings")
        if len(closed_roads) != len(set(closed_roads)):
            raise ValueError(f"{location}: closed_roads contains duplicate road IDs")
        for road_id in closed_roads:
            if road_id not in road_ids:
                raise ValueError(f"{location}: unknown closed road {road_id!r}")
        overlap = set(factors) & set(closed_roads)
        if overlap:
            raise ValueError(f"{location}: roads cannot be both slowed and closed: {sorted(overlap)}")
        if "N00" in coords and "N39" in coords and not is_reachable(
            set(coords), road_rows, "N00", "N39", set(closed_roads)
        ):
            raise ValueError(f"{location}: N00 cannot reach N39 after the closures")

    if manifest_path is None:
        candidate = nodes_path.parent / "manifest.json"
        manifest_path = candidate if candidate.is_file() else None
    if manifest_path is not None:
        validate_grid_manifest(manifest_path, nodes_path, roads_path, node_rows, road_rows)

    manifest_note = ", manifest and SHA-256 checked" if manifest_path else ""
    if verbose:
        print(
            f"Validation passed: {len(coords)} nodes, {len(road_ids)} roads, "
            f"{len(scenarios)} scenario(s){manifest_note}."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate road-network input data.")
    parser.add_argument("--nodes", type=Path, default=Path("data/nodes.csv"))
    parser.add_argument("--roads", type=Path, default=Path("data/roads.csv"))
    parser.add_argument("--scenarios", type=Path, default=Path("data/scenarios.json"))
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    validate_data(args.nodes, args.roads, args.scenarios, args.manifest)


if __name__ == "__main__":
    main()
