# CNlottor

CNlottor 是一个统一的彩票数据研究平台，由三个 KittenCN 上游项目重构而来。平台将数据获取、PyTorch 训练预测、统计分析、规则挖掘、Gaussian Copula 候选生成、滚动回测和客户端界面整合为同一套数据协议。

> 本项目仅用于编程、统计与机器学习研究。彩票开奖结果具有随机性，任何模型、规则和回测结果都不构成中奖或收益承诺。

## 支持的彩票

- 双色球 `ssq`
- 大乐透 `dlt`
- 排列三 `pls`
- 乐彩7星/七星彩 `qxc`
- 福彩3D `sd`
- 快乐8 `kl8`

平台根据彩票结构自动选择处理方式：

- 双色球、大乐透、快乐8使用无序集合、多标签输出和不重复号码校验；
- 排列三、福彩3D、七星彩使用有序位置分类，保留位置和重复数字。

## 架构

```text
src/cnlottor/
├── core/              # 彩票规则、统一开奖记录、SQLite 数据仓库
├── data_engine/       # 抓取、解析、标准化、校验与同步
├── model_engine/      # 通用 PyTorch GRU、多任务输出头、训练与预测
├── analysis_engine/   # 统计、规则、Copula、候选生成和滚动回测
├── api/               # FastAPI 服务
└── cli.py             # 统一命令行

clients/cnlottor_app/  # Flutter Windows / Android 客户端
modules/               # 保留的三个上游项目，用于来源追踪和行为对照
```

更详细的设计见 `docs/ARCHITECTURE.md`。

## 安装服务端

推荐 Python 3.11。

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

Linux/macOS：

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

## 常用命令

查看彩票定义：

```bash
cnlottor lotteries
```

初始化数据库并同步全部彩票：

```bash
cnlottor init-db
cnlottor sync --lottery all
```

也可以导入上游项目已有的 CSV：

```bash
cnlottor import-legacy \
  --lottery ssq \
  --csv modules/predict_tensorflow/data/ssq/data.csv
```

运行全部分析：

```bash
cnlottor analyze --lottery all --strategy all
```

单独运行规则或 Copula：

```bash
cnlottor analyze --lottery ssq --strategy rules
cnlottor analyze --lottery pls --strategy copula
```

训练与预测：

```bash
cnlottor train --lottery ssq --epochs 20 --window-size 12
cnlottor predict --lottery ssq
```

六种彩票依次训练：

```bash
cnlottor train --lottery all --epochs 20
```

滚动回测并与随机选号基线比较：

```bash
cnlottor backtest --lottery all --window 60
```

## 启动 API 服务

```bash
cnlottor serve --host 0.0.0.0 --port 8000
```

或：

```bash
cnlottor-server
```

主要接口：

```text
GET  /health
GET  /lotteries
GET  /draws/{lottery_code}
POST /sync/{lottery_code}
GET  /analysis/{lottery_code}?strategy=frequency|draw-shape|co-occurrence|rules|copula
POST /train/{lottery_code}
GET  /predict/{lottery_code}
GET  /backtest/{lottery_code}
```

## Windows 客户端

GitHub Actions 的 `CNlottor Client Build` 工作流会生成 `CNlottor-Windows.zip`。解压后运行客户端可执行文件，默认连接：

```text
http://127.0.0.1:8000
```

先在本机启动 Python 服务端即可。`tools/windows/start_server.ps1` 可以自动创建虚拟环境、安装依赖并启动服务。

## Android 客户端

同一工作流会生成 `CNlottor-Android-APK`。Android 客户端是 API 客户端，不在手机内训练 PyTorch 模型。服务端可运行在：

- 同一局域网中的 Windows 电脑；
- VPS 或云服务器；
- Android 模拟器可访问的开发机地址。

在客户端顶部填写服务端地址，例如：

```text
http://192.168.1.20:8000
```

生产部署建议使用 HTTPS，不要把训练接口直接暴露到不可信公网。

## 自动化验证

仓库包含三类 GitHub Actions：

- `CNlottor Backend CI`：Windows、Ubuntu 后端安装、CLI、API和分析测试；
- `CNlottor PyTorch CI`：CPU PyTorch 训练、保存、加载和预测测试；
- `CNlottor Client Build`：Flutter analyze/test，并构建 Android APK 和 Windows ZIP。

高级分析测试会覆盖全部六种彩票；PyTorch 专项测试同时覆盖无序集合型和有序数字型彩票。

## 旧模块兼容入口

重构期间仍可运行上游模块：

```bash
python cnlottor_cli.py list
python cnlottor_cli.py exec tensorflow -- python scripts/get_data.py --help
python cnlottor_cli.py exec pytorch -- python scripts/train_model.py --help
python cnlottor_cli.py exec kl8 -- python scripts/get_data.py --help
```

新代码不再依赖这些旧入口。它们主要用于来源追踪、许可证保留和结果对照。

## 许可证

仓库包含 GPL-3.0 和 MIT 上游代码。请保留 `THIRD_PARTY_NOTICES.md`、`SOURCES.md`、`LICENSES/` 以及各模块中的原始版权和许可证文件。
