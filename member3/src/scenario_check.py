"""40节点数据联调；使用NetworkX作独立参考，不执行两种组内算法或性能计时。"""
import json
from pathlib import Path
from types import SimpleNamespace
import networkx as nx
from src.data_loader import load_graph
from src.data_checks import audit_dataset, audit_loaded, check_city_scenarios, sha256
from src.validation import require, graph_state, nx_graph, close

ROOT = Path(__file__).resolve().parents[1]


def check_city(folder):
    coords, roads, scenarios, manifest = audit_dataset(folder, 'city40')
    records = []
    for scenario_id in ('normal', 'congested', 'closed'):
        paths = [str(folder/n) for n in ('nodes.csv', 'roads.csv', 'scenarios.json')]
        g = load_graph(*paths, scenario_id)
        audit_loaded(g, coords, roads, scenarios, scenario_id)
        again = load_graph(*paths, scenario_id)
        require(graph_state(g) == graph_state(again), '重复加载改变了权重')
        net = nx_graph(g)
        path = nx.shortest_path(net, 'N00', 'N39', weight='weight')
        edges = [next(e for e in g.adj[u] if e.to == v) for u, v in zip(path, path[1:])]
        records.append({'graph_id': 'city40', 'scenario_id': scenario_id, 'reference': 'NetworkX',
                        'path': path, 'road_ids': [e.road_id for e in edges],
                        'total_time_s': sum(e.time_s for e in edges),
                        'total_distance_m': sum(e.length_m for e in edges),
                        'node_count': len(g.coords), 'arc_count': sum(map(len, g.adj.values()))})
    basis = json.loads((folder/'scenario_basis.json').read_text(encoding='utf-8-sig'))
    baseline = basis['baseline']
    # 情景选取由已保存的参考Dijkstra路线定义，不用NetworkX的等成本破平局规则替代。
    normal = records[0]
    require(close(normal['total_time_s'], baseline['total_time_s']), '基准成本与独立参考不符')
    g = load_graph(*[str(folder/n) for n in ('nodes.csv','roads.csv','scenarios.json')], 'normal')
    from src.validation import validate_result
    validate_result(g, 'N00', 'N39', SimpleNamespace(found=True, **baseline))
    require(all(basis['source_sha256'][n] == sha256(folder/n) for n in ('nodes.csv','roads.csv')),
            '基准引用的数据哈希不符')
    check_city_scenarios(scenarios, SimpleNamespace(road_ids=baseline['road_ids']))
    require(all(r['total_time_s'] >= normal['total_time_s']-1e-6 for r in records), '降速删边后最优时间下降')
    return {'status': 'data_integration_passed', 'data_version': manifest['data_version'],
            'team_algorithm_verified': False, 'scenario_frozen': False, 'performance_measured': False,
            'purpose': '数据加载与情景参考核验，不是正式两算法实验',
            'source_sha256': {p.name: sha256(p) for p in sorted(folder.iterdir()) if p.is_file()},
            'scenarios': records,
            'pending': ['罗永军交付并验证Dijkstra和A*', '组内算法复核基准路线后冻结情景',
                        '四种规模路网与全量性能实验']}


def main():
    result = check_city(ROOT/'data/city40')
    out = ROOT/'integration/city40-data-check.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('40节点数据端联调通过：')
    for r in result['scenarios']:
        print(f"  {r['scenario_id']}: {r['arc_count']}条有向边，{r['total_time_s']:.1f}s，{r['total_distance_m']:.0f}m")
    print('未运行组内Dijkstra/A*，未做性能计时，情景尚未冻结。\n记录：',out)


if __name__ == '__main__':
    main()
