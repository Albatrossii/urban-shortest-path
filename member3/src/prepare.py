"""生成空表头及固定查询；不会生成正式路网、道路情景或替代队友算法。"""
import argparse
import json
import math
import random
from pathlib import Path
from src.contracts import CONFIG, SCHEMAS
from src.data_checks import read_csv, sha256
from src.experiments import write_csv, dump_json
from src.validation import require

ROOT=Path(__file__).resolve().parents[1]


def generate_queries(graph_id,coords):
    seed=20261125+len(coords)
    rng=random.Random(seed);nodes=sorted(coords);side=math.isqrt(len(coords));seen=set();out=[]
    require(side*side==len(coords),'查询生成仅适用于约定的方形网格')
    while len(out)<10:
        start=rng.choice(nodes);goal=rng.choice(nodes)
        if start==goal or (start,goal) in seen:
            continue
        distance=sum(abs(a-b) for a,b in zip(coords[start],coords[goal]))/200
        if distance<side-1:
            continue
        seen.add((start,goal))
        out.append({'graph_id':graph_id,'query_id':f'Q{len(out)+1:02d}','start':start,'goal':goal})
    return out


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--queries',action='store_true',help='收到四种规模 nodes.csv 后生成固定查询')
    args=ap.parse_args()
    if args.queries:
        output=ROOT/'data/queries.csv'
        require(not output.exists(),'queries.csv 已存在；先核对再自行移动旧版本，避免覆盖冻结查询')
        queries=[];sources={}
        for n in (100,400,900,1600):
            gid=f'grid{n}';p=ROOT/f'data/{gid}/nodes.csv'
            rows=read_csv(p);coords={r['node_id']:(float(r['x_m']),float(r['y_m'])) for r in rows}
            require(len(coords)==n,'节点数不符合规模')
            queries.extend(generate_queries(gid,coords));sources[gid]=sha256(p)
        write_csv(output,['graph_id','query_id','start','goal'],queries)
        dump_json(ROOT/'data/queries_provenance.json',{'rule':'任务书 V1.0：独立随机源、长距离、不重复有序对',
                  'seeds':{f'grid{n}':20261125+n for n in (100,400,900,1600)},'node_files_sha256':sources})
        print('已生成 40 组固定查询：',output)
    else:
        folder=ROOT/'templates';folder.mkdir(exist_ok=True)
        for name,fields in SCHEMAS.items():
            p=folder/(name+'.csv')
            if not p.exists():
                write_csv(p,fields,[])
        for p,value in [(ROOT/'config/experiment_config.json',CONFIG),
                        (folder/'environment_template.json',{'status':'not_run','mode':'official',
                          'cpu':None,'ram_bytes':None,'python':None,'dependencies':{},'parameters':CONFIG,
                          'data_sha256':{},'source_sha256':{},'started_at_utc':None})]:
            if not p.exists():dump_json(p,value)
        print('空白表头与参数已准备；未写入任何实验数字。')


if __name__=='__main__':main()
