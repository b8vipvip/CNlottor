from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator

from .lottery_spec import LotterySpec
from .schemas import LotteryDraw


class SQLiteDrawStore:
    """Normalized SQLite storage shared by data, model, and analysis engines."""

    def __init__(self, database: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.database))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS lottery_games (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS draws (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lottery_code TEXT NOT NULL,
                    issue TEXT NOT NULL,
                    draw_date TEXT,
                    source TEXT NOT NULL,
                    UNIQUE(lottery_code, issue),
                    FOREIGN KEY(lottery_code) REFERENCES lottery_games(code)
                );

                CREATE TABLE IF NOT EXISTS draw_numbers (
                    draw_id INTEGER NOT NULL,
                    pool_code TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    number INTEGER NOT NULL,
                    PRIMARY KEY(draw_id, pool_code, position),
                    FOREIGN KEY(draw_id) REFERENCES draws(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_draws_lottery_issue
                    ON draws(lottery_code, issue);
                """
            )

    def upsert_draws(self, spec: LotterySpec, draws: Iterable[LotteryDraw]) -> int:
        stored = 0
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO lottery_games(code, name) VALUES (?, ?)
                ON CONFLICT(code) DO UPDATE SET name = excluded.name
                """,
                (spec.code, spec.name),
            )
            for draw in draws:
                connection.execute(
                    """
                    INSERT INTO draws(lottery_code, issue, draw_date, source)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(lottery_code, issue) DO UPDATE SET
                        draw_date = excluded.draw_date,
                        source = excluded.source
                    """,
                    (
                        draw.lottery_code,
                        draw.issue,
                        draw.draw_date.isoformat() if draw.draw_date else None,
                        draw.source,
                    ),
                )
                row = connection.execute(
                    "SELECT id FROM draws WHERE lottery_code = ? AND issue = ?",
                    (draw.lottery_code, draw.issue),
                ).fetchone()
                assert row is not None
                draw_id = int(row["id"])
                connection.execute("DELETE FROM draw_numbers WHERE draw_id = ?", (draw_id,))
                for pool_code, numbers in draw.pools.items():
                    connection.executemany(
                        """
                        INSERT INTO draw_numbers(draw_id, pool_code, position, number)
                        VALUES (?, ?, ?, ?)
                        """,
                        [
                            (draw_id, pool_code, position, int(number))
                            for position, number in enumerate(numbers)
                        ],
                    )
                stored += 1
        return stored

    def load_draws(
        self,
        lottery_code: str,
        *,
        limit: int | None = None,
        ascending: bool = True,
    ) -> list[LotteryDraw]:
        order = "ASC" if ascending else "DESC"
        limit_clause = " LIMIT ?" if limit is not None else ""
        params: tuple[object, ...] = (
            (lottery_code, limit) if limit is not None else (lottery_code,)
        )
        query = (
            "SELECT id, lottery_code, issue, draw_date, source "
            "FROM draws WHERE lottery_code = ? "
            f"ORDER BY issue {order}{limit_clause}"
        )
        with self.connect() as connection:
            draw_rows = connection.execute(query, params).fetchall()
            results: list[LotteryDraw] = []
            for row in draw_rows:
                number_rows = connection.execute(
                    """
                    SELECT pool_code, position, number
                    FROM draw_numbers
                    WHERE draw_id = ?
                    ORDER BY pool_code, position
                    """,
                    (row["id"],),
                ).fetchall()
                pools: dict[str, list[int]] = {}
                for number_row in number_rows:
                    pools.setdefault(number_row["pool_code"], []).append(number_row["number"])
                results.append(
                    LotteryDraw(
                        lottery_code=row["lottery_code"],
                        issue=row["issue"],
                        draw_date=(date.fromisoformat(row["draw_date"]) if row["draw_date"] else None),
                        source=row["source"],
                        pools={key: tuple(values) for key, values in pools.items()},
                    )
                )
            return results

    def latest_issue(self, lottery_code: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT issue FROM draws WHERE lottery_code = ? ORDER BY issue DESC LIMIT 1",
                (lottery_code,),
            ).fetchone()
        return str(row["issue"]) if row else None
