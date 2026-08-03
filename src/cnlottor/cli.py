from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from cnlottor.analysis_engine import AnalysisService
from cnlottor.core import DEFAULT_REGISTRY, SQLiteDrawStore
from cnlottor.data_engine import DataChart500Provider, DataSyncService, import_legacy_csv

ROOT = Path(__file__).resolve().parents[2]
MODULES = {
    "tensorflow": ROOT / "modules" / "predict_tensorflow",
    "pytorch": ROOT / "modules" / "predict_pytorch",
    "kl8": ROOT / "modules" / "kl8_analyzer",
}
DEFAULT_DATABASE = ROOT / "data" / "cnlottor.db"


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


def cmd_init_db(args: argparse.Namespace) -> int:
    store = _store(args.database)
    print(store.database)
    return 0


def cmd_import_legacy(args: argparse.Namespace) -> int:
    spec = DEFAULT_REGISTRY.get(args.lottery)
    draws = import_legacy_csv(spec, args.csv)
    stored = _store(args.database).upsert_draws(spec, draws)
    print(json.dumps({"lottery": spec.code, "imported": len(draws), "stored": stored}, ensure_ascii=False))
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    report = DataSyncService(
        _store(args.database),
        DataChart500Provider(),
    ).sync(
        args.lottery,
        start_issue=args.start_issue,
        end_issue=args.end_issue,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, default=str))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    spec = DEFAULT_REGISTRY.get(args.lottery)
    draws = _store(args.database).load_draws(spec.code, ascending=True)
    if not draws:
        raise SystemExit(f"No stored draws found for {spec.code}; run sync or import-legacy first")
    service = AnalysisService()
    results = service.run_all(spec, draws) if args.strategy == "all" else [service.run(args.strategy, spec, draws)]
    print(json.dumps([asdict(result) for result in results], ensure_ascii=False, default=str, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CNlottor unified lottery research platform")
    subparsers = parser.add_subparsers(dest="action", required=True)

    list_parser = subparsers.add_parser("list", help="List legacy imported modules")
    list_parser.set_defaults(func=cmd_list)

    lotteries_parser = subparsers.add_parser("lotteries", help="List unified lottery definitions")
    lotteries_parser.set_defaults(func=cmd_lotteries)

    install_parser = subparsers.add_parser("install", help="Install a legacy module's requirements")
    install_parser.add_argument("module", choices=MODULES)
    install_parser.set_defaults(func=cmd_install)

    exec_parser = subparsers.add_parser("exec", help="Run a command inside a legacy module directory")
    exec_parser.add_argument("module", choices=MODULES)
    exec_parser.add_argument("command", nargs=argparse.REMAINDER)
    exec_parser.set_defaults(func=cmd_exec)

    init_parser = subparsers.add_parser("init-db", help="Initialize the unified SQLite database")
    init_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    init_parser.set_defaults(func=cmd_init_db)

    import_parser = subparsers.add_parser("import-legacy", help="Import an existing legacy data.csv")
    import_parser.add_argument("--lottery", required=True, choices=DEFAULT_REGISTRY.codes())
    import_parser.add_argument("--csv", required=True)
    import_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    import_parser.set_defaults(func=cmd_import_legacy)

    sync_parser = subparsers.add_parser("sync", help="Fetch and store lottery history")
    sync_parser.add_argument("--lottery", required=True, choices=DEFAULT_REGISTRY.codes())
    sync_parser.add_argument("--start-issue")
    sync_parser.add_argument("--end-issue")
    sync_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    sync_parser.set_defaults(func=cmd_sync)

    analyze_parser = subparsers.add_parser("analyze", help="Run generic analysis on stored draws")
    analyze_parser.add_argument("--lottery", required=True, choices=DEFAULT_REGISTRY.codes())
    analyze_parser.add_argument(
        "--strategy",
        default="all",
        choices=("all", "frequency", "draw-shape", "co-occurrence"),
    )
    analyze_parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    analyze_parser.set_defaults(func=cmd_analyze)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
