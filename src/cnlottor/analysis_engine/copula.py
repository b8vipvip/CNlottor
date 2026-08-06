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
    variance_epsilon: float = 1e-10


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
                    vector.extend(
                        1.0 if value == candidate else 0.0
                        for candidate in range(pool.minimum, pool.maximum + 1)
                    )
            else:
                chosen = set(numbers)
                vector.extend(
                    1.0 if candidate in chosen else 0.0
                    for candidate in range(pool.minimum, pool.maximum + 1)
                )
        return vector

    @staticmethod
    def _decode(spec: LotterySpec, row):
        pools = {}
        offset = 0
        for pool in spec.pools:
            if pool.ordered:
                values = []
                for _ in range(pool.draw_count):
                    part = row[offset : offset + pool.pool_size]
                    values.append(pool.minimum + int(np.argmax(part)))
                    offset += pool.pool_size
                pools[pool.code] = tuple(values)
            else:
                part = row[offset : offset + pool.pool_size]
                indices = np.argpartition(part, -pool.draw_count)[-pool.draw_count :]
                pools[pool.code] = tuple(
                    sorted(pool.minimum + int(index) for index in indices)
                )
                offset += pool.pool_size
        return pools

    def generate(
        self,
        spec: LotterySpec,
        draws: Sequence[LotteryDraw],
        samples: int | None = None,
    ):
        if np is None:
            raise RuntimeError("NumPy is required for Copula analysis")
        if len(draws) < self.config.min_draws:
            raise ValueError(f"at least {self.config.min_draws} draws are required")

        matrix = np.asarray([self._encode(spec, draw) for draw in draws], dtype=float)
        marginals = np.clip(matrix.mean(axis=0), 1e-4, 1 - 1e-4)
        variances = matrix.var(axis=0)
        active_mask = variances > self.config.variance_epsilon
        active_indices = np.flatnonzero(active_mask)
        constant_indices = np.flatnonzero(~active_mask)
        if active_indices.size == 0:
            raise ValueError("all Copula features are constant in the selected history")

        active_matrix = matrix[:, active_indices]
        if active_matrix.shape[1] == 1:
            correlation = np.ones((1, 1), dtype=float)
        else:
            correlation = np.corrcoef(active_matrix, rowvar=False)
            correlation = np.nan_to_num(
                correlation,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )
        correlation = (
            (1 - self.config.shrinkage) * correlation
            + self.config.shrinkage * np.eye(correlation.shape[0])
        )
        eigenvalues, eigenvectors = np.linalg.eigh(
            (correlation + correlation.T) / 2
        )
        correlation = (
            eigenvectors * np.clip(eigenvalues, 1e-6, None)
        ) @ eigenvectors.T

        full_mean = np.log(marginals / (1 - marginals))
        active_mean = full_mean[active_indices]
        requested = max(1, int(samples or self.config.samples))
        rng = np.random.default_rng(self.config.seed)
        latent_active = rng.multivariate_normal(
            active_mean,
            correlation,
            size=max(requested * 5, requested),
        )
        if latent_active.ndim == 1:
            latent_active = latent_active.reshape(1, -1)

        candidates = []
        seen = set()
        for active_row in latent_active:
            row = full_mean.copy()
            row[active_indices] = active_row
            pools = self._decode(spec, row)
            key = tuple((code, tuple(values)) for code, values in sorted(pools.items()))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(pools)
            if len(candidates) == requested:
                break

        # Degenerate histories may not provide enough unique samples. Return a
        # stable list length while clearly reporting the unique count.
        if not candidates:
            candidates.append(self._decode(spec, full_mean))
        unique_candidates = len(candidates)
        while len(candidates) < requested:
            candidates.append(dict(candidates[len(candidates) % unique_candidates]))

        return candidates, {
            "draws": len(draws),
            "dimensions": int(matrix.shape[1]),
            "active_dimensions": int(active_indices.size),
            "constant_dimensions": int(constant_indices.size),
            "unique_candidates": unique_candidates,
            "marginal_min": float(marginals.min()),
            "marginal_max": float(marginals.max()),
        }

    def analyze(self, spec: LotterySpec, draws: Sequence[LotteryDraw]) -> AnalysisResult:
        candidates, diagnostics = self.generate(spec, draws)
        return AnalysisResult(
            spec.code,
            self.name,
            {"diagnostics": diagnostics, "candidates": candidates},
        )
