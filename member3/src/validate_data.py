"""兼容首次city40交付与规模补充；不改原始数据和清单。"""
import argparse
import json
from pathlib import Path

def validate_data(nodes_path, roads_path, scenarios_path, manifest_path=None, *, verbose=True):
    paths=[Path(p) for p in (nodes_path,roads_path,scenarios_path)]
    candidate=Path(manifest_path) if manifest_path else paths[0].parent/'manifest.json'
    manifest=json.loads(candidate.read_text(encoding='utf-8-sig')) if candidate.is_file() else {}
    if str(manifest.get('graph_id','')).startswith('grid'):
        from src.scale_validate_data import validate_data as validator
    else:
        from src.city40_validate_data import validate_data as validator
    return validator(*paths,manifest_path=Path(manifest_path) if manifest_path else None,verbose=verbose)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--nodes',type=Path,default=Path('data/city40/nodes.csv'))
    p.add_argument('--roads',type=Path,default=Path('data/city40/roads.csv'))
    p.add_argument('--scenarios',type=Path,default=Path('data/city40/scenarios.json'))
    p.add_argument('--manifest',type=Path)
    a=p.parse_args();validate_data(a.nodes,a.roads,a.scenarios,a.manifest)
