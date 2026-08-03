from __future__ import annotations

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
