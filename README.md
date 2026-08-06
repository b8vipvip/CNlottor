# CNlottor

CNlottor 是一个统一的彩票数据研究平台，由三个 KittenCN 上游项目重构而来。平台把数据获取、PyTorch 训练预测、统计分析、规则挖掘、Gaussian Copula 候选生成、滚动回测和 Windows/Android 客户端整合到同一套数据协议中。

> 本项目仅用于编程、统计与机器学习研究。彩票开奖结果具有随机性，任何模型、规则和回测结果都不构成中奖或收益承诺。

## v0.4 支持的彩票

- 双色球 `ssq`
- 大乐透 `dlt`
- 排列三 `pls`
- 7星彩 `qxc`
- 福彩3D `sd`
- 快乐8 `kl8`

平台根据彩票结构自动选择处理方式：

- 双色球、大乐透、快乐8使用无序集合、多标签输出和不重复号码校验；
- 排列三、福彩3D使用有序位置分类，保留位置和重复数字；
- 7星彩使用六位有序基本号码和一位 `0–14` 特别号码。

## 架构

```text
src/cnlottor/
├── core/              # 彩票规则、统一开奖记录、SQLite 数据仓库
├── data_engine/       # 多来源抓取、解析、标准化、校验与同步
├── model_engine/      # 通用 PyTorch GRU、多任务输出头、训练与预测
├── analysis_engine/   # 统计、规则、Copula、候选生成和滚动回测
├── api/               # FastAPI 服务
└── cli.py             # 统一命令行

clients/cnlottor_app/  # Flutter Windows / Android 客户端
modules/               # 保留的三个上游项目，用于来源追踪和行为对照
```

数据引擎会按彩票路由数据来源：

- 中国福利彩票官方接口：双色球、福彩3D、快乐8；
- DataChart 历史页面：大乐透、排列三、7星彩。

同步器支持分页历史抓取、数据校验和 SQLite 去重更新。`sync --lottery all` 会逐种彩票执行；单个上游故障会写入失败报告，不会丢弃已经成功同步的其他彩票。

## 安装服务端

推荐 Python 3.11 或 3.12。

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[all]"
```

Linux/macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[all]"
```

## 首次使用

```powershell
cnlottor init-db --database ".\data\cnlottor.db"
cnlottor sync --lottery all --database ".\data\cnlottor.db"
```

同步报告示例：

```json
{
  "requested": 6,
  "succeeded": 6,
  "failed": 0,
  "reports": []
}
```

单种彩票同步失败时，可以单独重试：

```powershell
cnlottor sync --lottery kl8 --database ".\data\cnlottor.db"
```

## 分析、训练、预测和回测

```powershell
cnlottor analyze --lottery ssq --strategy all --database ".\data\cnlottor.db"

cnlottor train --lottery ssq --database ".\data\cnlottor.db" `
  --models ".\artifacts\models" --epochs 3 --window-size 12 --hidden-size 32

cnlottor predict --lottery ssq --database ".\data\cnlottor.db" `
  --models ".\artifacts\models"

cnlottor backtest --lottery ssq --database ".\data\cnlottor.db" --window 12
```

规则挖掘默认过滤仅出现一两次的稀疏关系，并在结果中显示实际发生次数。Copula 会自动排除零方差特征，避免少量历史数据产生无效相关矩阵警告。

## 启动 API 服务

```powershell
cnlottor serve --database ".\data\cnlottor.db" `
  --models ".\artifacts\models" --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

主要接口：

```text
GET  /health
GET  /lotteries
GET  /status/{lottery_code}
GET  /draws/{lottery_code}
POST /sync/{lottery_code}
GET  /analysis/{lottery_code}?strategy=frequency|draw-shape|co-occurrence|rules|copula
POST /train/{lottery_code}
GET  /predict/{lottery_code}
GET  /backtest/{lottery_code}?window=12
```

## Windows 与 Android 客户端

客户端顶部填写服务端地址并点击“连接”。v0.4 客户端可以直接完成：

- 查看历史期数、最新期号和模型状态；
- 同步当前彩票数据；
- 配置训练轮数、历史窗口和隐藏层大小；
- 训练模型；
- 模型预测并用号码球展示结果；
- 滚动回测；
- 频率、形态、规则和 Copula 分析。

Windows 默认连接：

```text
http://127.0.0.1:8000
```

Android 客户端需要填写电脑或服务器地址，例如：

```text
http://192.168.1.20:8000
```

Android 版是 API 客户端，PyTorch 训练仍由 Windows、Linux 或云端服务端执行。生产部署应使用 HTTPS 和身份认证，不要把训练接口直接暴露到不可信公网。

## GitHub Actions

- `CNlottor Backend CI`：Windows、Ubuntu 后端安装、CLI、API和分析测试；
- `CNlottor PyTorch CI`：CPU PyTorch 训练、保存、加载和预测测试；
- `CNlottor Client Build`：Flutter analyze/test，并构建 Android APK 和 Windows ZIP。

## 旧模块兼容入口

```bash
python cnlottor_cli.py list
python cnlottor_cli.py exec tensorflow -- python scripts/get_data.py --help
python cnlottor_cli.py exec pytorch -- python scripts/train_model.py --help
python cnlottor_cli.py exec kl8 -- python scripts/get_data.py --help
```

新平台代码不再依赖这些旧入口。它们主要用于来源追踪、许可证保留和结果对照。

## 许可证

仓库包含 GPL-3.0 和 MIT 上游代码。请保留 `THIRD_PARTY_NOTICES.md`、`SOURCES.md`、`LICENSES/` 以及各模块中的原始版权和许可证文件。
