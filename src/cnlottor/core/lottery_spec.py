from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class NumberPoolSpec:
    """Rules for one independently drawn number pool."""

    code: str
    minimum: int
    maximum: int
    draw_count: int
    ordered: bool = False
    unique: bool = True
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.code or not self.code.strip():
            raise ValueError("pool code must not be empty")
        if self.minimum > self.maximum:
            raise ValueError("pool minimum cannot exceed maximum")
        if self.draw_count <= 0:
            raise ValueError("draw_count must be positive")
        if self.unique and self.draw_count > self.pool_size:
            raise ValueError("draw_count cannot exceed pool size for unique pools")

    @property
    def pool_size(self) -> int:
        return self.maximum - self.minimum + 1

    def validate_numbers(self, numbers: Iterable[int]) -> tuple[int, ...]:
        values = tuple(int(number) for number in numbers)
        if len(values) != self.draw_count:
            raise ValueError(
                f"pool {self.code!r} requires {self.draw_count} numbers, got {len(values)}"
            )
        outside = [value for value in values if not self.minimum <= value <= self.maximum]
        if outside:
            raise ValueError(
                f"pool {self.code!r} contains out-of-range numbers: {outside}"
            )
        if self.unique and len(set(values)) != len(values):
            raise ValueError(f"pool {self.code!r} does not allow duplicate numbers")
        return values

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "NumberPoolSpec":
        return cls(
            code=str(payload["code"]),
            name=str(payload["name"]) if payload.get("name") is not None else None,
            minimum=int(payload["minimum"]),
            maximum=int(payload["maximum"]),
            draw_count=int(payload["draw_count"]),
            ordered=bool(payload.get("ordered", False)),
            unique=bool(payload.get("unique", True)),
        )


@dataclass(frozen=True, slots=True)
class LotterySpec:
    """Complete structural rules for one lottery game."""

    code: str
    name: str
    pools: tuple[NumberPoolSpec, ...]
    provider_code: str | None = None
    issue_format: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized_code = self.code.strip().lower()
        if not normalized_code:
            raise ValueError("lottery code must not be empty")
        object.__setattr__(self, "code", normalized_code)
        object.__setattr__(self, "aliases", tuple(alias.strip().lower() for alias in self.aliases))
        if not self.name.strip():
            raise ValueError("lottery name must not be empty")
        if not self.pools:
            raise ValueError("a lottery must define at least one number pool")
        pool_codes = [pool.code for pool in self.pools]
        if len(pool_codes) != len(set(pool_codes)):
            raise ValueError(f"duplicate pool codes in {self.code}: {pool_codes}")

    def get_pool(self, code: str) -> NumberPoolSpec:
        for pool in self.pools:
            if pool.code == code:
                return pool
        raise KeyError(f"lottery {self.code!r} has no pool {code!r}")

    @property
    def is_ordered(self) -> bool:
        return any(pool.ordered for pool in self.pools)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LotterySpec":
        return cls(
            code=str(payload["code"]),
            name=str(payload["name"]),
            provider_code=(
                str(payload["provider_code"])
                if payload.get("provider_code") is not None
                else None
            ),
            issue_format=(
                str(payload["issue_format"])
                if payload.get("issue_format") is not None
                else None
            ),
            aliases=tuple(str(alias) for alias in payload.get("aliases", ())),
            pools=tuple(NumberPoolSpec.from_mapping(item) for item in payload["pools"]),
        )
