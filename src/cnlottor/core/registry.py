from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from .lottery_spec import LotterySpec, NumberPoolSpec


def _pool(
    code: str,
    minimum: int,
    maximum: int,
    draw_count: int,
    *,
    ordered: bool = False,
    unique: bool = True,
    name: str | None = None,
) -> NumberPoolSpec:
    return NumberPoolSpec(
        code=code,
        name=name,
        minimum=minimum,
        maximum=maximum,
        draw_count=draw_count,
        ordered=ordered,
        unique=unique,
    )


BUILTIN_SPECS: tuple[LotterySpec, ...] = (
    LotterySpec(
        code="ssq",
        name="双色球",
        provider_code="ssq",
        aliases=("double-color-ball",),
        pools=(
            _pool("main", 1, 33, 6, name="红球"),
            _pool("bonus", 1, 16, 1, name="蓝球"),
        ),
    ),
    LotterySpec(
        code="dlt",
        name="大乐透",
        provider_code="dlt",
        pools=(
            _pool("main", 1, 35, 5, name="前区"),
            _pool("bonus", 1, 12, 2, name="后区"),
        ),
    ),
    LotterySpec(
        code="pls",
        name="排列三",
        provider_code="pls",
        aliases=("pl3",),
        pools=(
            _pool("digits", 0, 9, 3, ordered=True, unique=False, name="开奖号码"),
        ),
    ),
    LotterySpec(
        code="qxc",
        name="七星彩",
        provider_code="qxc",
        pools=(
            _pool("digits", 0, 9, 7, ordered=True, unique=False, name="开奖号码"),
        ),
    ),
    LotterySpec(
        code="sd",
        name="福彩3D",
        provider_code="sd",
        aliases=("fc3d", "3d"),
        pools=(
            _pool("digits", 0, 9, 3, ordered=True, unique=False, name="开奖号码"),
        ),
    ),
    LotterySpec(
        code="kl8",
        name="快乐8",
        provider_code="kl8",
        aliases=("快乐8", "happy8"),
        pools=(
            _pool("main", 1, 80, 20, name="开奖号码"),
        ),
    ),
)


class LotteryRegistry:
    def __init__(self, specs: Iterable[LotterySpec] = BUILTIN_SPECS):
        self._specs: dict[str, LotterySpec] = {}
        self._aliases: dict[str, str] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: LotterySpec, *, replace: bool = False) -> None:
        if spec.code in self._specs and not replace:
            raise ValueError(f"lottery {spec.code!r} is already registered")
        self._specs[spec.code] = spec
        self._aliases[spec.code] = spec.code
        for alias in spec.aliases:
            if alias in self._aliases and self._aliases[alias] != spec.code and not replace:
                raise ValueError(f"alias {alias!r} is already registered")
            self._aliases[alias] = spec.code

    def get(self, code_or_alias: str) -> LotterySpec:
        normalized = code_or_alias.strip().lower()
        canonical = self._aliases.get(normalized)
        if canonical is None:
            raise KeyError(f"unsupported lottery: {code_or_alias}")
        return self._specs[canonical]

    def all(self) -> tuple[LotterySpec, ...]:
        return tuple(self._specs[code] for code in sorted(self._specs))

    def codes(self) -> tuple[str, ...]:
        return tuple(spec.code for spec in self.all())

    @classmethod
    def from_mappings(cls, items: Iterable[Mapping[str, object]]) -> "LotteryRegistry":
        return cls(LotterySpec.from_mapping(item) for item in items)

    @classmethod
    def from_yaml_directory(cls, directory: str | Path) -> "LotteryRegistry":
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "PyYAML is required to load external lottery definitions; "
                "install CNlottor with the 'yaml' extra"
            ) from exc

        specs: list[LotterySpec] = []
        for path in sorted(Path(directory).glob("*.yaml")):
            with path.open(encoding="utf-8") as stream:
                payload = yaml.safe_load(stream)
            specs.append(LotterySpec.from_mapping(payload))
        if not specs:
            raise ValueError(f"no lottery definitions found in {directory}")
        return cls(specs)


DEFAULT_REGISTRY = LotteryRegistry()
