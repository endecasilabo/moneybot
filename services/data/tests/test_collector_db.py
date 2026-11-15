from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
import unittest

from google.cloud import bigquery

from src.db import DB


class Client:
    def __init__(self, row: tuple[object, ...] | None = None) -> None:
        self.row = row
        self.statement: str | None = None
        self.params: list[bigquery.ScalarQueryParameter] | None = None
        self.inserts: list[tuple[str, list[dict[str, object]], list[bigquery.SchemaField] | None]] = []
        self.default_query_job_config = bigquery.QueryJobConfig(
            default_dataset=bigquery.DatasetReference("p", "moneybot"),
        )

    def query(self, statement: str, job_config: bigquery.QueryJobConfig | None = None) -> "Client":
        self.statement = statement
        self.params = [] if job_config is None else list(job_config.query_parameters or [])
        return self

    def result(self) -> list[tuple[object, ...]]:
        if self.row is None:
            return []
        return [self.row]

    def insert_rows(
        self,
        table: str,
        rows: list[dict[str, object]],
        selected_fields: list[bigquery.SchemaField] | None = None,
    ) -> list[dict[str, object]]:
        self.inserts.append((table, list(rows), selected_fields))
        return []


class CollectorDbTest(unittest.TestCase):
    def test_latest_filters_and_skips_null(self) -> None:
        stamp = datetime(2026, 11, 6, 20, 30, tzinfo=UTC)
        client = Client((stamp,))
        found = DB.latest(client, "trades", "ts", {"symbol": "SPY", "feed": "sip"})  # type: ignore[arg-type]
        self.assertEqual(found, stamp)
        self.assertEqual(
            client.statement,
            "SELECT max(ts) AS latest FROM trades WHERE symbol = @symbol AND feed = @feed",
        )
        self.assertEqual(
            [(param.name, param.type_, param.value) for param in client.params or []],
            [("symbol", "STRING", "SPY"), ("feed", "STRING", "sip")],
        )
        self.assertIsNone(DB.latest(Client((None,)), "trades", "ts"))  # type: ignore[arg-type]

    def test_latest_rejects_bad_identifier_and_non_string_filter(self) -> None:
        client = Client()
        with self.assertRaises(RuntimeError):
            DB.latest(client, "trades", "ts;drop")  # type: ignore[arg-type]
        with self.assertRaises(RuntimeError):
            DB.latest(client, "trades", "ts", {"qty": 1})  # type: ignore[arg-type]

    def test_insert_skips_empty_encodes_uuid_and_chunks(self) -> None:
        empty = Client()
        DB.insert(empty, "trades", [{"name": "symbol", "data_type": "string"}], [])  # type: ignore[arg-type]
        self.assertEqual(empty.inserts, [])

        client = Client()
        bar_id = UUID(int=1)
        DB.insert(  # type: ignore[arg-type]
            client,
            "trades",
            [
                {"name": "id", "data_type": "uuid"},
                {"name": "qty", "data_type": "numeric"},
            ],
            [(bar_id, Decimal("1.5"))] + [("x", Decimal("1"))] * 500,
        )
        self.assertEqual(len(client.inserts), 2)
        table, first, fields = client.inserts[0]
        self.assertEqual(table, "p.moneybot.trades")
        self.assertEqual(len(first), 500)
        self.assertEqual(first[0], {"id": str(bar_id), "qty": Decimal("1.5")})
        self.assertEqual([(field.name, field.field_type) for field in fields or []], [("id", "STRING"), ("qty", "NUMERIC")])
        self.assertEqual(len(client.inserts[1][1]), 1)

        with self.assertRaises(RuntimeError):
            DB.insert(client, "trades", [{"name": "symbol", "data_type": "blob"}], [("x",)])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
