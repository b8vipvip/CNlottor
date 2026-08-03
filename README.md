# CNlottor

CNlottor 将 KittenCN 的三个彩票数据研究项目聚合在一个仓库中，并提供统一的本地管理入口。项目仅用于编程、数据分析和机器学习研究，不构成投资或中奖承诺。

## 集成模块

| 模块 | 目录 | 用途 |
|---|---|---|
| TensorFlow 预测系统 | `modules/predict_tensorflow` | 双色球、大乐透、排列三、七星彩、福彩3D等历史数据与 LSTM 实验 |
| PyTorch 预测系统 | `modules/predict_pytorch` | Transformer/LSTM、训练、预测与数据 Pipeline |
| KL8 分析器 | `modules/kl8_analyzer` | 快乐8统计分析、候选组合、回测及高级算法实验 |

## 统一入口

直接使用：

```bash
python cnlottor.py list
python cnlottor.py install pytorch

python cnlottor.py exec tensorflow -- python scripts/get_data.py --help
python cnlottor.py exec tensorflow -- python scripts/train.py --help
python cnlottor.py exec tensorflow -- python scripts/predict.py --help

python cnlottor.py exec pytorch -- python scripts/get_data.py --help
python cnlottor.py exec pytorch -- python scripts/train_model.py --help
python cnlottor.py exec pytorch -- python scripts/predict.py --help

python cnlottor.py exec kl8 -- python scripts/get_data.py --help
```

也可以把根目录工具安装成命令：

```bash
python -m pip install -e .
cnlottor list
```

`exec` 命令只负责切换到对应模块目录并执行原项目命令，因此各模块仍可按照自己的 README 独立使用，避免强行混合不同框架的依赖和数据格式。

## 目录结构

```text
CNlottor/
├── cnlottor.py
├── modules/
│   ├── predict_tensorflow/
│   ├── predict_pytorch/
│   └── kl8_analyzer/
├── tests/
├── SOURCES.md
└── THIRD_PARTY_NOTICES.md
```

## 安装建议

三个上游项目使用 TensorFlow、PyTorch 和不同版本的数据科学依赖。建议为每个模块使用独立虚拟环境，避免依赖冲突。

## 许可证

本仓库是多许可证聚合项目。每个上游模块继续适用其原许可证和版权声明；详情见 `THIRD_PARTY_NOTICES.md`、`SOURCES.md` 及模块内原始文件。
