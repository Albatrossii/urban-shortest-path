from dataclasses import dataclass


@dataclass(frozen=True)
class Arc:
    to: str
    road_id: str
    length_m: float
    time_s: float


@dataclass
class Graph:
    coords: dict
    adj: dict
    vmax_kmh: float


@dataclass
class SearchResult:
    found: bool
    path: list
    road_ids: list
    total_time_s: float | None
    total_distance_m: float | None
    expanded_nodes: int


SCHEMAS = {
    'query_results': 'experiment_id,data_version,graph_id,scenario_id,query_id,start,goal,algorithm,found,path_json,road_ids_json,total_distance_m,total_time_s,expanded_nodes'.split(','),
    'timing_raw': 'experiment_id,graph_id,scenario_id,query_id,algorithm,round,batch_size,elapsed_ns,per_call_ms'.split(','),
    'timing_summary': 'graph_id,scenario_id,query_id,algorithm,median_ms,p25_ms,p75_ms,batch_size'.split(','),
    'scale_summary': 'graph_id,node_count,algorithm,median_query_ms,median_expanded_nodes'.split(','),
    # 以下是任务书固定表之外的辅助汇总，不更改上面四张表的列。
    'speedup_summary': 'graph_id,node_count,median_paired_speedup'.split(','),
    'scenario_summary': 'scenario_id,algorithm,total_time_s,total_distance_m,time_change_pct,median_ms,expanded_nodes'.split(','),
}

CONFIG = {'warmups': 3, 'pilot_calls': 100, 'rounds': 30,
          'target_batch_s': 0.02, 'max_batch': 10000,
          'data_seed': 20261124, 'query_seed': 20261125,
          'rel_tol': 1e-9, 'abs_tol': 1e-6}
