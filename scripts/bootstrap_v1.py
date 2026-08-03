from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES: dict[str, str] = {
"pyproject.toml": '''[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "cnlottor"
version = "0.3.0"
description = "Unified data, PyTorch modeling, analysis, backtesting and API platform for Chinese lotteries"
readme = "README.md"
requires-python = ">=3.10"

[project.optional-dependencies]
data = ["requests>=2.31", "beautifulsoup4>=4.12", "lxml>=5.0"]
yaml = ["PyYAML>=6.0"]
analysis = ["numpy>=1.26"]
model = ["numpy>=1.26", "torch>=2.2"]
server = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "pydantic>=2.7"]
dev = ["coverage>=7.0", "httpx>=0.27"]
all = [
  "requests>=2.31", "beautifulsoup4>=4.12", "lxml>=5.0", "PyYAML>=6.0",
  "numpy>=1.26", "torch>=2.2", "fastapi>=0.115", "uvicorn[standard]>=0.30",
  "pydantic>=2.7", "httpx>=0.27"
]

[project.scripts]
cnlottor = "cnlottor.cli:main"
cnlottor-server = "cnlottor.api.server:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
''',
"src/cnlottor/model_engine/torch_backend.py": '''from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from cnlottor.core import LotterySpec
from cnlottor.model_engine.dataset import EncodedDraw

try:
    import torch
    from torch import nn
except ImportError:  # pragma: no cover
    torch = None
    nn = None


class TorchUnavailableError(RuntimeError):
    pass


def require_torch():
    if torch is None or nn is None:
        raise TorchUnavailableError("PyTorch is not installed; install CNlottor with the model extra")
    return torch


def encoded_input_size(spec: LotterySpec) -> int:
    return sum(
        pool.pool_size * pool.draw_count if pool.ordered else pool.pool_size
        for pool in spec.pools
    )


def vectorize_draw(spec: LotterySpec, draw: EncodedDraw) -> list[float]:
    values: list[float] = []
    for pool in spec.pools:
        encoded = draw.pools[pool.code]
        if not pool.ordered:
            values.extend(float(value) for value in encoded.values)
            continue
        for value in encoded.values:
            one_hot = [0.0] * pool.pool_size
            one_hot[int(value)] = 1.0
            values.extend(one_hot)
    return values


if nn is not None:
    class LotterySequenceModel(nn.Module):
        def __init__(self, spec: LotterySpec, hidden_size: int = 64, num_layers: int = 1):
            super().__init__()
            self.spec = spec
            self.input_size = encoded_input_size(spec)
            self.encoder = nn.GRU(
                input_size=self.input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
            )
            self.heads = nn.ModuleDict()
            for pool in spec.pools:
                output_size = pool.pool_size * pool.draw_count if pool.ordered else pool.pool_size
                self.heads[pool.code] = nn.Linear(hidden_size, output_size)

        def forward(self, inputs):
            encoded, _ = self.encoder(inputs)
            state = encoded[:, -1, :]
            return {code: head(state) for code, head in self.heads.items()}
else:  # pragma: no cover
    class LotterySequenceModel:
        def __init__(self, *args, **kwargs):
            require_torch()


@dataclass(frozen=True, slots=True)
class TorchBatch:
    inputs: object
    targets: Mapping[str, object]


def build_batch(spec: LotterySpec, windows: Sequence[object]) -> TorchBatch:
    t = require_torch()
    inputs = t.tensor(
        [[vectorize_draw(spec, item) for item in window.history] for window in windows],
        dtype=t.float32,
    )
    targets = {}
    for pool in spec.pools:
        values = [window.target.pools[pool.code].values for window in windows]
        targets[pool.code] = t.tensor(
            values,
            dtype=t.long if pool.ordered else t.float32,
        )
    return TorchBatch(inputs=inputs, targets=targets)
''',
"src/cnlottor/model_engine/service.py": '''from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from cnlottor.core import LotteryDraw, LotterySpec, PredictionResult
from cnlottor.model_engine.dataset import build_supervised_windows, encode_draw
from cnlottor.model_engine.torch_backend import (
    LotterySequenceModel,
    build_batch,
    require_torch,
    vectorize_draw,
)


@dataclass(frozen=True, slots=True)
class TrainConfig:
    window_size: int = 12
    epochs: int = 20
    hidden_size: int = 64
    num_layers: int = 1
    learning_rate: float = 1e-3
    validation_ratio: float = 0.2
    seed: int = 42


@dataclass(frozen=True, slots=True)
class TrainReport:
    lottery_code: str
    checkpoint: str
    examples: int
    train_loss: float
    validation_loss: float
    config: dict


class TorchModelService:
    def __init__(self, artifacts_root: str | Path = "artifacts/models") -> None:
        self.artifacts_root = Path(artifacts_root)

    def _directory(self, lottery_code: str) -> Path:
        path = self.artifacts_root / lottery_code
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _loss(spec, outputs, targets):
        t = require_torch()
        total = t.zeros((), dtype=t.float32, device=next(iter(outputs.values())).device)
        for pool in spec.pools:
            logits = outputs[pool.code]
            target = targets[pool.code]
            if pool.ordered:
                logits = logits.view(-1, pool.draw_count, pool.pool_size)
                total = total + sum(
                    t.nn.functional.cross_entropy(logits[:, position, :], target[:, position])
                    for position in range(pool.draw_count)
                )
            else:
                total = total + t.nn.functional.binary_cross_entropy_with_logits(logits, target)
        return total

    def train(self, spec: LotterySpec, draws: Sequence[LotteryDraw], config: TrainConfig | None = None) -> TrainReport:
        t = require_torch()
        cfg = config or TrainConfig()
        random.seed(cfg.seed)
        t.manual_seed(cfg.seed)
        windows = build_supervised_windows(spec, draws, cfg.window_size)
        if len(windows) < 2:
            raise ValueError("not enough draws for the requested training window")
        split = max(1, int(len(windows) * (1.0 - cfg.validation_ratio)))
        split = min(split, len(windows) - 1)
        train_batch = build_batch(spec, windows[:split])
        validation_batch = build_batch(spec, windows[split:])
        model = LotterySequenceModel(spec, cfg.hidden_size, cfg.num_layers)
        optimizer = t.optim.Adam(model.parameters(), lr=cfg.learning_rate)
        train_loss = 0.0
        model.train()
        for _ in range(cfg.epochs):
            optimizer.zero_grad()
            loss = self._loss(spec, model(train_batch.inputs), train_batch.targets)
            loss.backward()
            optimizer.step()
            train_loss = float(loss.detach().cpu())
        model.eval()
        with t.no_grad():
            validation_loss = float(
                self._loss(spec, model(validation_batch.inputs), validation_batch.targets).detach().cpu()
            )
        directory = self._directory(spec.code)
        checkpoint = directory / "latest.pt"
        payload = {
            "state_dict": model.state_dict(),
            "lottery_code": spec.code,
            "config": asdict(cfg),
            "spec": {
                "code": spec.code,
                "name": spec.name,
                "pools": [asdict(pool) for pool in spec.pools],
            },
        }
        t.save(payload, checkpoint)
        (directory / "latest.json").write_text(
            json.dumps({"checkpoint": str(checkpoint), "train_loss": train_loss, "validation_loss": validation_loss, "config": asdict(cfg)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return TrainReport(spec.code, str(checkpoint), len(windows), train_loss, validation_loss, asdict(cfg))

    def predict(self, spec: LotterySpec, draws: Sequence[LotteryDraw], checkpoint: str | Path | None = None) -> PredictionResult:
        t = require_torch()
        path = Path(checkpoint) if checkpoint else self._directory(spec.code) / "latest.pt"
        if not path.exists():
            raise FileNotFoundError(path)
        payload = t.load(path, map_location="cpu", weights_only=False)
        cfg = TrainConfig(**payload["config"])
        ordered = sorted(draws, key=lambda draw: draw.issue)
        if len(ordered) < cfg.window_size:
            raise ValueError("not enough draws for prediction")
        model = LotterySequenceModel(spec, cfg.hidden_size, cfg.num_layers)
        model.load_state_dict(payload["state_dict"])
        model.eval()
        history = [encode_draw(spec, draw) for draw in ordered[-cfg.window_size:]]
        inputs = t.tensor([[vectorize_draw(spec, draw) for draw in history]], dtype=t.float32)
        with t.no_grad():
            outputs = model(inputs)
        pools = {}
        scores = {}
        for pool in spec.pools:
            logits = outputs[pool.code][0]
            if pool.ordered:
                probabilities = t.softmax(logits.view(pool.draw_count, pool.pool_size), dim=-1)
                indices = probabilities.argmax(dim=-1).tolist()
                pools[pool.code] = tuple(pool.minimum + int(index) for index in indices)
                scores[pool.code] = tuple(float(value) for value in probabilities.flatten().tolist())
            else:
                probabilities = t.sigmoid(logits)
                indices = t.topk(probabilities, k=pool.draw_count).indices.tolist()
                pools[pool.code] = tuple(sorted(pool.minimum + int(index) for index in indices))
                scores[pool.code] = tuple(float(value) for value in probabilities.tolist())
        return PredictionResult(
            lottery_code=spec.code,
            issue=None,
            pools=pools,
            model_name="gru-multitask-pytorch",
            model_version="0.3.0",
            scores=scores,
        )
''',
"src/cnlottor/model_engine/__init__.py": '''from .contracts import LotteryPredictor, ModelTrainer
from .dataset import EncodedDraw, EncodedPool, SupervisedWindow, build_supervised_windows, encode_draw, encode_pool
from .service import TorchModelService, TrainConfig, TrainReport
from .torch_backend import TorchUnavailableError

__all__ = [
    "LotteryPredictor", "ModelTrainer", "EncodedDraw", "EncodedPool", "SupervisedWindow",
    "build_supervised_windows", "encode_draw", "encode_pool", "TorchModelService",
    "TrainConfig", "TrainReport", "TorchUnavailableError",
]
''',
"src/cnlottor/analysis_engine/rules.py": '''from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Sequence

from cnlottor.core import AnalysisResult, LotteryDraw, LotterySpec


def draw_tokens(spec: LotterySpec, draw: LotteryDraw) -> tuple[str, ...]:
    tokens = []
    for pool in spec.pools:
        numbers = draw.pools[pool.code]
        if pool.ordered:
            tokens.extend(f"{pool.code}:p{position + 1}={number}" for position, number in enumerate(numbers))
        else:
            tokens.extend(f"{pool.code}:n={number}" for number in numbers)
    return tuple(tokens)


class AssociationRuleAnalyzer:
    name = "association-rules"

    def __init__(self, min_support: float = 0.03, min_confidence: float = 0.2, limit: int = 1000):
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.limit = limit

    def analyze(self, spec: LotterySpec, draws: Sequence[LotteryDraw]) -> AnalysisResult:
        selected = list(draws)[-self.limit:]
        transactions = [set(draw_tokens(spec, draw)) for draw in selected]
        singles = Counter(token for transaction in transactions for token in transaction)
        pairs = Counter(pair for transaction in transactions for pair in combinations(sorted(transaction), 2))
        total = max(len(transactions), 1)
        rules = []
        for pair, count in pairs.items():
            support = count / total
            if support < self.min_support:
                continue
            for antecedent, consequent in (pair, pair[::-1]):
                confidence = count / singles[antecedent]
                if confidence < self.min_confidence:
                    continue
                consequent_support = singles[consequent] / total
                rules.append({
                    "antecedent": antecedent,
                    "consequent": consequent,
                    "support": support,
                    "confidence": confidence,
                    "lift": confidence / consequent_support if consequent_support else 0.0,
                })
        rules.sort(key=lambda item: (item["lift"], item["confidence"], item["support"]), reverse=True)
        return AnalysisResult(spec.code, self.name, {"transactions": len(transactions), "rules": rules[:200]})
''',
"src/cnlottor/analysis_engine/copula.py": '''from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from cnlottor.core import AnalysisResult, LotteryDraw, LotterySpec

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


@dataclass(frozen=True, slots=True)
class CopulaConfig:
    min_draws: int = 30
    shrinkage: float = 0.15
    samples: int = 20
    seed: int = 42


class GenericCopulaGenerator:
    name = "gaussian-copula"

    def __init__(self, config: CopulaConfig | None = None):
        self.config = config or CopulaConfig()

    @staticmethod
    def _encode(spec: LotterySpec, draw: LotteryDraw):
        vector = []
        for pool in spec.pools:
            numbers = draw.pools[pool.code]
            if pool.ordered:
                for value in numbers:
                    vector.extend(1.0 if value == candidate else 0.0 for candidate in range(pool.minimum, pool.maximum + 1))
            else:
                chosen = set(numbers)
                vector.extend(1.0 if candidate in chosen else 0.0 for candidate in range(pool.minimum, pool.maximum + 1))
        return vector

    def generate(self, spec: LotterySpec, draws: Sequence[LotteryDraw], samples: int | None = None):
        if np is None:
            raise RuntimeError("NumPy is required for Copula analysis")
        if len(draws) < self.config.min_draws:
            raise ValueError(f"at least {self.config.min_draws} draws are required")
        matrix = np.asarray([self._encode(spec, draw) for draw in draws], dtype=float)
        marginals = np.clip(matrix.mean(axis=0), 1e-4, 1 - 1e-4)
        correlation = np.corrcoef(matrix, rowvar=False)
        correlation = np.nan_to_num(correlation, nan=0.0, posinf=0.0, neginf=0.0)
        correlation = (1 - self.config.shrinkage) * correlation + self.config.shrinkage * np.eye(correlation.shape[0])
        eigenvalues, eigenvectors = np.linalg.eigh((correlation + correlation.T) / 2)
        correlation = (eigenvectors * np.clip(eigenvalues, 1e-6, None)) @ eigenvectors.T
        mean = np.log(marginals / (1 - marginals))
        rng = np.random.default_rng(self.config.seed)
        latent = rng.multivariate_normal(mean, correlation, size=samples or self.config.samples)
        candidates = []
        for row in latent:
            offset = 0
            pools = {}
            for pool in spec.pools:
                if pool.ordered:
                    values = []
                    for _ in range(pool.draw_count):
                        part = row[offset: offset + pool.pool_size]
                        values.append(pool.minimum + int(np.argmax(part)))
                        offset += pool.pool_size
                    pools[pool.code] = tuple(values)
                else:
                    part = row[offset: offset + pool.pool_size]
                    indices = np.argpartition(part, -pool.draw_count)[-pool.draw_count:]
                    pools[pool.code] = tuple(sorted(pool.minimum + int(index) for index in indices))
                    offset += pool.pool_size
            candidates.append(pools)
        return candidates, {
            "draws": len(draws),
            "dimensions": int(matrix.shape[1]),
            "marginal_min": float(marginals.min()),
            "marginal_max": float(marginals.max()),
        }

    def analyze(self, spec: LotterySpec, draws: Sequence[LotteryDraw]) -> AnalysisResult:
        candidates, diagnostics = self.generate(spec, draws)
        return AnalysisResult(spec.code, self.name, {"diagnostics": diagnostics, "candidates": candidates})
''',
"src/cnlottor/analysis_engine/backtest.py": '''from __future__ import annotations

import random
from collections import Counter
from typing import Sequence

from cnlottor.core import BacktestResult, LotteryDraw, LotterySpec


def score_prediction(spec: LotterySpec, predicted, actual: LotteryDraw):
    scores = {}
    for pool in spec.pools:
        expected = tuple(predicted[pool.code])
        observed = actual.pools[pool.code]
        scores[pool.code] = (
            sum(left == right for left, right in zip(expected, observed))
            if pool.ordered
            else len(set(expected) & set(observed))
        )
    return scores


def frequency_prediction(spec: LotterySpec, draws: Sequence[LotteryDraw]):
    result = {}
    for pool in spec.pools:
        if pool.ordered:
            values = []
            for position in range(pool.draw_count):
                counter = Counter(draw.pools[pool.code][position] for draw in draws)
                values.append(counter.most_common(1)[0][0])
            result[pool.code] = tuple(values)
        else:
            counter = Counter(number for draw in draws for number in draw.pools[pool.code])
            result[pool.code] = tuple(sorted(number for number, _ in counter.most_common(pool.draw_count)))
    return result


def random_prediction(spec: LotterySpec, rng: random.Random):
    result = {}
    for pool in spec.pools:
        universe = list(range(pool.minimum, pool.maximum + 1))
        if pool.ordered and not pool.unique:
            result[pool.code] = tuple(rng.choice(universe) for _ in range(pool.draw_count))
        else:
            result[pool.code] = tuple(sorted(rng.sample(universe, pool.draw_count)))
    return result


class RollingBacktester:
    def run(self, spec: LotterySpec, draws: Sequence[LotteryDraw], window: int = 60, seed: int = 42) -> BacktestResult:
        ordered = sorted(draws, key=lambda draw: draw.issue)
        if len(ordered) <= window:
            raise ValueError("not enough draws for rolling backtest")
        rng = random.Random(seed)
        totals = {pool.code: 0 for pool in spec.pools}
        random_totals = {pool.code: 0 for pool in spec.pools}
        exact = 0
        random_exact = 0
        evaluated = 0
        for index in range(window, len(ordered)):
            history = ordered[index - window:index]
            actual = ordered[index]
            prediction = frequency_prediction(spec, history)
            baseline = random_prediction(spec, rng)
            scores = score_prediction(spec, prediction, actual)
            random_scores = score_prediction(spec, baseline, actual)
            for code in totals:
                totals[code] += scores[code]
                random_totals[code] += random_scores[code]
            exact += int(all(scores[pool.code] == pool.draw_count for pool in spec.pools))
            random_exact += int(all(random_scores[pool.code] == pool.draw_count for pool in spec.pools))
            evaluated += 1
        metrics = {f"mean_hits_{code}": value / evaluated for code, value in totals.items()}
        metrics.update({f"random_mean_hits_{code}": value / evaluated for code, value in random_totals.items()})
        metrics["exact_rate"] = exact / evaluated
        metrics["random_exact_rate"] = random_exact / evaluated
        return BacktestResult(spec.code, "rolling-frequency-vs-random", evaluated, metrics)
''',
"src/cnlottor/analysis_engine/__init__.py": '''from .backtest import RollingBacktester, frequency_prediction, random_prediction, score_prediction
from .contracts import AnalysisStrategy
from .copula import CopulaConfig, GenericCopulaGenerator
from .rules import AssociationRuleAnalyzer
from .service import AnalysisService
from .statistics import CoOccurrenceAnalysis, DrawShapeAnalysis, FrequencyAnalysis

__all__ = [
    "AnalysisStrategy", "AnalysisService", "FrequencyAnalysis", "DrawShapeAnalysis",
    "CoOccurrenceAnalysis", "AssociationRuleAnalyzer", "CopulaConfig", "GenericCopulaGenerator",
    "RollingBacktester", "frequency_prediction", "random_prediction", "score_prediction",
]
''',
"src/cnlottor/api/__init__.py": '''from .app import app, create_app

__all__ = ["app", "create_app"]
''',
"src/cnlottor/api/app.py": '''from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from cnlottor.analysis_engine import AssociationRuleAnalyzer, GenericCopulaGenerator, RollingBacktester
from cnlottor.analysis_engine.service import AnalysisService
from cnlottor.core import DEFAULT_REGISTRY, SQLiteDrawStore
from cnlottor.data_engine import DataChart500Provider, DataSyncService
from cnlottor.model_engine import TorchModelService, TrainConfig, TorchUnavailableError


class TrainRequest(BaseModel):
    window_size: int = Field(default=12, ge=1)
    epochs: int = Field(default=20, ge=1, le=500)
    hidden_size: int = Field(default=64, ge=4, le=1024)
    learning_rate: float = Field(default=1e-3, gt=0)


def create_app(database: str | Path | None = None, artifacts_root: str | Path | None = None) -> FastAPI:
    db = Path(database or os.getenv("CNLOTTOR_DATABASE", "data/cnlottor.db"))
    models = Path(artifacts_root or os.getenv("CNLOTTOR_MODELS", "artifacts/models"))
    store = SQLiteDrawStore(db)
    model_service = TorchModelService(models)
    application = FastAPI(title="CNlottor API", version="0.3.0")
    application.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @application.get("/health")
    def health():
        return {"status": "ok", "version": "0.3.0", "database": str(db)}

    @application.get("/lotteries")
    def lotteries():
        return [
            {"code": spec.code, "name": spec.name, "pools": [asdict(pool) for pool in spec.pools]}
            for spec in DEFAULT_REGISTRY.all()
        ]

    @application.get("/draws/{lottery_code}")
    def draws(lottery_code: str, limit: int = Query(default=100, ge=1, le=5000)):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        return [asdict(draw) for draw in store.load_draws(spec.code, limit=limit, ascending=False)]

    @application.post("/sync/{lottery_code}")
    def sync(lottery_code: str):
        try:
            return asdict(DataSyncService(store, DataChart500Provider()).sync(lottery_code))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @application.get("/analysis/{lottery_code}")
    def analysis(lottery_code: str, strategy: str = "frequency"):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        if not history:
            raise HTTPException(status_code=404, detail="no draws stored")
        try:
            if strategy == "rules":
                result = AssociationRuleAnalyzer().analyze(spec, history)
            elif strategy == "copula":
                result = GenericCopulaGenerator().analyze(spec, history)
            else:
                result = AnalysisService().run(strategy, spec, history)
            return asdict(result)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.post("/train/{lottery_code}")
    def train(lottery_code: str, request: TrainRequest):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        try:
            report = model_service.train(spec, history, TrainConfig(
                window_size=request.window_size,
                epochs=request.epochs,
                hidden_size=request.hidden_size,
                learning_rate=request.learning_rate,
            ))
            return asdict(report)
        except TorchUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.get("/predict/{lottery_code}")
    def predict(lottery_code: str):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        try:
            return asdict(model_service.predict(spec, history))
        except TorchUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="model checkpoint not found") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.get("/backtest/{lottery_code}")
    def backtest(lottery_code: str, window: int = Query(default=60, ge=5)):
        spec = DEFAULT_REGISTRY.get(lottery_code)
        history = store.load_draws(spec.code, ascending=True)
        try:
            return asdict(RollingBacktester().run(spec, history, window=window))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return application


app = create_app()
''',
"src/cnlottor/api/server.py": '''from __future__ import annotations

import os


def main() -> int:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install CNlottor with the server extra") from exc
    uvicorn.run(
        "cnlottor.api.app:app",
        host=os.getenv("CNLOTTOR_HOST", "0.0.0.0"),
        port=int(os.getenv("CNLOTTOR_PORT", "8000")),
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
"tests/test_rules_copula_backtest.py": '''import unittest

from cnlottor.analysis_engine import AssociationRuleAnalyzer, CopulaConfig, GenericCopulaGenerator, RollingBacktester
from cnlottor.core import DEFAULT_REGISTRY, LotteryDraw


def draws_for(code, count=80):
    spec = DEFAULT_REGISTRY.get(code)
    result = []
    for index in range(count):
        pools = {}
        for pool in spec.pools:
            if pool.ordered:
                pools[pool.code] = tuple((index + position) % pool.pool_size + pool.minimum for position in range(pool.draw_count))
            else:
                start = index % max(1, pool.pool_size - pool.draw_count + 1)
                pools[pool.code] = tuple(range(pool.minimum + start, pool.minimum + start + pool.draw_count))
        result.append(LotteryDraw(code, f"{index + 1:04d}", pools, source="test"))
    return result


class AdvancedAnalysisTests(unittest.TestCase):
    def test_rules_support_ordered_and_set_lotteries(self):
        for code in ("ssq", "pls"):
            result = AssociationRuleAnalyzer(min_support=0.01, min_confidence=0.01).analyze(DEFAULT_REGISTRY.get(code), draws_for(code))
            self.assertEqual(result.strategy, "association-rules")
            self.assertTrue(result.payload["rules"])

    def test_copula_generates_valid_candidates(self):
        try:
            generator = GenericCopulaGenerator(CopulaConfig(min_draws=10, samples=3))
        except Exception as exc:
            self.skipTest(str(exc))
        for code in ("ssq", "pls"):
            spec = DEFAULT_REGISTRY.get(code)
            candidates, _ = generator.generate(spec, draws_for(code, 40))
            self.assertEqual(len(candidates), 3)
            for candidate in candidates:
                for pool in spec.pools:
                    pool.validate_numbers(candidate[pool.code])

    def test_backtest_includes_random_baseline(self):
        result = RollingBacktester().run(DEFAULT_REGISTRY.get("pls"), draws_for("pls"), window=20)
        self.assertGreater(result.evaluated_draws, 0)
        self.assertIn("random_exact_rate", result.metrics)


if __name__ == "__main__":
    unittest.main()
''',
"tests/test_api.py": '''import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

from cnlottor.api.app import create_app


@unittest.skipIf(TestClient is None, "FastAPI test dependencies are not installed")
class ApiTests(unittest.TestCase):
    def test_health_and_lotteries(self):
        with tempfile.TemporaryDirectory() as directory:
            client = TestClient(create_app(Path(directory) / "test.db", Path(directory) / "models"))
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.get("/lotteries")
            self.assertEqual(response.status_code, 200)
            self.assertEqual({item["code"] for item in response.json()}, {"ssq", "dlt", "pls", "qxc", "sd", "kl8"})


if __name__ == "__main__":
    unittest.main()
''',
"tests/test_torch_model_service.py": '''import tempfile
import unittest
from pathlib import Path

from cnlottor.core import DEFAULT_REGISTRY, LotteryDraw

try:
    from cnlottor.model_engine import TorchModelService, TrainConfig
    import torch
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "PyTorch is not installed")
class TorchModelServiceTests(unittest.TestCase):
    def test_train_and_predict_ordered_lottery(self):
        spec = DEFAULT_REGISTRY.get("pls")
        draws = [
            LotteryDraw("pls", f"{index + 1:04d}", {"digits": (index % 10, (index + 1) % 10, (index + 2) % 10)}, source="test")
            for index in range(24)
        ]
        with tempfile.TemporaryDirectory() as directory:
            service = TorchModelService(Path(directory))
            report = service.train(spec, draws, TrainConfig(window_size=4, epochs=1, hidden_size=8))
            self.assertTrue(Path(report.checkpoint).exists())
            prediction = service.predict(spec, draws)
            spec.get_pool("digits").validate_numbers(prediction.pools["digits"])


if __name__ == "__main__":
    unittest.main()
''',
".github/workflows/ci.yml": '''name: CNlottor Backend CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  backend:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.11"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - name: Install backend
        run: python -m pip install -e ".[data,yaml,analysis,server,dev]"
      - name: Verify CLI
        run: |
          cnlottor lotteries
          python cnlottor_cli.py list
      - name: Run tests
        run: python -m unittest discover -s tests -v
      - name: Compile unified source
        run: python -m compileall -q src
      - name: Compile legacy modules except known invalid upstream script
        if: runner.os == 'Linux'
        shell: bash
        run: |
          python -m compileall -q modules/predict_tensorflow
          python -m compileall -q modules/predict_pytorch
          find modules/kl8_analyzer -name '*.py' ! -path '*/kl8_analysis_plus.py' -print0 | xargs -0 python -m py_compile
''',
".github/workflows/model-ci.yml": '''name: CNlottor PyTorch CI

on:
  pull_request:
    paths: ["src/cnlottor/model_engine/**", "tests/test_torch_model_service.py", "pyproject.toml"]
  push:
    branches: [main]
    paths: ["src/cnlottor/model_engine/**", "tests/test_torch_model_service.py", "pyproject.toml"]

permissions:
  contents: read

jobs:
  pytorch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install -e ".[model]"
      - run: python -m unittest tests.test_torch_model_service -v
''',
"clients/cnlottor_app/pubspec.yaml": '''name: cnlottor_app
description: CNlottor Windows and Android client
publish_to: none
version: 0.3.0+1

environment:
  sdk: ">=3.3.0 <4.0.0"

dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.2

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^5.0.0

flutter:
  uses-material-design: true
''',
"clients/cnlottor_app/lib/main.dart": '''import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() => runApp(const CNlottorApp());

class CNlottorApp extends StatelessWidget {
  const CNlottorApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CNlottor',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _urlController = TextEditingController(text: 'http://127.0.0.1:8000');
  List<dynamic> lotteries = [];
  String? selected;
  String output = '请先连接 CNlottor 服务端';
  bool loading = false;

  Future<dynamic> _get(String path) async {
    final base = _urlController.text.trim().replaceAll(RegExp(r'/+$'), '');
    final response = await http.get(Uri.parse('$base$path')).timeout(const Duration(seconds: 30));
    if (response.statusCode >= 400) throw Exception('${response.statusCode}: ${response.body}');
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<void> connect() async {
    setState(() => loading = true);
    try {
      final health = await _get('/health');
      final games = await _get('/lotteries') as List<dynamic>;
      setState(() {
        lotteries = games;
        selected = games.isEmpty ? null : games.first['code'] as String;
        output = const JsonEncoder.withIndent('  ').convert(health);
      });
    } catch (error) {
      setState(() => output = '连接失败：$error');
    } finally {
      setState(() => loading = false);
    }
  }

  Future<void> runAnalysis(String strategy) async {
    if (selected == null) return;
    setState(() => loading = true);
    try {
      final value = await _get('/analysis/$selected?strategy=$strategy');
      setState(() => output = const JsonEncoder.withIndent('  ').convert(value));
    } catch (error) {
      setState(() => output = '请求失败：$error');
    } finally {
      setState(() => loading = false);
    }
  }

  Future<void> predict() async {
    if (selected == null) return;
    setState(() => loading = true);
    try {
      final value = await _get('/predict/$selected');
      setState(() => output = const JsonEncoder.withIndent('  ').convert(value));
    } catch (error) {
      setState(() => output = '请求失败：$error');
    } finally {
      setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('CNlottor 数据研究平台')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          Row(children: [
            Expanded(child: TextField(controller: _urlController, decoration: const InputDecoration(labelText: '服务端地址', border: OutlineInputBorder()))),
            const SizedBox(width: 12),
            FilledButton(onPressed: loading ? null : connect, child: const Text('连接')),
          ]),
          const SizedBox(height: 16),
          Row(children: [
            Expanded(child: DropdownButtonFormField<String>(
              value: selected,
              decoration: const InputDecoration(labelText: '彩票类型', border: OutlineInputBorder()),
              items: lotteries.map((item) => DropdownMenuItem(value: item['code'] as String, child: Text('${item['name']} (${item['code']})'))).toList(),
              onChanged: (value) => setState(() => selected = value),
            )),
          ]),
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            OutlinedButton(onPressed: loading ? null : () => runAnalysis('frequency'), child: const Text('频率分析')),
            OutlinedButton(onPressed: loading ? null : () => runAnalysis('draw-shape'), child: const Text('形态分析')),
            OutlinedButton(onPressed: loading ? null : () => runAnalysis('rules'), child: const Text('规则挖掘')),
            OutlinedButton(onPressed: loading ? null : () => runAnalysis('copula'), child: const Text('Copula候选')),
            FilledButton.tonal(onPressed: loading ? null : predict, child: const Text('模型预测')),
          ]),
          const SizedBox(height: 12),
          if (loading) const LinearProgressIndicator(),
          const SizedBox(height: 8),
          Expanded(child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: Theme.of(context).colorScheme.surfaceContainerHighest, borderRadius: BorderRadius.circular(12)),
            child: SingleChildScrollView(child: SelectableText(output)),
          )),
        ]),
      ),
    );
  }
}
''',
"clients/cnlottor_app/test/widget_test.dart": '''import 'package:flutter_test/flutter_test.dart';
import 'package:cnlottor_app/main.dart';

void main() {
  testWidgets('renders CNlottor client', (tester) async {
    await tester.pumpWidget(const CNlottorApp());
    expect(find.text('CNlottor 数据研究平台'), findsOneWidget);
    expect(find.text('连接'), findsOneWidget);
  });
}
''',
".github/workflows/client-build.yml": '''name: CNlottor Client Build

on:
  pull_request:
    paths: ["clients/cnlottor_app/**", ".github/workflows/client-build.yml"]
  push:
    branches: [main]
    paths: ["clients/cnlottor_app/**", ".github/workflows/client-build.yml"]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  android:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
      - uses: subosito/flutter-action@v2
        with:
          channel: stable
          cache: true
      - working-directory: clients/cnlottor_app
        run: flutter pub get
      - working-directory: clients/cnlottor_app
        run: flutter analyze
      - working-directory: clients/cnlottor_app
        run: flutter test
      - working-directory: clients/cnlottor_app
        run: flutter build apk --release
      - uses: actions/upload-artifact@v4
        with:
          name: CNlottor-Android-APK
          path: clients/cnlottor_app/build/app/outputs/flutter-apk/app-release.apk

  windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with:
          channel: stable
          cache: true
      - run: flutter config --enable-windows-desktop
      - working-directory: clients/cnlottor_app
        run: flutter pub get
      - working-directory: clients/cnlottor_app
        run: flutter analyze
      - working-directory: clients/cnlottor_app
        run: flutter test
      - working-directory: clients/cnlottor_app
        run: flutter build windows --release
      - shell: pwsh
        run: Compress-Archive -Path clients/cnlottor_app/build/windows/x64/runner/Release/* -DestinationPath CNlottor-Windows.zip
      - uses: actions/upload-artifact@v4
        with:
          name: CNlottor-Windows
          path: CNlottor-Windows.zip
''',
"docs/ARCHITECTURE.md": '''# CNlottor architecture

CNlottor v0.3 separates the system into five layers:

1. `core`: lottery rules, normalized draw schemas and SQLite storage.
2. `data_engine`: providers, parsing, validation and synchronization.
3. `model_engine`: generic PyTorch sequence encoder and lottery-aware output heads.
4. `analysis_engine`: statistics, position-aware rules, Gaussian Copula candidates and rolling backtests.
5. `api` plus Flutter clients: service boundary for Windows and Android.

The Android application is intentionally a client. PyTorch training remains on the Python service because native Android is not a reliable environment for the full training stack. Windows can run the service locally; Android connects over LAN or HTTPS.
''',
}


def write_files() -> None:
    for relative, content in FILES.items():
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    manifest = ROOT / "clients/cnlottor_app/android/app/src/main/AndroidManifest.xml"
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8")
        if "android.permission.INTERNET" not in text:
            text = text.replace("<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\">", "<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\">\n    <uses-permission android:name=\"android.permission.INTERNET\" />")
        text = text.replace("<application", "<application android:usesCleartextTraffic=\"true\"", 1)
        manifest.write_text(text, encoding="utf-8", newline="\n")

    for disposable in (ROOT / "scripts/bootstrap_v1.py", ROOT / ".github/workflows/develop-v1.yml"):
        if disposable.exists():
            disposable.unlink()


if __name__ == "__main__":
    write_files()
