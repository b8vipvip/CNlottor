#!/usr/bin/env python3
"""Unified local launcher for the three imported lottery research modules."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = {
    "tensorflow": ROOT / "modules" / "predict_tensorflow",
    "pytorch": ROOT / "modules" / "predict_pytorch",
    "kl8": ROOT / "modules" / "kl8_analyzer",
}


def module_path(name: str) -> Path:
    path = MODULES[name]
    if not path.is_dir():
        raise SystemExit(f"Module directory is missing: {path}")
    return path


def cmd_list(_: argparse.Namespace) -> int:
    for name, path in MODULES.items():
        status = "available" if path.is_dir() else "missing"
        print(f"{name:10} {status:9} {path.relative_to(ROOT)}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    path = module_path(args.module)
    requirements = path / "requirements.txt"
    if not requirements.is_file():
        raise SystemExit(f"No requirements.txt found in {path}")
    command = [sys.executable, "-m", "pip", "install", "-r", str(requirements)]
    return subprocess.call(command, cwd=path)


def cmd_exec(args: argparse.Namespace) -> int:
    path = module_path(args.module)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Provide a command after '--'.")
    return subprocess.call(command, cwd=path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage and run the imported CNlottor modules."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    list_parser = subparsers.add_parser("list", help="List integrated modules")
    list_parser.set_defaults(func=cmd_list)

    install_parser = subparsers.add_parser(
        "install", help="Install a module's requirements"
    )
    install_parser.add_argument("module", choices=MODULES)
    install_parser.set_defaults(func=cmd_install)

    exec_parser = subparsers.add_parser(
        "exec", help="Run a command inside a module directory"
    )
    exec_parser.add_argument("module", choices=MODULES)
    exec_parser.add_argument("command", nargs=argparse.REMAINDER)
    exec_parser.set_defaults(func=cmd_exec)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
