import copy
import json
import tempfile
import unittest
from pathlib import Path
from src.data_checks import audit_dataset
from src.scenario_check import ROOT, check_city


class CityIntegrationTests(unittest.TestCase):
    def test_real_submission_and_nonmutation(self):
        folder=ROOT/'data/city40'
        before={str(p):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        result=check_city(folder)
        self.assertEqual([round(r['total_time_s'],1) for r in result['scenarios']],[193.2,205.2,202.8])
        self.assertEqual([r['arc_count'] for r in result['scenarios']],[134,134,132])
        self.assertFalse(result['team_algorithm_verified'])
        self.assertFalse(result['performance_measured'])
        self.assertFalse(result['scenario_frozen'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in folder.rglob('*') if p.is_file()})

    def test_both_manifest_schemas_and_reject_corruption(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'city40';shutil.copytree(ROOT/'data/city40',folder)
            audit_dataset(folder,'city40')
            p=folder/'manifest.json';m=json.loads(p.read_text())
            m['grid_shape']=[5,8];m['units']={'distance':'m','speed':'km/h','time':'s'}
            m['files_sha256']=m.pop('sha256');p.write_text(json.dumps(m))
            audit_dataset(folder,'city40')
            (folder/'scenario_basis.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'哈希不一致'):
                audit_dataset(folder,'city40')


if __name__=='__main__':unittest.main()
