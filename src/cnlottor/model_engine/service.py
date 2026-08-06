from __future__ import annotations

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

MODEL_VERSION = "0.4.0"


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
        total = t.zeros(
            (),
            dtype=t.float32,
            device=next(iter(outputs.values())).device,
        )
        for pool in spec.pools:
            logits = outputs[pool.code]
            target = targets[pool.code]
            if pool.ordered:
                logits = logits.view(-1, pool.draw_count, pool.pool_size)
                total = total + sum(
                    t.nn.functional.cross_entropy(
                        logits[:, position, :],
                        target[:, position],
                    )
                    for position in range(pool.draw_count)
                )
            else:
                total = total + t.nn.functional.binary_cross_entropy_with_logits(
                    logits,
                    target,
                )
        return total

    @staticmethod
    def _spec_payload(spec: LotterySpec) -> dict:
        return {
            "code": spec.code,
            "name": spec.name,
            "pools": [asdict(pool) for pool in spec.pools],
        }

    @classmethod
    def _validate_checkpoint_spec(cls, spec: LotterySpec, payload: dict) -> None:
        stored = payload.get("spec")
        if not isinstance(stored, dict):
            # Backward compatibility for early v0.3 checkpoints.
            return
        current_pools = cls._spec_payload(spec)["pools"]
        stored_pools = stored.get("pools")
        if stored.get("code") != spec.code or stored_pools != current_pools:
            raise ValueError(
                "model checkpoint lottery definition no longer matches the current "
                f"{spec.code} rules; retrain this lottery model"
            )

    def train(
        self,
        spec: LotterySpec,
        draws: Sequence[LotteryDraw],
        config: TrainConfig | None = None,
    ) -> TrainReport:
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
                self._loss(
                    spec,
                    model(validation_batch.inputs),
                    validation_batch.targets,
                )
                .detach()
                .cpu()
            )
        directory = self._directory(spec.code)
        checkpoint = directory / "latest.pt"
        payload = {
            "state_dict": model.state_dict(),
            "lottery_code": spec.code,
            "model_version": MODEL_VERSION,
            "config": asdict(cfg),
            "spec": self._spec_payload(spec),
        }
        t.save(payload, checkpoint)
        (directory / "latest.json").write_text(
            json.dumps(
                {
                    "checkpoint": str(checkpoint),
                    "model_version": MODEL_VERSION,
                    "train_loss": train_loss,
                    "validation_loss": validation_loss,
                    "config": asdict(cfg),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return TrainReport(
            spec.code,
            str(checkpoint),
            len(windows),
            train_loss,
            validation_loss,
            asdict(cfg),
        )

    def predict(
        self,
        spec: LotterySpec,
        draws: Sequence[LotteryDraw],
        checkpoint: str | Path | None = None,
    ) -> PredictionResult:
        t = require_torch()
        path = (
            Path(checkpoint)
            if checkpoint
            else self._directory(spec.code) / "latest.pt"
        )
        if not path.exists():
            raise FileNotFoundError(path)
        payload = t.load(path, map_location="cpu", weights_only=False)
        self._validate_checkpoint_spec(spec, payload)
        cfg = TrainConfig(**payload["config"])
        ordered = sorted(draws, key=lambda draw: draw.issue)
        if len(ordered) < cfg.window_size:
            raise ValueError("not enough draws for prediction")
        model = LotterySequenceModel(spec, cfg.hidden_size, cfg.num_layers)
        model.load_state_dict(payload["state_dict"])
        model.eval()
        history = [encode_draw(spec, draw) for draw in ordered[-cfg.window_size :]]
        inputs = t.tensor(
            [[vectorize_draw(spec, draw) for draw in history]],
            dtype=t.float32,
        )
        with t.no_grad():
            outputs = model(inputs)
        pools = {}
        scores = {}
        for pool in spec.pools:
            logits = outputs[pool.code][0]
            if pool.ordered:
                probabilities = t.softmax(
                    logits.view(pool.draw_count, pool.pool_size),
                    dim=-1,
                )
                indices = probabilities.argmax(dim=-1).tolist()
                pools[pool.code] = tuple(
                    pool.minimum + int(index) for index in indices
                )
                scores[pool.code] = tuple(
                    float(value) for value in probabilities.flatten().tolist()
                )
            else:
                probabilities = t.sigmoid(logits)
                indices = t.topk(
                    probabilities,
                    k=pool.draw_count,
                ).indices.tolist()
                pools[pool.code] = tuple(
                    sorted(pool.minimum + int(index) for index in indices)
                )
                scores[pool.code] = tuple(
                    float(value) for value in probabilities.tolist()
                )
        return PredictionResult(
            lottery_code=spec.code,
            issue=None,
            pools=pools,
            model_name="gru-multitask-pytorch",
            model_version=str(payload.get("model_version") or MODEL_VERSION),
            scores=scores,
        )
