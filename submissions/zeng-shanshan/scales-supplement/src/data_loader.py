"""Load and validate a road network for the shortest-path algorithms."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from src.validate_data import validate_data


@dataclass(frozen=True)
class Arc:
    """One directed road arc in the scenario-specific graph."""

    to: str
    road_id: str
    length_m: float
    time_s: float


@dataclass(frozen=True)
class Graph:
    """Validated graph data shared by Dijkstra and A*."""

    coords: dict[str, tuple[float, float]]
    adj: dict[str, list[Arc]]
    vmax_kmh: float


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} file does not exist: {path}")


def load_graph(
    nodes_path: str,
    roads_path: str,
    scenarios_path: str,
    scenario_id: str,
) -> Graph:
    """Load a validated, undirected-road graph for one traffic scenario.

    Physical roads are stored once in ``roads.csv`` and expanded here into
    forward and reverse directed arcs. Closed roads are omitted. Speed factors
    are applied to the original speed on every call, so reloading a scenario
    never compounds a previous adjustment.
    """
    node_file = Path(nodes_path)
    road_file = Path(roads_path)
    scenario_file = Path(scenarios_path)
    for path, label in (
        (node_file, "Node data"),
        (road_file, "Road data"),
        (scenario_file, "Scenario data"),
    ):
        _require_file(path, label)

    # Validate before building the graph. Validation stays quiet during graph
    # loading; the standalone validator remains responsible for its CLI report.
    validate_data(node_file, road_file, scenario_file, verbose=False)

    with node_file.open("r", encoding="utf-8-sig", newline="") as stream:
        coords = {
            row["node_id"]: (float(row["x_m"]), float(row["y_m"]))
            for row in csv.DictReader(stream)
        }

    with road_file.open("r", encoding="utf-8-sig", newline="") as stream:
        roads = list(csv.DictReader(stream))

    try:
        scenarios = json.loads(scenario_file.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:  # Normally reported by validation first.
        raise ValueError(f"Invalid JSON in scenario file {scenario_file}: {exc}") from exc
    if scenario_id not in scenarios:
        available = ", ".join(sorted(scenarios))
        raise ValueError(
            f"Unknown scenario {scenario_id!r} in {scenario_file}; "
            f"available scenarios: {available}"
        )

    scenario = scenarios[scenario_id]
    speed_factors = scenario["speed_factors"]
    closed_roads = set(scenario["closed_roads"])
    vmax_kmh = max(float(road["speed_kmh"]) for road in roads)
    adjacency: dict[str, list[Arc]] = {node_id: [] for node_id in coords}

    for road in roads:
        road_id = road["road_id"]
        if road_id in closed_roads:
            continue

        u, v = road["u"], road["v"]
        length_m = float(road["length_m"])
        original_speed_kmh = float(road["speed_kmh"])
        effective_speed_kmh = original_speed_kmh * speed_factors.get(road_id, 1.0)
        time_s = 3.6 * length_m / effective_speed_kmh

        adjacency[u].append(Arc(v, road_id, length_m, time_s))
        adjacency[v].append(Arc(u, road_id, length_m, time_s))

    for arcs in adjacency.values():
        arcs.sort(key=lambda arc: (arc.to, arc.road_id))

    return Graph(coords=coords, adj=adjacency, vmax_kmh=vmax_kmh)
