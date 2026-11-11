import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from src.db import finish_run, insert, start_run


class FakeClient:
    def __init__(self, errors: list[dict] | None = None) -> None:
        self.errors = errors or []
        self.rows: list[tuple[str, dict]] = []

    def insert_rows_json(self, table: str, rows: list[dict]) -> list[dict]:
        self.rows.extend((table, row) for row in rows)
        return self.errors


@patch.dict(os.environ, {"BQ_DATASET": "proj.moneybot_dev"})
class AppendOnlyTest(unittest.TestCase):
    def test_money_dates_and_json_are_sent_as_bigquery_json(self) -> None:
        client = FakeClient()
        insert(client, "orders", {"qty": Decimal("1.50"), "d": date(2026, 11, 6), "j": [{"a": 1}]})
        self.assertEqual(
            client.rows,
            [("proj.moneybot_dev.orders", {"qty": "1.50", "d": "2026-11-06", "j": '[{"a": 1}]'})],
        )

    def test_finishing_a_run_appends_an_event_instead_of_updating(self) -> None:
        client = FakeClient()
        run_id = start_run(client, "trade")
        finish_run(client, run_id, "trade", "ok", None)
        statuses = [(row["run_id"], row["status"]) for _, row in client.rows]
        self.assertEqual(statuses, [(run_id, "running"), (run_id, "ok")])

    def test_rejected_insert_raises_instead_of_losing_the_row(self) -> None:
        with self.assertRaises(RuntimeError):
            insert(FakeClient(errors=[{"index": 0, "errors": ["bad"]}]), "runs", {"x": 1})


if __name__ == "__main__":
    unittest.main()
