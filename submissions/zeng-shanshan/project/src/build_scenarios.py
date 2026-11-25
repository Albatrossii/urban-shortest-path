"""Build the fixed traffic scenarios from the city40 normal-route baseline.

Run this module from the project root. The baseline route is computed with a
reference Dijkstra implementation using the task's specified tie-breaking
rules. It must still be compared with the algorithm module used by the team.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
from collections import deque
from pathlib import Path
from typing import Any


START = "N00"
GOAL = "N39"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def read_graph(data_dir: Path) -> tuple[dict[str, tuple[int, int]], list[dict[str, Any]]]:
    with (data_dir / "nodes.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        coords = {
            row["node_id"]: (int(row["x_m"]), int(row["y_m"]))
            for row in csv.DictReader(stream)
        }
    roads: list[dict[str, Any]] = []
    with (data_dir / "roads.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            length_m = float(row["length_m"])
            speed_kmh = float(row["speed_kmh"])
            roads.append(
                {
                    "road_id": row["road_id"],
                    "u": row["u"],
                    "v": row["v"],
                    "length_m": length_m,
                    "speed_kmh": speed_kmh,
                    "time_s": 3.6 * length_m / speed_kmh,
                }
            )
    return coords, roads


def dijkstra(
    node_ids: list[str], roads: list[dict[str, Any]], start: str, goal: str
) -> dict[str, Any]:
    adjacency: dict[str, list[tuple[str, str, float, float]]] = {
        node_id: [] for node_id in node_ids
    }
    road_by_id = {road["road_id"]: road for road in roads}
    for road in roads:
        u, v = road["u"], road["v"]
        arc = (road["road_id"], road["time_s"], road["length_m"])
        adjacency[u].append((v, *arc))
        adjacency[v].append((u, *arc))
    for arcs in adjacency.values():
        arcs.sort(key=lambda arc: (arc[0], arc[1]))

    distances = {node_id: math.inf for node_id in node_ids}
    previous: dict[str, tuple[str, str]] = {}
    distances[start] = 0.0
    heap = [(0.0, start)]
    closed: set[str] = set()
    expanded_nodes = 0

    while heap:
        distance, node = heapq.heappop(heap)
        if distance != distances[node] or node in closed:
            continue
        closed.add(node)
        expanded_nodes += 1
        if node == goal:
            break
        for neighbor, road_id, time_s, _length_m in adjacency[node]:
            new_distance = distance + time_s
            if new_distance < distances[neighbor]:
                distances[neighbor] = new_distance
                previous[neighbor] = (node, road_id)
                heapq.heappush(heap, (new_distance, neighbor))

    if goal not in closed:
        raise ValueError(f"No path from {start} to {goal}")

    path = [goal]
    road_ids: list[str] = []
    current = goal
    while current != start:
        parent, road_id = previous[current]
        road_ids.append(road_id)
        path.append(parent)
        current = parent
    path.reverse()
    road_ids.reverse()
    return {
        "path": path,
        "road_ids": road_ids,
        "total_time_s": distances[goal],
        "total_distance_m": sum(road_by_id[road_id]["length_m"] for road_id in road_ids),
        "expanded_nodes": expanded_nodes,
    }


def bellman_ford_time(
    node_ids: list[str], roads: list[dict[str, Any]], start: str, goal: str
) -> float:
    """Independent distance check for the reference Dijkstra baseline."""
    distances = {node_id: math.inf for node_id in node_ids}
    distances[start] = 0.0
    for _ in range(len(node_ids) - 1):
        changed = False
        for road in roads:
            for u, v in ((road["u"], road["v"]), (road["v"], road["u"])):
                candidate = distances[u] + road["time_s"]
                if candidate < distances[v]:
                    distances[v] = candidate
                    changed = True
        if not changed:
            break
    return distances[goal]


def networkx_check(
    node_ids: list[str], roads: list[dict[str, Any]], baseline_time_s: float
) -> dict[str, Any]:
    try:
        import networkx as nx
    except ImportError:
        return {"status": "not run; NetworkX is not installed in this interpreter"}

    graph = nx.DiGraph()
    graph.add_nodes_from(node_ids)
    for road in roads:
        graph.add_edge(road["u"], road["v"], weight=road["time_s"])
        graph.add_edge(road["v"], road["u"], weight=road["time_s"])
    networkx_time = nx.shortest_path_length(graph, source=START, target=GOAL, weight="weight")
    networkx_path = nx.shortest_path(graph, source=START, target=GOAL, weight="weight")
    matches = math.isclose(
        baseline_time_s, networkx_time, rel_tol=1e-9, abs_tol=1e-6
    )
    if not matches:
        raise ValueError(
            f"Reference Dijkstra time {baseline_time_s} does not match "
            f"NetworkX time {networkx_time}"
        )
    return {
        "status": "passed",
        "networkx_version": nx.__version__,
        "total_time_s": networkx_time,
        "matches_dijkstra": True,
        "one_shortest_path": networkx_path,
        "path_may_differ_when_multiple_equal_cost_routes_exist": True,
    }


def is_reachable(
    node_ids: list[str], roads: list[dict[str, Any]], start: str, goal: str, closed: set[str]
) -> bool:
    adjacency = {node_id: [] for node_id in node_ids}
    for road in roads:
        if road["road_id"] in closed:
            continue
        adjacency[road["u"]].append(road["v"])
        adjacency[road["v"]].append(road["u"])
    visited = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == goal:
            return True
        for neighbor in adjacency[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(data_dir: Path) -> dict[str, Any]:
    manifest_path = data_dir / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("data_version") != "city40-v1.0":
        raise ValueError(f"{manifest_path}: expected city40-v1.0 data")

    coords, roads = read_graph(data_dir)
    node_ids = sorted(coords)
    source_hashes = {
        "nodes.csv": sha256(data_dir / "nodes.csv"),
        "roads.csv": sha256(data_dir / "roads.csv"),
    }
    baseline = dijkstra(node_ids, roads, START, GOAL)
    independent_time = bellman_ford_time(node_ids, roads, START, GOAL)
    if not math.isclose(
        baseline["total_time_s"], independent_time, rel_tol=1e-9, abs_tol=1e-6
    ):
        raise ValueError("Dijkstra and Bellman-Ford baseline times do not agree")
    nx_result = networkx_check(node_ids, roads, baseline["total_time_s"])
    basis_path = data_dir / "scenario_basis.json"
    if nx_result.get("status") != "passed" and basis_path.is_file():
        previous_basis = read_json(basis_path)
        previous_nx = previous_basis.get("networkx_check", {})
        if (
            previous_basis.get("source_sha256") == source_hashes
            and previous_nx.get("status") == "passed"
            and math.isclose(
                previous_nx.get("total_time_s", math.inf),
                baseline["total_time_s"],
                rel_tol=1e-9,
                abs_tol=1e-6,
            )
        ):
            nx_result = previous_nx

    road_count = len(baseline["road_ids"])
    congested_count = max(1, math.ceil(0.3 * road_count))
    congested_start = math.floor((road_count - congested_count) / 2)
    congested_roads = baseline["road_ids"][congested_start : congested_start + congested_count]
    closed_road = baseline["road_ids"][math.floor(road_count / 2)]
    scenarios = {
        "normal": {"speed_factors": {}, "closed_roads": []},
        "congested": {
            "speed_factors": {road_id: 0.3 for road_id in congested_roads},
            "closed_roads": [],
        },
        "closed": {"speed_factors": {}, "closed_roads": [closed_road]},
    }
    if not is_reachable(node_ids, roads, START, GOAL, {closed_road}):
        raise ValueError(f"Closing {closed_road} disconnects {START} from {GOAL}")

    scenario_path = data_dir / "scenarios.json"
    scenario_path.write_text(
        json.dumps(scenarios, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    basis = {
        "graph_id": "city40",
        "scenario_id": "normal",
        "start": START,
        "goal": GOAL,
        "source_sha256": source_hashes,
        "baseline": baseline,
        "independent_distance_check": {
            "method": "Bellman-Ford over the same physical roads",
            "total_time_s": independent_time,
            "matches_dijkstra": True,
        },
        "networkx_check": nx_result,
        "scenario_selection": {
            "congested_road_ids": congested_roads,
            "speed_factor": 0.3,
            "closed_road_id": closed_road,
            "closed_graph_reachable": True,
        },
        "cross_validation_status": (
            "NetworkX distance check passed; pending comparison with Luo Yongjun's tested algorithm. "
            "This local reference route remains a draft basis until team sign-off."
            if nx_result.get("status") == "passed"
            else "Pending NetworkX and Luo Yongjun's tested algorithm checks; "
            "this local reference route is a draft basis, not the team's final sign-off."
        ),
    }
    basis_path.write_text(
        json.dumps(basis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        raise ValueError(f"{manifest_path}: sha256 must be an object")
    hashes["scenarios.json"] = sha256(scenario_path)
    hashes["scenario_basis.json"] = sha256(basis_path)
    manifest["scenario_generation"] = {
        "baseline_source": (
            "reference Dijkstra; Bellman-Ford and NetworkX distance checks passed; "
            "Luo Yongjun cross-validation pending"
            if nx_result.get("status") == "passed"
            else "reference Dijkstra; independent Bellman-Ford check passed; "
            "NetworkX and Luo Yongjun cross-validation pending"
        ),
        "baseline_query": f"{START}->{GOAL}",
        "baseline_road_ids": baseline["road_ids"],
        "congested_road_ids": congested_roads,
        "closed_road_id": closed_road,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return basis


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    basis = build(args.data_dir)
    baseline = basis["baseline"]
    print(f"Baseline {START}->{GOAL}: {len(baseline['road_ids'])} roads")
    print(f"Time: {baseline['total_time_s']:.12g} s; distance: {baseline['total_distance_m']:.12g} m")
    print(f"Congested roads: {basis['scenario_selection']['congested_road_ids']}")
    print(f"Closed road: {basis['scenario_selection']['closed_road_id']}")
    if basis["networkx_check"].get("status") == "passed":
        print("NetworkX distance check passed; Luo Yongjun cross-check is still pending.")
    else:
        print("NetworkX and Luo Yongjun cross-checks are still pending.")


if __name__ == "__main__":
    main()
