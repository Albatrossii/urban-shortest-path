"""从项目根目录运行 python -m src.experiments --help。"""
import argparse
import csv
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from src.contracts import CONFIG, SCHEMAS
from src.validation import boundary_checks, checked_call, close, require, graph_state
from src.data_checks import read_csv, sha256, audit_dataset, audit_loaded, check_city_scenarios
from src.benchmark import benchmark_pair

ROOT = Path(__file__).resolve().parents[1]


def dump_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def environment(mode, cfg, data_root):
    files = {}
    for p in sorted(data_root.rglob('*')):
        if p.is_file():
            files[str(p.relative_to(data_root))] = sha256(p)
    source_hashes = {str(p.relative_to(ROOT)): sha256(p) for base in ('src', 'examples')
                     for p in sorted((ROOT / base).rglob('*.py'))}
    try:
        git = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                             capture_output=True, text=True, timeout=3)
        git_head = git.stdout.strip() if git.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        git_head = None
    cpu = platform.processor() or platform.machine()
    memory = None
    if sys.platform == 'darwin':
        try:
            cpu = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip()
            memory = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True))
        except (OSError, subprocess.CalledProcessError):
            pass
    elif hasattr(os, 'sysconf'):
        try:
            memory = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
        except (ValueError, OSError):
            pass
    return {'status': 'preparing', 'mode': mode, 'demo_not_for_paper': mode != 'official',
            'started_at_utc': datetime.now(timezone.utc).isoformat(),
            'platform': platform.platform(), 'cpu': cpu, 'ram_bytes': memory,
            'python': sys.version, 'executable': sys.executable,
            'dependencies': {'networkx': importlib.metadata.version('networkx')},
            'taskbook_version': 'V1.0', 'code_git_head': git_head,
            'source_sha256': source_hashes, 'data_sha256': files, 'parameters': cfg,
            'scope': 'all', 'notes': '数据种子在 manifest，查询种子=20261125+节点数；示例不代表正式实验。'}


def load_official(backend, data_root, scope):
    graph_ids = ['city40'] if scope == 'scenario' else ['city40', 'grid100', 'grid400', 'grid900', 'grid1600']
    prepared = []
    queries = read_csv(data_root / 'queries.csv') if scope == 'all' else []
    for graph_id in graph_ids:
        folder = data_root / graph_id
        coords, roads, scenarios, manifest = audit_dataset(folder, graph_id)
        if graph_id == 'city40':
            work = [('normal', 'city_Q01', 'N00', 'N39'),
                    ('congested', 'city_Q01', 'N00', 'N39'), ('closed', 'city_Q01', 'N00', 'N39')]
        else:
            qs = [q for q in queries if q['graph_id'] == graph_id]
            require(len(qs) == 10 and len({q['query_id'] for q in qs}) == 10, f'{graph_id} 必须有 10 组不同编号查询')
            require(len({(q['start'], q['goal']) for q in qs}) == 10, '查询有重复')
            side = int(len(coords) ** .5)
            for q in qs:
                require(q['start'] in coords and q['goal'] in coords and q['start'] != q['goal'], '查询端点非法')
                distance = sum(abs(a-b) for a,b in zip(coords[q['start']], coords[q['goal']])) / 200
                require(distance >= side - 1, '规模查询距离不满足门槛')
            # 按相同规则独立再生成，防止查询来源与种子不一致。
            from src.prepare import generate_queries
            require(qs == generate_queries(graph_id, coords), '查询与固定种子生成结果不一致')
            work = [('normal', q['query_id'], q['start'], q['goal']) for q in qs]
        cached = {}
        for scenario_id, query_id, start, goal in work:
            if scenario_id not in cached:
                g = backend.load_graph(folder/'nodes.csv', folder/'roads.csv', folder/'scenarios.json', scenario_id)
                audit_loaded(g, coords, roads, scenarios, scenario_id)
                again = backend.load_graph(folder/'nodes.csv', folder/'roads.csv', folder/'scenarios.json', scenario_id)
                require(graph_state(g) == graph_state(again), '重复加载产生累计降速或不稳定结果')
                cached[scenario_id] = g
            prepared.append({'experiment_id': 'scenario' if graph_id == 'city40' else 'scale',
                             'data_version': manifest['data_version'], 'graph_id': graph_id,
                             'scenario_id': scenario_id, 'query_id': query_id, 'start': start, 'goal': goal,
                             'graph': cached[scenario_id]})
    if scope == 'all':
        require(len(queries) == 40, 'queries.csv 必须恰有四种规模共 40 组查询')
    return prepared


def aggregate(qrows, summaries):
    scale = []; speedup = []; scenario = []
    time_index = {(r['graph_id'], r['scenario_id'], r['query_id'], r['algorithm']): r for r in summaries}
    for gid in sorted({r['graph_id'] for r in qrows if r['experiment_id'] == 'scale'}, key=lambda v:int(v[4:])):
        rows = [r for r in qrows if r['graph_id'] == gid]
        ratios = []
        for qid in sorted({r['query_id'] for r in rows}):
            d = time_index[gid, 'normal', qid, 'dijkstra']['median_ms']
            a = time_index[gid, 'normal', qid, 'astar']['median_ms']
            require(a > 0 and d > 0, '计时精度不足，无法计算加速比')
            ratios.append(d/a)
        speedup.append({'graph_id': gid, 'node_count': int(gid[4:]), 'median_paired_speedup': statistics.median(ratios)})
        for name in ('dijkstra', 'astar'):
            qr = [r for r in rows if r['algorithm'] == name]
            ts = [time_index[gid, 'normal', r['query_id'], name]['median_ms'] for r in qr]
            scale.append({'graph_id': gid, 'node_count': int(gid[4:]), 'algorithm': name,
                          'median_query_ms': statistics.median(ts),
                          'median_expanded_nodes': statistics.median(r['expanded_nodes'] for r in qr)})
    for r in [r for r in qrows if r['experiment_id'] == 'scenario']:
        baseline = next(v for v in qrows if v['graph_id'] == r['graph_id'] and
                        v['algorithm'] == r['algorithm'] and v['scenario_id'] == 'normal')
        change = None
        if r['found'] and baseline['found'] and baseline['total_time_s'] > 0:
            change = (r['total_time_s']-baseline['total_time_s'])/baseline['total_time_s']*100
        key = (r['graph_id'], r['scenario_id'], r['query_id'], r['algorithm'])
        scenario.append({'scenario_id': r['scenario_id'], 'algorithm': r['algorithm'],
                         'total_time_s': r['total_time_s'], 'total_distance_m': r['total_distance_m'],
                         'time_change_pct': change, 'median_ms': time_index[key]['median_ms'],
                         'expanded_nodes': r['expanded_nodes']})
    return scale, speedup, scenario


def run(args):
    config_path = ROOT/'config/experiment_config.json'
    cfg = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else dict(CONFIG)
    require(cfg == CONFIG, '实验参数与任务书 V1.0 不同，请先统一任务书和程序，不单独修改参数')
    if args.quick:
        require(args.mode == 'demo', '--quick 只适用于示例，正式参数固定')
        cfg.update(warmups=1, pilot_calls=3, rounds=4, target_batch_s=.001, max_batch=20)
    backend = importlib.import_module('examples.demo_backend' if args.mode == 'demo' else 'src.team_api')
    data_root = ROOT / 'data'
    if args.mode == 'official':
        required = [ROOT/'src/data_loader.py', ROOT/'src/algorithms.py']
        required += [data_root/g/n for g in (['city40'] if args.scope == 'scenario' else
                     ['city40','grid100','grid400','grid900','grid1600'])
                     for n in ('nodes.csv','roads.csv','scenarios.json','manifest.json')]
        if args.scope == 'all':
            required.append(data_root/'queries.csv')
        missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
        if missing:
            print('正式材料尚未齐备；未运行实验，也未生成正式结果。\n缺少：\n' + '\n'.join(missing))
            return 2
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    parent = 'demo_results' if args.mode == 'demo' else ('checks' if args.check else 'results')
    out = ROOT / parent / ('run_' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    meta = environment(args.mode, cfg, data_root)
    meta['scope'] = args.scope
    meta['run_kind'] = 'validation_only' if args.check else 'benchmark'
    dump_json(out/'environment.json', meta)
    try:
        logs = boundary_checks(backend)
        work = backend.demo_work() if args.mode == 'demo' else load_official(backend, data_root, args.scope)
        functions = {n: getattr(backend, n) for n in ('dijkstra','astar')}
        # 必须先验证所有正式查询，再开始任何计时。
        for w in work:
            w['expected'] = {n: checked_call(fn, w['graph'], w['start'], w['goal']) for n, fn in functions.items()}
            d, a = (w['expected'][n] for n in ('dijkstra','astar'))
            require(d.found == a.found and (not d.found or close(d.total_time_s,a.total_time_s)), '两算法最优成本不一致')
            if w['experiment_id'] == 'scenario':
                require(d.found, '展示情景须保持起终点可达')
            logs.append({k:w[k] for k in ('graph_id','scenario_id','query_id') } | {'passed':True})
        if args.mode == 'official':
            city = [w for w in work if w['graph_id'] == 'city40']
            baseline = next(w for w in city if w['scenario_id'] == 'normal')['expected']['dijkstra']
            scenarios = json.loads((data_root/'city40/scenarios.json').read_text(encoding='utf-8'))
            check_city_scenarios(scenarios, baseline)
            require(all(w['expected']['dijkstra'].total_time_s >= baseline.total_time_s-1e-6 for w in city),
                    '降速或删边后最优时间反而下降')
        dump_json(out/'validation.json', {'passed':True,'checks':logs})
        if args.check:
            meta['status'] = 'validated_only'
            dump_json(out/'environment.json', meta)
            print(f'核验通过，未计时。核验记录：{out}')
            return 0
        qrows=[]; raw=[]; summaries=[]
        for i,w in enumerate(work,1):
            print(f"[{i}/{len(work)}] {w['graph_id']} {w['scenario_id']} {w['query_id']}",flush=True)
            base = {k:w[k] for k in ('experiment_id','graph_id','scenario_id','query_id')}
            rr, ss = benchmark_pair(w['graph'], w['start'], w['goal'], functions, w['expected'], cfg)
            raw.extend(base | r for r in rr)
            summaries.extend({k:w[k] for k in ('graph_id','scenario_id','query_id')} | r for r in ss)
            for name,r in w['expected'].items():
                qrows.append(base | {'data_version':w['data_version'],'start':w['start'],'goal':w['goal'],
                    'algorithm':name,'found':r.found,'path_json':json.dumps(r.path,ensure_ascii=False),
                    'road_ids_json':json.dumps(r.road_ids,ensure_ascii=False),'total_distance_m':r.total_distance_m,
                    'total_time_s':r.total_time_s,'expanded_nodes':r.expanded_nodes})
            # 保存已完成进度；status 未完成时这些文件不能用于论文。
            for name, records in [('query_results',qrows),('timing_raw',raw),('timing_summary',summaries)]:
                write_csv(out/(name+'.csv'),SCHEMAS[name],records)
        scale,speedup,scenario = aggregate(qrows,summaries)
        for name, records in [('scale_summary',scale),('speedup_summary',speedup),('scenario_summary',scenario)]:
            write_csv(out/(name+'.csv'),SCHEMAS[name],records)
        meta.update(status='completed',query_algorithm_rows=len(qrows),raw_timing_rows=len(raw),
                    completed_at_utc=datetime.now(timezone.utc).isoformat())
        # 复核输入与源代码没有在计时过程中变化。
        after = environment(args.mode,cfg,data_root)
        require(meta['data_sha256'] == after['data_sha256'] and meta['source_sha256'] == after['source_sha256'],
                '运行期间输入或代码发生变化，结果不可作为正式完成记录')
        dump_json(out/'environment.json',meta)
        print(f'完成：{out}\n' + ('仅为示例演练，不能作为论文实验结果。' if args.mode=='demo' else '请将整个本次运行文件夹交给成员四及组长。'))
        return 0
    except Exception as exc:
        meta.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        dump_json(out/'environment.json',meta)
        dump_json(out/'failure.json',{'error':meta['error'],'completed_checks':locals().get('logs',[])})
        print(f'已停止：{meta["error"]}\n排查记录：{out}',file=sys.stderr)
        return 1


def main():
    ap=argparse.ArgumentParser(description='成员三实验程序：默认正式全量；示例结果单独保存。')
    ap.add_argument('--mode',choices=['official','demo'],default='official')
    ap.add_argument('--scope',choices=['all','scenario'],default='all',help='scenario 先试跑六个情景组合；all 全量86组合')
    ap.add_argument('--quick',action='store_true',help='仅示例可用，缩短计时验证流程')
    ap.add_argument('--check',action='store_true',help='仅正确性核验，不做计时')
    sys.exit(run(ap.parse_args()))


if __name__=='__main__':
    main()
