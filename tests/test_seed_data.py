# PROMPT:
# Write pytest tests for a POS CSV seeding function that supports both the
# official challenge POS schema and the uploaded dataset schema.
#
# HUMAN CHANGES:
# Added tests for transaction_id/timestamp/basket_value_inr format and
# order_id/order_date/order_time/total_amount format. Included duplicate and
# malformed row checks to protect conversion-rate ingestion.

from pathlib import Path

import database
from database import POSTransaction
from seed_data import seed_pos_data


def test_seed_pos_data_supports_official_schema(tmp_path):
    csv_file = tmp_path / "official_pos.csv"

    csv_file.write_text(
        "\n".join(
            [
                "transaction_id,store_id,timestamp,basket_value_inr",
                "TXN_001,STORE_BLR_002,2026-04-10T10:00:00,499.50",
                "TXN_002,STORE_BLR_002,2026-04-10T10:05:00,1299.00",
            ]
        ),
        encoding="utf-8",
    )

    summary = seed_pos_data(str(csv_file))

    assert summary["status"] == "success"
    assert summary["rows_seen"] == 2
    assert summary["inserted_count"] == 2
    assert summary["duplicate_count"] == 0
    assert summary["skipped_count"] == 0

    db = database.SessionLocal()

    try:
        rows = (
            db.query(POSTransaction)
            .filter(POSTransaction.store_id == "STORE_BLR_002")
            .all()
        )

        assert len(rows) == 2

        transaction_ids = {row.transaction_id for row in rows}
        assert transaction_ids == {"TXN_001", "TXN_002"}

    finally:
        db.close()


def test_seed_pos_data_supports_uploaded_order_schema(tmp_path):
    csv_file = tmp_path / "uploaded_pos.csv"

    csv_file.write_text(
        "\n".join(
            [
                "order_id,order_date,order_time,store_id,product_id,brand_name,total_amount",
                "ORD_001,10-04-2026,16:55:36,ST1008,P001,BrandA,799.00",
                "ORD_002,10-04-2026,17:05:10,ST1008,P002,BrandB,0",
            ]
        ),
        encoding="utf-8",
    )

    summary = seed_pos_data(str(csv_file))

    assert summary["status"] == "success"
    assert summary["rows_seen"] == 2
    assert summary["inserted_count"] == 2
    assert summary["duplicate_count"] == 0
    assert summary["skipped_count"] == 0

    db = database.SessionLocal()

    try:
        rows = (
            db.query(POSTransaction)
            .filter(POSTransaction.store_id == "ST1008")
            .order_by(POSTransaction.transaction_id.asc())
            .all()
        )

        assert len(rows) == 2
        assert rows[0].transaction_id == "ORD_001"
        assert rows[0].basket_value_inr == 799.00
        assert rows[1].transaction_id == "ORD_002"
        assert rows[1].basket_value_inr == 0.0

    finally:
        db.close()


def test_seed_pos_data_skips_duplicate_transaction_ids(tmp_path):
    csv_file = tmp_path / "duplicate_pos.csv"

    csv_file.write_text(
        "\n".join(
            [
                "transaction_id,store_id,timestamp,basket_value_inr",
                "TXN_DUP,STORE_BLR_002,2026-04-10T10:00:00,499.50",
                "TXN_DUP,STORE_BLR_002,2026-04-10T10:05:00,999.00",
            ]
        ),
        encoding="utf-8",
    )

    summary = seed_pos_data(str(csv_file))

    assert summary["status"] == "success"
    assert summary["rows_seen"] == 2
    assert summary["inserted_count"] == 1
    assert summary["duplicate_count"] == 1
    assert summary["skipped_count"] == 0

    db = database.SessionLocal()

    try:
        rows = (
            db.query(POSTransaction)
            .filter(POSTransaction.transaction_id == "TXN_DUP")
            .all()
        )

        assert len(rows) == 1
        assert rows[0].basket_value_inr == 499.50

    finally:
        db.close()


def test_seed_pos_data_skips_malformed_rows(tmp_path):
    csv_file = tmp_path / "malformed_pos.csv"

    csv_file.write_text(
        "\n".join(
            [
                "transaction_id,store_id,timestamp,basket_value_inr",
                "TXN_VALID,STORE_BLR_002,2026-04-10T10:00:00,499.50",
                "TXN_BAD_DATE,STORE_BLR_002,not-a-date,999.00",
                "TXN_BAD_AMOUNT,STORE_BLR_002,2026-04-10T10:05:00,not-an-amount",
                ",STORE_BLR_002,2026-04-10T10:10:00,100.00",
            ]
        ),
        encoding="utf-8",
    )

    summary = seed_pos_data(str(csv_file))

    assert summary["status"] == "success"
    assert summary["rows_seen"] == 4
    assert summary["inserted_count"] == 1
    assert summary["duplicate_count"] == 0
    assert summary["skipped_count"] == 3

    db = database.SessionLocal()

    try:
        rows = db.query(POSTransaction).all()

        assert len(rows) == 1
        assert rows[0].transaction_id == "TXN_VALID"

    finally:
        db.close()


def test_seed_pos_data_missing_file_returns_safe_summary(tmp_path):
    missing_file = tmp_path / "missing.csv"

    assert not Path(missing_file).exists()

    summary = seed_pos_data(str(missing_file))

    assert summary["status"] == "file_missing"
    assert summary["rows_seen"] == 0
    assert summary["inserted_count"] == 0
    assert summary["duplicate_count"] == 0
    assert summary["skipped_count"] == 0