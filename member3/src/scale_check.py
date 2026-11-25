"""四规模数据和固定查询核验；不调用组内算法或测量性能。"""
import json
from pathlib import Path
import networkx as nx
from src.data_loader import load_graph
from src.data_checks import audit_dataset,audit_loaded,read_csv,sha256
from src.prepare import generate_queries
from src.validation import require,graph_state,nx_graph
ROOT=Path(__file__).resolve().parents[1]

def check_scales(data):
    queries=read_csv(data/'queries.csv');require(len(queries)==40,'固定查询总数应为40')
    summaries=[];references=[]
    for n in (100,400,900,1600):
        gid=f'grid{n}';folder=data/gid
        coords,roads,scenarios,manifest=audit_dataset(folder,gid)
        require(scenarios=={'normal':{'speed_factors':{},'closed_roads':[]}},'规模实验只允许normal')
        paths=[str(folder/name) for name in ('nodes.csv','roads.csv','scenarios.json')]
        graph=load_graph(*paths,'normal');audit_loaded(graph,coords,roads,scenarios,'normal')
        require(graph_state(graph)==graph_state(load_graph(*paths,'normal')),'重复加载不一致')
        qs=[q for q in queries if q['graph_id']==gid]
        require(qs==generate_queries(gid,coords),'查询与固定种子不符')
        net=nx_graph(graph)
        for q in qs:
            require(nx.has_path(net,q['start'],q['goal']),'查询不可达')
            references.append(q|{'reference':'NetworkX','reference_time_s':nx.shortest_path_length(net,q['start'],q['goal'],weight='weight')})
        summaries.append({'graph_id':gid,'nodes':len(coords),'physical_roads':len(roads),
                          'directed_arcs':net.number_of_edges(),'seed':manifest['seed'],'queries':len(qs)})
    return {'status':'scale_data_integration_passed','team_algorithm_verified':False,'performance_measured':False,
            'scope':'数据、加载、固定查询和独立最短时间参考核验','graphs':summaries,'reference_queries':references,
            'data_sha256':{str(p.relative_to(data)):sha256(p) for p in sorted(data.rglob('*')) if p.is_file()},
            'pending':['罗永军正式Dijkstra与A*','正式算法核验及情景冻结','86组合正式计时']}

def main():
    result=check_scales(ROOT/'data');out=ROOT/'integration/scale-data-check.json';out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for g in result['graphs']:print(g)
    print('四规模数据及40组查询通过，未测性能。记录：',out)
if __name__=='__main__':main()
