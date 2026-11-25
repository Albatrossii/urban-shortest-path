import copy
import statistics
import unittest
from examples import demo_backend as demo
from src.benchmark import benchmark_pair, calibrate_batch
from src.contracts import CONFIG, SearchResult
from src.experiments import aggregate
from src.prepare import generate_queries
from src.validation import boundary_checks, checked_call, validate_result


class HarnessTests(unittest.TestCase):
    def test_boundary_checks(self):
        self.assertEqual(len(boundary_checks(demo)),14)

    def test_detect_wrong_cost_and_closed_road(self):
        w=demo.demo_work()[0];g=w['graph'];r=demo.dijkstra(g,'A','C')
        wrong=copy.deepcopy(r);wrong.total_time_s+=1
        with self.assertRaises(ValueError):validate_result(g,'A','C',wrong)
        closed=demo.demo_work()[2]['graph']
        with self.assertRaises(ValueError):validate_result(closed,'A','C',r)

    def test_equal_cost_different_distance_is_allowed(self):
        from src.contracts import Graph,Arc
        g=Graph({'A':(0,0),'B':(1,0),'C':(2,0)},
                {'A':[Arc('B','AB',1,1),Arc('C','AC',3,2)],
                 'B':[Arc('C','BC',1,1)],'C':[]},10)
        validate_result(g,'A','C',SearchResult(True,['A','C'],['AC'],2,3,2))
        validate_result(g,'A','C',SearchResult(True,['A','B','C'],['AB','BC'],2,2,3))

    def test_batch_limits(self):
        self.assertEqual(calibrate_batch(1,CONFIG),1)
        self.assertEqual(calibrate_batch(0,CONFIG),10000)
        self.assertEqual(calibrate_batch(.001,CONFIG),20)

    def test_benchmark_rows_and_summary(self):
        w=demo.demo_work()[0];g=w['graph'];functions={'dijkstra':demo.dijkstra,'astar':demo.astar}
        expected={n:checked_call(fn,g,'A','C') for n,fn in functions.items()}
        cfg=dict(CONFIG,warmups=1,pilot_calls=2,rounds=4,target_batch_s=.0001,max_batch=2)
        raw,summary=benchmark_pair(g,'A','C',functions,expected,cfg)
        self.assertEqual(len(raw),8)
        self.assertEqual([r['algorithm'] for r in raw],['dijkstra','astar','astar','dijkstra']*2)
        for r in raw:self.assertEqual(r['per_call_ms'],r['elapsed_ns']/r['batch_size']/1e6)
        for r in summary:
            values=[x['per_call_ms'] for x in raw if x['algorithm']==r['algorithm']]
            self.assertEqual(r['median_ms'],statistics.median(values))
            self.assertEqual(r['p25_ms'],statistics.quantiles(values,method='inclusive')[0])

    def test_query_generation(self):
        coords={f'N{i:04d}':(200*(i%10),200*(i//10)) for i in range(100)}
        qs=generate_queries('grid100',coords)
        self.assertEqual(qs,generate_queries('grid100',coords));self.assertEqual(len(qs),10)
        self.assertEqual(len({(q['start'],q['goal']) for q in qs}),10)
        for q in qs:
            self.assertGreaterEqual(sum(abs(a-b) for a,b in zip(coords[q['start']],coords[q['goal']]))/200,9)

    def test_pairwise_aggregation(self):
        qs=[];ss=[]
        for i,(dt,at) in enumerate([(1,1),(100,10),(3,1)]):
            for name,t in [('dijkstra',dt),('astar',at)]:
                qs.append({'experiment_id':'scale','graph_id':'grid100','query_id':str(i),
                           'algorithm':name,'expanded_nodes':10+i})
                ss.append({'graph_id':'grid100','scenario_id':'normal','query_id':str(i),
                           'algorithm':name,'median_ms':t})
        scale,speed,_=aggregate(qs,ss)
        self.assertEqual(speed[0]['median_paired_speedup'],3)
        self.assertEqual(scale[0]['median_query_ms'],3)


if __name__=='__main__':unittest.main()
