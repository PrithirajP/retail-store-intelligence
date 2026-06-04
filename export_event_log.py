import json
import sqlite3
from pathlib import Path


DB_PATH = Path("store_intelligence_from_docker.db")
OUTPUT_PATH = Path("event_log.jsonl")


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            "store_intelligence_from_docker.db not found. "
            "Run: docker cp store-api:/app/store_intelligence.db .\\store_intelligence_from_docker.db"
        )

    print(f"Using database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            event_id,
            store_id,
            camera_id,
            visitor_id,
            event_type,
            timestamp,
            zone_id,
            dwell_ms,
            is_staff,
            confidence,
            queue_depth,
            sku_zone,
            session_seq
        FROM events
        ORDER BY timestamp ASC
        """
    ).fetchall()

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            event = {
                "event_id": row["event_id"],
                "store_id": row["store_id"],
                "camera_id": row["camera_id"],
                "visitor_id": row["visitor_id"],
                "event_type": row["event_type"],
                "timestamp": row["timestamp"],
                "zone_id": row["zone_id"],
                "dwell_ms": row["dwell_ms"],
                "is_staff": bool(row["is_staff"]),
                "confidence": row["confidence"],
                "metadata": {
                    "queue_depth": row["queue_depth"],
                    "sku_zone": row["sku_zone"],
                    "session_seq": row["session_seq"],
                },
            }

            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    conn.close()

    print(f"Exported {len(rows)} events to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()