import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from database import SessionLocal, POSTransaction


logger = logging.getLogger(__name__)


SUPPORTED_DATE_FORMATS = [
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
]


def _clean_string(value) -> Optional[str]:
    if value is None:
        return None

    cleaned = str(value).strip()

    if cleaned == "":
        return None

    return cleaned


def _parse_float(value) -> Optional[float]:
    """
    Parse amount values safely.

    Supports normal numeric strings and strings containing commas or currency marks.
    """

    cleaned = _clean_string(value)

    if cleaned is None:
        return None

    cleaned = (
        cleaned.replace(",", "")
        .replace("₹", "")
        .replace("INR", "")
        .strip()
    )

    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_timestamp_from_official_schema(row: dict) -> Optional[datetime]:
    """
    Official challenge schema:

    transaction_id, store_id, timestamp, basket_value_inr
    """

    raw_timestamp = _clean_string(row.get("timestamp"))

    if raw_timestamp is None:
        return None

    normalized = raw_timestamp.replace("Z", "")

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            return datetime.strptime(raw_timestamp, fmt)
        except ValueError:
            continue

    return None


def _parse_timestamp_from_uploaded_schema(row: dict) -> Optional[datetime]:
    """
    Uploaded/current POS schema:

    order_id, order_date, order_time, store_id, product_id, brand_name, total_amount
    """

    order_date = _clean_string(row.get("order_date"))
    order_time = _clean_string(row.get("order_time"))

    if order_date is None or order_time is None:
        return None

    raw_timestamp = f"{order_date} {order_time}"

    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            return datetime.strptime(raw_timestamp, fmt)
        except ValueError:
            continue

    return None


def _normalize_pos_row(row: dict) -> Optional[dict]:
    """
    Normalize either supported POS schema into the internal POSTransaction fields.

    Internal fields:
    - transaction_id
    - store_id
    - timestamp
    - basket_value_inr
    """

    # Official schema
    if row.get("transaction_id") is not None:
        transaction_id = _clean_string(row.get("transaction_id"))
        store_id = _clean_string(row.get("store_id"))
        timestamp = _parse_timestamp_from_official_schema(row)
        basket_value = _parse_float(row.get("basket_value_inr"))

    # Uploaded/current schema
    elif row.get("order_id") is not None:
        transaction_id = _clean_string(row.get("order_id"))
        store_id = _clean_string(row.get("store_id"))
        timestamp = _parse_timestamp_from_uploaded_schema(row)
        basket_value = _parse_float(row.get("total_amount"))

    else:
        return None

    if transaction_id is None:
        return None

    if store_id is None:
        return None

    if timestamp is None:
        return None

    if basket_value is None:
        return None

    return {
        "transaction_id": transaction_id,
        "store_id": store_id,
        "timestamp": timestamp,
        "basket_value_inr": basket_value,
    }


def _transaction_exists(db, transaction_id: str) -> bool:
    existing = (
        db.query(POSTransaction)
        .filter(POSTransaction.transaction_id == transaction_id)
        .first()
    )

    return existing is not None


def seed_pos_data(csv_path: str) -> dict:
    """
    Seed POS transactions from a CSV file.

    Supports two schemas:

    1. Official challenge schema:
       transaction_id, store_id, timestamp, basket_value_inr

    2. Uploaded/current dataset schema:
       order_id, order_date, order_time, store_id, product_id, brand_name, total_amount

    Returns a summary dictionary for tests and logging.
    """

    path = Path(csv_path)

    summary = {
        "file": str(path),
        "rows_seen": 0,
        "inserted_count": 0,
        "duplicate_count": 0,
        "skipped_count": 0,
        "status": "success",
    }

    if not path.exists():
        logger.warning("POS CSV file not found: %s", csv_path)
        summary["status"] = "file_missing"
        return summary

    db = SessionLocal()
    seen_transaction_ids = set()

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)

            for row_number, row in enumerate(reader, start=2):
                summary["rows_seen"] += 1

                normalized = _normalize_pos_row(row)

                if normalized is None:
                    logger.warning(
                        "Skipping malformed POS row at line %s: %s",
                        row_number,
                        row,
                    )
                    summary["skipped_count"] += 1
                    continue

                transaction_id = normalized["transaction_id"]

                if transaction_id in seen_transaction_ids:
                    summary["duplicate_count"] += 1
                    continue

                seen_transaction_ids.add(transaction_id)

                if _transaction_exists(db, transaction_id):
                    summary["duplicate_count"] += 1
                    continue

                transaction = POSTransaction(
                    transaction_id=transaction_id,
                    store_id=normalized["store_id"],
                    timestamp=normalized["timestamp"],
                    basket_value_inr=normalized["basket_value_inr"],
                )

                db.add(transaction)
                summary["inserted_count"] += 1

        db.commit()
        logger.info(
            "Seeded POS data from %s: inserted=%s duplicates=%s skipped=%s",
            csv_path,
            summary["inserted_count"],
            summary["duplicate_count"],
            summary["skipped_count"],
        )

        return summary

    except Exception as exc:
        db.rollback()
        logger.error("Failed to seed POS data from %s: %s", csv_path, exc)
        summary["status"] = "error"
        summary["error"] = str(exc)
        return summary

    finally:
        db.close()