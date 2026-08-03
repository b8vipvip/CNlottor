# CNlottor

CNlottor 正在把 KittenCN 的三个彩票研究项目重构成一个统一平台：

- `data_engine`：负责数据获取、解析、校验和存储；
- `model_engine`：负责通用数据编码、训练、模型管理和预测；
- `analysis_engine`：负责统计分析、规则挖掘、Copula、候选生成和回测；
- `core`：统一定义彩票规则、开奖记录和跨引擎数据协议。

项目仅用于编程、数据分析和机器学习研究，不构成投资或中奖承诺。

## 当前重构状态

第一阶段已经建立新的统一基础：

- 支持双色球、大乐透、排列三、七星彩、福彩3D、快乐8六种彩票规则；
- 区分无序不重复号码池与有序可重复数字池；
- 使用统一 `LotteryDraw` 数据模型；
- 使用 SQLite 规范化保存开奖记录及号码位置；
- 从原 TensorFlow 项目迁移 DataChart 数据抓取和解析能力；
- 支持导入旧项目的 `data.csv`；
- 模型层提供多标签和按位置分类两种统一编码；
- 分析层已泛化频率、和值/跨度/奇偶和共现分析；
- 原三个项目暂时保留在 `modules/`，用于迁移期间的行为对照。

## 新目录结构

```text
CNlottor/
├── src/cnlottor/
│   ├── core/
│   ├── data_engine/
│   ├── model_engine/
│   ├── analysis_engine/
│   └── cli.py
├── configs/lotteries/
├── modules/                     # 迁移期间保留的三个上游项目
├── data/
├── tests/
├── cnlottor_cli.py
└── pyproject.toml
```

## 安装

安装统一平台和在线数据依赖：

```bash
python -m pip install -e ".[data,yaml]"
```

## 统一命令

查看支持的彩票：

```bash
cnlottor lotteries
# 或
python cnlottor_cli.py lotteries
```

初始化统一数据库：

```bash
cnlottor init-db
```

从旧模块 CSV 导入数据：

```bash
cnlottor import-legacy \
  --lottery ssq \
  --csv modules/predict_tensorflow/data/ssq/data.csv
```

在线同步数据：

```bash
cnlottor sync --lottery pls
cnlottor sync --lottery kl8 --start-issue 2025001 --end-issue 2025100
```

运行通用分析：

```bash
cnlottor analyze --lottery ssq --strategy all
cnlottor analyze --lottery pls --strategy frequency
```

## 旧模块兼容入口

迁移完成前仍可运行旧项目：

```bash
python cnlottor_cli.py list
python cnlottor_cli.py install pytorch
python cnlottor_cli.py exec tensorflow -- python scripts/get_data.py --help
python cnlottor_cli.py exec pytorch -- python scripts/train_model.py --help
python cnlottor_cli.py exec kl8 -- python scripts/get_data.py --help
```

## 下一阶段

接下来会将 PyTorch 项目的 Transformer/LSTM 训练器迁入 `model_engine`，使其只读取统一 SQLite 数据；随后参数化迁移规则挖掘、特征增强、Copula 和滚动回测，删除其中写死的 `80选20` 假设。

## 许可证

本仓库包含 GPL-3.0 和 MIT 上游代码。迁移期间继续保留全部上游版权、许可证和来源记录，详情见 `THIRD_PARTY_NOTICES.md`、`SOURCES.md` 及各模块原始文件。
