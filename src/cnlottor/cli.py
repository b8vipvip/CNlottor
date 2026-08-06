from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from cnlottor.analysis_engine import (
    AnalysisService,
    AssociationRuleAnalyzer,
    GenericCopulaGenerator,
    RollingBacktester,
)
from cnlottor.core import DEFAULT_REGISTRY, SQLiteDrawStore
from cnlottor.data_engine import DataSyncService, build_default_provider, import_legacy_csv
from cnlottor.model_engine import TorchModelService, TrainConfig

ROOT = Path(__file__).resolve().parents[2]
MODULES = {
    "tensorflow": ROOT / "modules" / "predict_tensorflow",
    "pytorch": ROOT / "modules" / "predict_pytorch",
    "kl8": ROOT / "modules" / "kl8_analyzer",
}
DEFAULT_DATABASE = ROOT / "data" / "cnlottor.db"
DEFAULT_MODELS = ROOT / "artifacts" / "models"
LOTTERY_CHOICES = (*DEFAULT_REGISTRY.codes(), "all")


def _configure_utf8_stdio() -> None:
    """Use UTF-8 for Chinese CLI output on Windows and other legacy consoles."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, default=str, indent=2))


def _codes(value: str) -> tuple[str, ...]:
    return DEFAULT_REGISTRY.codes() if value == "all" else (DEFAULT_REGISTRY.get(value).code,)


def module_path(name: str) -> Path:
    path = MODULES[name]
    if not path.is_dir():
        raise SystemExit(f"Module directory is missing: {path}")
    return path


def cmd_list(_: argparse.Namespace) -> int:
    for name, path in MODULES.items():
        status = "available" if path.is_dir() else "missing"
        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            relative = path
        print(f"{name:10} {status:9} {relative}")
    return 0


def cmd_lotteries(_: argparse.Namespace) -> int:
    for spec in DEFAULT_REGISTRY.all():
        pools = ", ".join(
            f"{pool.code}:{pool.minimum}-{pool.maximum} x{pool.draw_count}"
            + (" ordered" if pool.ordered else " set")
            for pool in spec.pools
        )
        print(f"{spec.code:5} {spec.name:8} {pools}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    path = module_path(args.module)
    requirements = path / "requirements.txt"
    if not requirements.is_file():
        raise SystemExit(f"No requirements.txt found in {path}")
    return subprocess.call(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
        cwd=path,
    )


def cmd_exec(args: argparse.Namespace) -> int:
    path = module_path(args.module)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Provide a command after '--'.")
    return subprocess.call(command, cwd=path)


def _store(path: str) -> SQLiteDrawStore:
    return SQLiteDrawStore(Path(path))


def _history(store: SQLiteDrawStore, code: str):
    draws = store.load_draws(code, ascending=True)
    if not draws:
        raise SystemExit(f"No stored draws found for {code}; run sync or import-legacy first")
    return draws


def cmd_init_db(args: argparse.Namespace) -> int:
    store = _store(args.database)
    print(store.database)
    return 0


def cmd_import_legacy(args: argparse.Namespace) -> int:
    spec = DEFAULT_REGISTRY.get(args.lottery)
    draws = import_legacy_csv(spec, args.csv)
    stored = _store(args.database).upsert_draws(spec, draws)
    _json({"lottery": spec.code, "imported": len(draws), "stored": stored})
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    service = DataSyncService(_store(args.database), build_default_provider())
    reports: list[dict[str, object]] = []
    failures = 0
    for code in _codes(args.lottery):
        try:
            report = asdict(
                service.sync(
                    code,
                    start_issue=args.start_issue,
                    end_issue=args.end_issue,
                )
            )
            reports.append({"success": True, **report})
        except Exception as exc:
            failures += 1
            reports.append(
                {
                    "success": False,
                    "lottery_code": code,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            if args.fail_fast:
                break
    _json(
        {
            "requested": len(_codes(args.lottery)),
            "succeeded": len(reports) - failures,
            "failed": failures,
            "reports": reports,
        }
    )
    # A single-lottery failure remains a failing command. For `all`, partial
    # success is returned normally so one upstream outage does not discard the
    # data fetched for the other games.
    if failures and (args.lottery != "all" or failures == len(reports)):
        return 1
    return 0


def _analyze_one(strategy: str, spec, draws):
    if strategy == "rules":
        return AssociationRuleAnalyzer().analyze(spec, draws)
    if strategy == "copula":
        return GenericCopulaGenerator().analyze(spec, draws)
    return AnalysisService().run(strategy, spec, draws)


def cmd_analyze(args: argparse.Namespace) -> int:
    store = _store(args.database)
    output = []
    for code in _codes(args.lottery):
        spec = DEFAULT_REGISTRY.get(code)
        draws = _history(store, code)
        strategies = (
            ("frequency", "draw-shape", "co-occurrence", "rules", "copula")
            if args.strategy == "all"
            else (args.strategy,)
        )
        for strategy in strategies:
            try:
                output.append(asdict(_analyze_one(strategy, spec, draws)))
            except ValueError as exc:
                output.append(
                    {
                        "lottery_code": code,
                        "strategy": strategy,
                        "skipped": True,
                        "reason": str(exc),
                    }
                )
    _json(output)
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    store = _store(args.database)
    service = TorchModelService(args.models)
    reports = []
    config = TrainConfig(
        window_size=args.window_size,
        epochs=args.epochs,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        learning_rate=args.learning_rate,
        validation_ratio=args.validation_ratio,
        seed=args.seed,
    )
    for code in _codes(args.lottery):
        spec = DEFAULT_REGISTRY.get(code)
        reports.append(asdict(service.train(spec, _history(store, code), config)))
    _json(reports)
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    store = _store(args.database)
    service = TorchModelService(args.models)
    results = []
    for code in _codes(args.lottery):
        spec = DEFAULT_REGISTRY.get(code)
        results.append(asdict(service.predict(spec, _history(store, code))))
    _json(results)
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    store = _store(args.database)
    backtester = RollingBacktester()
    results = []
    for code in _codes(args.lottery):
        spec = DEFAULT_REGISTRY.get(code)
        results.append(
            asdict(
                backtester.run(
                    spec,
                    _history(store, code),
                    window=args.window,
                    seed=args.seed,
                )
            )
        )
    _json(results)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install CNlottor with the server extra") from exc

    from cnlottor.api.app import create_app

    uvicorn.run(
        create_app(args.database, args.models),
        host=args.host,
        port=args.port,
        reload=False,
    )
    return 0


def _add_lottery_argument(parser: argparse.ArgumentParser, *, allow_all: bool = True) -> None:
    choices = LOTTERY_CHOICES if allow_all else DEFAULT_REGISTRY.codes()
    parser.add_argument("--lottery", required=True, choices=choices)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CNlottor unified lottery research platform"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    list_parser = subparsers.add_parser("list", help="List legacy imported modules")
    list_parser.set_defaults(func=cmd_list)

    lotteries_parser = subparsers.add_parser(
        "lotteries", help="List unified lottery definitions"
    )
    lotteries_parser.set_defaults(func=cmd_lotteries)

    install_parser = subparsers.add_parser(
        "install", help="Install a legacy module's requirements"
    )
    install_parser.add_argument("module", choices=MODULES)
    install_parser.set_defaults(func=cmd_install)

    exec_parser = subparsers.add_parser(
        "exec", help="Run a command inside a legacy module directory"
    )
    exec_parser.add_argument("module", choices=MODULES)
    exec_parser.add_argument("command", nargs=argparse.REMAINDER)
    exec_parser.set_defaults(func=cmd_exec)

    init_parser = subparsers.add_parser(
        "init-db", help="Initialize the unified SQLite database"
    )
    init_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    init_parser.set_defaults(func=cmd_init_db)

    import_parser = subparsers.add_parser(
        "import-legacy", help="Import an existing legacy data.csv"
    )
    _add_lottery_argument(import_parser, allow_all=False)
    import_parser.add_argument("--csv", required=True)
    import_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    import_parser.set_defaults(func=cmd_import_legacy)

    sync_parser = subparsers.add_parser(
        "sync", help="Fetch and store lottery history"
    )
    _add_lottery_argument(sync_parser)
    sync_parser.add_argument("--start-issue")
    sync_parser.add_argument("--end-issue")
    sync_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    sync_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first provider failure",
    )
    sync_parser.set_defaults(func=cmd_sync)

    analyze_parser = subparsers.add_parser(
        "analyze", help="Run statistical, rule and Copula analysis"
    )
    _add_lottery_argument(analyze_parser)
    analyze_parser.add_argument(
        "--strategy",
        default="all",
        choices=(
            "all",
            "frequency",
            "draw-shape",
            "co-occurrence",
            "rules",
            "copula",
        ),
    )
    analyze_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    analyze_parser.set_defaults(func=cmd_analyze)

    train_parser = subparsers.add_parser(
        "train", help="Train the generic PyTorch sequence model"
    )
    _add_lottery_argument(train_parser)
    train_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    train_parser.add_argument("--models", default=str(DEFAULT_MODELS))
    train_parser.add_argument("--window-size", type=int, default=12)
    train_parser.add_argument("--epochs", type=int, default=20)
    train_parser.add_argument("--hidden-size", type=int, default=64)
    train_parser.add_argument("--num-layers", type=int, default=1)
    train_parser.add_argument("--learning-rate", type=float, default=1e-3)
    train_parser.add_argument("--validation-ratio", type=float, default=0.2)
    train_parser.add_argument("--seed", type=int, default=42)
    train_parser.set_defaults(func=cmd_train)

    predict_parser = subparsers.add_parser(
        "predict", help="Predict with the latest trained checkpoint"
    )
    _add_lottery_argument(predict_parser)
    predict_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    predict_parser.add_argument("--models", default=str(DEFAULT_MODELS))
    predict_parser.set_defaults(func=cmd_predict)

    backtest_parser = subparsers.add_parser(
        "backtest", help="Run rolling backtests against a random baseline"
    )
    _add_lottery_argument(backtest_parser)
    backtest_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    backtest_parser.add_argument("--window", type=int, default=12)
    backtest_parser.add_argument("--seed", type=int, default=42)
    backtest_parser.set_defaults(func=cmd_backtest)

    serve_parser = subparsers.add_parser(
        "serve", help="Start the FastAPI service for Windows and Android clients"
    )
    serve_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    serve_parser.add_argument("--models", default=str(DEFAULT_MODELS))
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def main() -> int:
    _configure_utf8_stdio()
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
