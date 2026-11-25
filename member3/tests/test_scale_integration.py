import unittest
from src.scale_check import ROOT,check_scales
from src.scenario_check import check_city
class ScaleIntegrationTests(unittest.TestCase):
    def test_four_scales_and_queries(self):
        r=check_scales(ROOT/'data')
        self.assertEqual([g['physical_roads'] for g in r['graphs']],[180,760,1740,3120])
        self.assertEqual([g['directed_arcs'] for g in r['graphs']],[360,1520,3480,6240])
        self.assertEqual(len(r['reference_queries']),40)
        self.assertFalse(r['performance_measured'])
    def test_original_city40_remains_compatible(self):
        self.assertEqual(check_city(ROOT/'data/city40')['status'],'data_integration_passed')
if __name__=='__main__':unittest.main()
