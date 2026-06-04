import json
from pathlib import Path


EVENT_LOG_PATH = Path("event_log.jsonl")

REQUIRED_FIELDS = {
    "event_id",
    "store_id",
    "camera_id",
    "visitor_id",
    "event_type",
    "timestamp",
    "zone_id",
    "dwell_ms",
    "is_staff",
    "confidence",
    "metadata",
}

VALID_EVENT_TYPES = {
    "ENTRY",
    "EXIT",
    "ZONE_ENTER",
    "ZONE_EXIT",
    "ZONE_DWELL",
    "BILLING_QUEUE_JOIN",
    "BILLING_QUEUE_EXIT",
    "BILLING_QUEUE_ABANDON",
    "REENTRY",
}


def main():
    if not EVENT_LOG_PATH.exists():
        raise FileNotFoundError("event_log.jsonl not found.")

    count = 0

    with EVENT_LOG_PATH.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                raise ValueError(f"Blank line found at line {line_number}")

            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_number}: {exc}")

            missing = REQUIRED_FIELDS - set(event.keys())

            if missing:
                raise ValueError(
                    f"Missing fields at line {line_number}: {sorted(missing)}"
                )

            if event["event_type"] not in VALID_EVENT_TYPES:
                raise ValueError(
                    f"Invalid event_type at line {line_number}: {event['event_type']}"
                )

            if not isinstance(event["metadata"], dict):
                raise ValueError(f"metadata must be object at line {line_number}")

            count += 1

    print(f"Valid JSONL file. Total events: {count}")


if __name__ == "__main__":
    main()