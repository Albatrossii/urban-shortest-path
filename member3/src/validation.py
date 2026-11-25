import copy
import math
import networkx as nx
from src.contracts import Arc


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


def graph_state(g):
    return (tuple(sorted((n, tuple(xy)) for n, xy in g.coords.items())),
            tuple((n, tuple((e.to, e.road_id, e.length_m, e.time_s)
                            for e in es)) for n, es in sorted(g.adj.items())),
            g.vmax_kmh)


def nx_graph(g):
    out = nx.DiGraph()
    out.add_nodes_from(g.coords)
    for u, es in g.adj.items():
        for e in es:
            out.add_edge(u, e.to, weight=e.time_s)
    return out


def validate_graph(g):
    require(set(g.coords) == set(g.adj), 'coords 与 adj 节点集合不一致')
    require(math.isfinite(g.vmax_kmh) and g.vmax_kmh > 0, '无效全网最高速度')
    for n, xy in g.coords.items():
        require(len(xy) == 2 and all(math.isfinite(v) for v in xy), f'{n} 坐标无效')
        es = g.adj[n]
        require([(e.to, e.road_id) for e in es] == sorted((e.to, e.road_id) for e in es),
                f'{n} 邻接表未排序')
        require(len({e.to for e in es}) == len(es), f'{n} 存在平行边')
        for e in es:
            require(e.to in g.coords and e.to != n, '边端点无效')
            require(all(math.isfinite(v) and v > 0 for v in (e.length_m, e.time_s)), '边权非法')
            require(e.length_m + 1e-9 >= math.dist(xy, g.coords[e.to]), '边长小于直线距离')
            require(3.6 * e.length_m / e.time_s <= g.vmax_kmh + 1e-9, '速度超过启发函数上界')


def validate_result(g, start, goal, result):
    require(type(result.found) is bool, 'found 必须为 bool')
    require(type(result.expanded_nodes) is int and 1 <= result.expanded_nodes <= len(g.coords),
            'expanded_nodes 应包含起点且不重复计数')
    require(isinstance(result.path, list) and isinstance(result.road_ids, list), '路径必须为列表')
    ref = nx_graph(g)
    reachable = nx.has_path(ref, start, goal)
    require(result.found == reachable, '可达性与 NetworkX 不一致')
    if not reachable:
        require(result.path == [] and result.road_ids == [] and result.total_time_s is None
                and result.total_distance_m is None, '不可达返回格式错误')
        return
    require(result.path and result.path[0] == start and result.path[-1] == goal, '起终点不符')
    require(len(result.road_ids) == len(result.path) - 1, '道路序列长度错误')
    require(len(set(result.path)) == len(result.path), '正权最短路不应含环')
    total_t = total_d = 0.0
    for u, v, rid in zip(result.path, result.path[1:], result.road_ids):
        found = [e for e in g.adj.get(u, []) if e.to == v and e.road_id == rid]
        require(len(found) == 1, f'路径使用不存在或已封闭的道路：{u}->{v}/{rid}')
        total_t += found[0].time_s
        total_d += found[0].length_m
    require(close(result.total_time_s, total_t), '返回时间与逐边求和不一致')
    require(close(result.total_distance_m, total_d), '返回距离与逐边求和不一致')
    require(close(total_t, nx.shortest_path_length(ref, start, goal, weight='weight')),
            '返回路径不是 NetworkX 验证的最短时间路径')
    if start == goal:
        require(result.expanded_nodes == 1, '起终点相同时扩展数应为 1')


def checked_call(fn, g, start, goal):
    before = graph_state(g)
    r = fn(g, start, goal)
    require(graph_state(g) == before, '算法修改了 Graph')
    validate_result(g, start, goal, r)
    return r


def signature(r):
    return (r.found, tuple(r.path), tuple(r.road_ids), r.total_time_s,
            r.total_distance_m, r.expanded_nodes)


def boundary_checks(backend):
    coords = {'A': (0, 0), 'B': (100, 0), 'C': (200, 0), 'Z': (0, 200)}
    adj = {n: [] for n in coords}
    for rid, u, v, length in [('AB', 'A', 'B', 100), ('BC', 'B', 'C', 100), ('AC', 'A', 'C', 250)]:
        adj[u].append(Arc(v, rid, length, length / 10))
        adj[v].append(Arc(u, rid, length, length / 10))
    adj = {n: sorted(es, key=lambda e: (e.to, e.road_id)) for n, es in adj.items()}
    logs = []
    for name in ('dijkstra', 'astar'):
        fn = getattr(backend, name)
        g = backend.make_graph(copy.deepcopy(coords), copy.deepcopy(adj), 36)
        validate_graph(g)
        for start, goal in [('A', 'C'), ('A', 'A'), ('A', 'Z')]:
            r = checked_call(fn, g, start, goal)
            if (start, goal) == ('A', 'C'):
                require(close(r.total_time_s, 20) and close(r.total_distance_m, 200), '手算示例错误')
            logs.append({'algorithm': name, 'case': f'{start}->{goal}', 'passed': True})
        # 关闭 BC 后只能走 AC，25 秒。
        closed = {n: [e for e in es if e.road_id != 'BC'] for n, es in adj.items()}
        r = checked_call(fn, backend.make_graph(copy.deepcopy(coords), closed, 36), 'A', 'C')
        require(close(r.total_time_s, 25), '封路绕行失败')
        # AC 改为 200m 后，与 A-B-C 等成本，允许任意一条。
        equal = {n: [Arc(e.to, e.road_id, 200, 20) if e.road_id == 'AC' else e
                     for e in es] for n, es in adj.items()}
        checked_call(fn, backend.make_graph(copy.deepcopy(coords), equal, 36), 'A', 'C')
        for start, goal in [('MISSING', 'A'), ('A', 'MISSING')]:
            try:
                fn(g, start, goal)
            except ValueError:
                pass
            else:
                raise ValueError(f'{name} 对不存在的节点没有抛出 ValueError')
        logs.extend({'algorithm': name, 'case': c, 'passed': True}
                    for c in ['封路绕行', '等成本路线', '起点不存在', '终点不存在'])
    return logs
