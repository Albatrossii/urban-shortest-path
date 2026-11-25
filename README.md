# 城市交通路网最短路径研究

图论课程五人小组作业，研究交通拥堵和道路封闭下的最短预计通行时间，并比较 Dijkstra 与 A*。

## 当前进度

- 已完成任务书和分工、成员三实验准备工具，以及曾珊珊提交的 40 节点路网模型与数据初稿。
- 40 节点数据通过结构、随机速度序列、哈希、情景加载和独立最短时间核验。
- 40 节点数据及原始加载器已接入 `member3/data/city40/`，数据端三情景联调通过。
- 正式 Dijkstra、A* 待罗永军交付；交通情景尚待组内算法复核后冻结。
- 100、400、900、1600 节点的性能实验数据尚待补齐。
- **尚未完成两种组内正式算法的性能实验；仓库中的示例和工具测试不构成论文实验结论。**

## 目录

| 目录 | 内容 |
| --- | --- |
| `docs/` | 统一任务书、最初分工、数据检查结果 |
| `member3/` | 马心悦的实验工具、表头模板、接口约定、交接说明及操作指南 |
| `submissions/zeng-shanshan/` | 曾珊珊的原始交付压缩包、Word 初稿及解压后的项目 |

原始交付保持独立，不将参考 Dijkstra 当作罗永军的正式算法。成员三演练生成的结果保存在忽略上传的 `demo_results/`。

## 成员分工

| 成员 | 职责 |
| --- | --- |
| 曾珊珊 | 路网建模、数据、情景及数据加载 |
| 罗永军 | Dijkstra、A* 实现与正确性 |
| 马心悦 | 实验设计、核验、计时、汇总及结果分析 |
| 蒋宇杰 | 图表与最终汇报 |
| 吴林岭 | 组长、论文整合、复现与提交 |

## 成员三演练

需要 Python 3.10 或以上版本。Windows 可将 `python3` 换为 `python`。

```sh
cd member3
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m src.experiments --mode demo --quick
```

这一步使用 `examples/demo_backend.py` 验证工作流程。输出标记为 `DEMO_ONLY`，不得用于论文性能比较。

收到正式材料后，按 `member3/docs/队友交接说明.txt` 接入，再依次生成查询、核验、试跑与全量运行。40 节点数据端可单独核验：

```sh
python3 -m src.scenario_check
```

该命令生成 `member3/integration/city40-data-check.json`，只使用 NetworkX 进行数据核验，不生成两算法性能记录。收到罗永军的 `src/algorithms.py` 后，先运行 `python3 -m src.experiments --scope scenario --check`，再运行 `python3 -m src.experiments --scope scenario`。当前正式入口仅会报告正式算法缺失并停止。

## 复核曾珊珊的现有数据

从仓库根目录执行：

```sh
cd submissions/zeng-shanshan/project
python3 -m src.validate_data
python3 -m src.validate_data --nodes data/sample/nodes.csv --roads data/sample/roads.csv --scenarios data/sample/scenarios.json
```

当前最短预计通行时间的独立数据核验结果：正常 193.2 秒、拥堵 205.2 秒、封路 202.8 秒；三种结果对应路径距离均为 2200 米。这些是输入数据的参考核验值，尚不能用于声明正式算法的运行效率。

## 待完成的交接

1. 曾珊珊补齐四种规模路网，扩展固定 city40 的生成及校验逻辑。
2. 罗永军用正式算法确认正常基准路线，随后共同冻结情景。
3. 40 节点数据已复制到实验工具的 `data/city40/`；实验端只读兼容两种 manifest 约定，未改原始数据及哈希。
4. 原始 `data_loader.py` 与依赖 `validate_data.py` 已一并接入。后者仍固定 city40，扩展规模数据时需泛化。
5. 正式实验完成后，按任务书保存环境、输入和代码哈希、原始计时及汇总表。

## 结果口径

主目标是预计通行时间最短，单位秒；同时记录该路线距离（米）。算法耗时单位毫秒。交通情景采用静态模拟参数，不代表真实城市实测出行时间。

本仓库用于课程协作，尚未指定开源许可证。
