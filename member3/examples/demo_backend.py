"""演练专用参考实现。两个入口共用搜索内核，禁止用于论文性能结论。"""
import heapq
import math
from src.contracts import Graph, Arc, SearchResult


def make_graph(coords, adj, vmax_kmh):
    return Graph(coords, adj, vmax_kmh)


def _search(g, start, goal, heuristic):
    if start not in g.coords or goal not in g.coords:
        raise ValueError('节点不存在')
    distance={start:0.0}; previous={}; closed=set(); count=0
    h=lambda n: 3.6*math.dist(g.coords[n],g.coords[goal])/g.vmax_kmh if heuristic else 0.0
    heap=[(h(start),start,0.0)]
    while heap:
        _,u,cost=heapq.heappop(heap)
        if u in closed or cost!=distance.get(u):
            continue
        count+=1
        if u==goal:
            path=[u]; roads=[]; length=0.0
            while u!=start:
                prev,edge=previous[u]
                roads.append(edge.road_id);length+=edge.length_m;path.append(prev);u=prev
            return SearchResult(True,path[::-1],roads[::-1],cost,length,count)
        closed.add(u)
        for e in g.adj[u]:
            new=cost+e.time_s
            if e.to not in closed and new<distance.get(e.to,math.inf):
                distance[e.to]=new;previous[e.to]=(u,e)
                heapq.heappush(heap,(new+h(e.to),e.to,new))
    return SearchResult(False,[],[],None,None,count)


def dijkstra(g,start,goal):
    return _search(g,start,goal,False)


def astar(g,start,goal):
    return _search(g,start,goal,True)


def demo_work():
    coords={'A':(0,0),'B':(100,0),'C':(200,0),'D':(100,100)}
    roads=[('AB','A','B',100,10),('BC','B','C',100,10),
           ('AD','A','D',150,15),('DC','D','C',150,15)]
    work=[]
    for scenario in ('normal','congested','closed'):
        adj={n:[] for n in coords}
        for rid,u,v,length,seconds in roads:
            if scenario=='closed' and rid=='BC':
                continue
            if scenario=='congested' and rid=='BC':
                seconds/=.3
            adj[u].append(Arc(v,rid,length,seconds));adj[v].append(Arc(u,rid,length,seconds))
        adj={n:sorted(es,key=lambda e:(e.to,e.road_id)) for n,es in adj.items()}
        work.append({'experiment_id':'scenario','data_version':'DEMO_ONLY',
                     'graph_id':'demo4','scenario_id':scenario,'query_id':'demo_Q01',
                     'start':'A','goal':'C','graph':Graph(coords,adj,36)})
    return work
