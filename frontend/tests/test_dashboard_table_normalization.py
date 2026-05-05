from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.dashboard_helpers import normalize_table_rows


def test_normalize_table_rows_stringifies_bool_none_and_nested_values() -> None:
    rows = [
        {
            "name": "job-1",
            "retry_eligible": True,
            "notes": None,
            "payload": {"status": "failed"},
            "count": 3,
        }
    ]

    assert normalize_table_rows(rows) == [
        {
            "name": "job-1",
            "retry_eligible": "true",
            "notes": "",
            "payload": "{'status': 'failed'}",
            "count": "3",
        }
    ]
