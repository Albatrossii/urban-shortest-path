"""独立核对队友提交的数据及加载结果；不实现正式数据加载器。"""
import csv
import hashlib
import json
import math
from src.validation import require, close, validate_graph, graph_state, nx_graph
import networkx as nx


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_dataset(folder, graph_id):
    nodes = read_csv(folder / 'nodes.csv')
    roads = read_csv(folder / 'roads.csv')
    scenarios = json.loads((folder / 'scenarios.json').read_text(encoding='utf-8'))
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    coords = {r['node_id']: (float(r['x_m']), float(r['y_m'])) for r in nodes}
    require(len(coords) == len(nodes), '节点编号重复')
    require(len({r['road_id'] for r in roads}) == len(roads), '道路编号重复')
    expected_n = 40 if graph_id == 'city40' else int(graph_id[4:])
    side = math.isqrt(expected_n)
    rows, cols = (5, 8) if graph_id == 'city40' else (side, side)
    require(len(nodes) == expected_n, f'{graph_id} 节点数错误')
    require(len(roads) == rows * (cols - 1) + cols * (rows - 1), '物理道路数错误')
    width = 2 if graph_id == 'city40' else 4
    require(set(coords) == {f'N{i:0{width}d}' for i in range(expected_n)}, '节点编号不符合约定')
    for i in range(expected_n):
        require(coords[f'N{i:0{width}d}'] == (200 * (i % cols), 200 * (i // cols)), '坐标不符合网格约定')
    pairs = set()
    base = nx.Graph()
    base.add_nodes_from(coords)
    for road in roads:
        u, v = road['u'], road['v']
        require(u in coords and v in coords and u != v, '道路端点非法')
        key = tuple(sorted((u, v)))
        require(key not in pairs, '存在重复无向道路')
        pairs.add(key)
        length, speed = float(road['length_m']), float(road['speed_kmh'])
        require(math.isfinite(length) and math.isfinite(speed) and length > 0 and speed > 0, '长度速度非法')
        require(close(length, 200) and close(math.dist(coords[u], coords[v]), 200), '不是相邻网格边')
        require(speed in (20, 30, 40, 50, 60), '正常速度不在约定集合内')
        base.add_edge(u, v)
    require(nx.is_connected(base), '基础路网不连通')
    require(scenarios.get('normal') == {'speed_factors': {}, 'closed_roads': []}, 'normal 情景必须为空覆盖')
    require(manifest.get('data_version'), 'manifest 缺少 data_version')
    require(manifest.get('node_count') == expected_n and manifest.get('road_count') == len(roads), 'manifest 规模错误')
    require(manifest.get('seed') == 20261124 + (0 if graph_id == 'city40' else expected_n), 'manifest 种子错误')
    # 只在读取时兼容两份清单约定；不重写交付文件或其哈希。
    for shape in [manifest[k] for k in ('grid_shape',) if k in manifest]:
        require(shape in ([rows, cols], {'rows': rows, 'cols': cols}), 'manifest 网格规格错误')
    require('grid_shape' in manifest, 'manifest 缺少 grid_shape')
    require(manifest.get('units') in (
        {'distance': 'm', 'speed': 'km/h', 'time': 's'},
        {'coordinates': 'm', 'length': 'm', 'speed': 'km/h', 'time': 's'}), 'manifest 单位错误')
    hash_maps = [manifest[k] for k in ('files_sha256', 'sha256') if k in manifest]
    require(hash_maps and all(isinstance(h, dict) for h in hash_maps), 'manifest 缺少有效哈希映射')
    for hashes in hash_maps:
        require(all(n in hashes for n in ('nodes.csv', 'roads.csv', 'scenarios.json')), 'manifest 必需文件哈希缺失')
        for name, expected in hashes.items():
            require(isinstance(name, str) and name not in ('', '.', '..') and '/' not in name and '\\' not in name,
                    'manifest 哈希文件名不安全')
            file = folder / name
            require(file.is_file() and expected == sha256(file), f'{name} 哈希不一致')
    return coords, roads, scenarios, manifest


def audit_loaded(g, coords, roads, scenarios, scenario_id):
    validate_graph(g)
    require(g.coords == coords, '加载器改变了节点或坐标')
    require(close(g.vmax_kmh, max(float(r['speed_kmh']) for r in roads)), '加载器 vmax_kmh 不是原始最高速度')
    conf = scenarios[scenario_id]
    require(set(conf) == {'speed_factors', 'closed_roads'}, '情景配置字段错误')
    ids = {r['road_id'] for r in roads}
    require(set(conf['speed_factors']) <= ids and set(conf['closed_roads']) <= ids, '情景包含未知道路')
    require(len(set(conf['closed_roads'])) == len(conf['closed_roads']), '封路重复')
    expected = {}
    for r in roads:
        factor = conf['speed_factors'].get(r['road_id'], 1)
        require(isinstance(factor, (int, float)) and 0 < factor <= 1, '非法降速系数')
        if r['road_id'] not in conf['closed_roads']:
            length = float(r['length_m'])
            seconds = 3.6 * length / (float(r['speed_kmh']) * factor)
            for u, v in ((r['u'], r['v']), (r['v'], r['u'])):
                expected[(u, v, r['road_id'])] = (length, seconds)
    actual = {(u, e.to, e.road_id): (e.length_m, e.time_s) for u, es in g.adj.items() for e in es}
    require(set(actual) == set(expected), '加载器未正确展开双向边或移除封路')
    for key in actual:
        require(all(close(a, b) for a, b in zip(actual[key], expected[key])), f'{key} 加载权重错误')


def check_city_scenarios(scenarios, baseline):
    require(set(scenarios) == {'normal', 'congested', 'closed'}, '展示路网须恰有三种情景')
    p = baseline.road_ids
    require(len(p) > 0, '基准路径为空')
    k = max(1, math.ceil(.3 * len(p)))
    begin = (len(p) - k) // 2
    require(scenarios['congested'] == {'speed_factors': {r: .3 for r in p[begin:begin+k]}, 'closed_roads': []},
            '拥堵道路不是按正常基准路径中央段选取')
    require(scenarios['closed'] == {'speed_factors': {}, 'closed_roads': [p[len(p)//2]]},
            '封路配置与正常基准路径不符')
