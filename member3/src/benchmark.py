import math
import statistics
import time
from src.validation import require, signature, graph_state


def calibrate_batch(t_seconds, cfg):
    return min(cfg['max_batch'], max(1, math.ceil(cfg['target_batch_s'] / max(t_seconds, 1e-9))))


def benchmark_pair(g, start, goal, functions, expected, cfg):
    before = graph_state(g)

    def timed(fn, calls):
        begin = time.perf_counter_ns()
        for _ in range(calls):
            last = fn(g, start, goal)
        elapsed = time.perf_counter_ns() - begin
        return elapsed, last

    for name, fn in functions.items():
        for _ in range(cfg['warmups']):
            require(signature(fn(g, start, goal)) == signature(expected[name]), '预热结果不稳定')
    pilot = [timed(fn, cfg['pilot_calls'])[0] / cfg['pilot_calls'] / 1e9 for fn in functions.values()]
    batch = calibrate_batch(min(pilot), cfg)
    raw = []
    names = list(functions)
    for round_id in range(1, cfg['rounds'] + 1):
        order = names if round_id % 2 else names[::-1]
        for name in order:
            elapsed, last = timed(functions[name], batch)
            # 在计时之外比较返回值；不把逐次断言的开销计入时间。
            require(signature(last) == signature(expected[name]), '计时末次结果与核验结果不同')
            require(graph_state(g) == before, '计时期间算法修改了 Graph')
            raw.append({'algorithm': name, 'round': round_id, 'batch_size': batch,
                        'elapsed_ns': elapsed, 'per_call_ms': elapsed / batch / 1e6})
    summaries = []
    for name in names:
        values = [r['per_call_ms'] for r in raw if r['algorithm'] == name]
        q = statistics.quantiles(values, method='inclusive')
        summaries.append({'algorithm': name, 'median_ms': statistics.median(values),
                          'p25_ms': q[0], 'p75_ms': q[2], 'batch_size': batch})
    return raw, summaries
