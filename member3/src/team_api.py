"""唯一需要对接队友的文件。禁止用示例后端冒充正式算法。

请曾珊珊提供 src/data_loader.py，罗永军提供 src/algorithms.py。
若队友使用字典而不是属性对象，请只在这里进行双向转换。
"""
def load_graph(nodes_path, roads_path, scenarios_path, scenario_id):
    from src.data_loader import load_graph as team_load
    return team_load(str(nodes_path), str(roads_path), str(scenarios_path), scenario_id)


def dijkstra(graph, start, goal):
    from src.algorithms import dijkstra as team_dijkstra
    return team_dijkstra(graph, start, goal)


def astar(graph, start, goal):
    from src.algorithms import astar as team_astar
    return team_astar(graph, start, goal)


def make_graph(coords, adj, vmax_kmh):
    # 核验边界用例所需；若队友要求自己的 Graph 类型，在此转换。
    from src.contracts import Graph
    return Graph(coords, adj, vmax_kmh)
