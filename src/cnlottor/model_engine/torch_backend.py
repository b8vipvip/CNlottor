from __future__ import annotations

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
