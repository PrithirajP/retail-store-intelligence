from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# SQLite is used for zero-configuration challenge deployment.
SQLALCHEMY_DATABASE_URL = "sqlite:///./store_intelligence.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ---------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------

class EventRecord(Base):
    """
    Stores the raw event stream.

    Milestone 3 upgrade:
    This table now persists the full Event Schema v1.2 payload needed for
    heatmap, queue analytics, health checks, and anomaly detection.
    """

    __tablename__ = "events"

    event_id = Column(String, primary_key=True, index=True)

    store_id = Column(String, index=True)
    camera_id = Column(String, index=True)
    visitor_id = Column(String, index=True)

    event_type = Column(String, index=True)
    timestamp = Column(DateTime, index=True)

    zone_id = Column(String, nullable=True, index=True)
    dwell_ms = Column(Integer, nullable=True)

    is_staff = Column(Boolean, default=False, index=True)
    confidence = Column(Float, nullable=True)

    # Flattened metadata fields from Event Schema v1.2
    queue_depth = Column(Integer, nullable=True)
    sku_zone = Column(String, nullable=True, index=True)
    session_seq = Column(Integer, nullable=True)


class VisitorSession(Base):
    """
    Materialized visitor journey table for fast metric and funnel queries.

    This is intentionally derived state. The raw source of truth remains
    the events table.
    """

    __tablename__ = "sessions"

    visitor_id = Column(String, primary_key=True, index=True)
    store_id = Column(String, index=True)

    entry_time = Column(DateTime, nullable=True)
    last_seen_time = Column(DateTime, nullable=True)

    billing_join_time = Column(DateTime, nullable=True)
    billing_exit_time = Column(DateTime, nullable=True)

    is_converted = Column(Boolean, default=False, index=True)
    is_staff = Column(Boolean, default=False, index=True)


class POSTransaction(Base):
    """
    Stores POS transaction records loaded from the provided CSV.
    """

    __tablename__ = "pos_transactions"

    transaction_id = Column(String, primary_key=True, index=True)
    store_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    basket_value_inr = Column(Float)

    # Prevents assigning the same POS receipt to multiple visitors.
    claimed_by_visitor_id = Column(String, nullable=True, index=True)


Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------
# Core Business Logic
# ---------------------------------------------------------------------

def correlate_billing_exit(db, visitor_id: str, store_id: str, exit_time):
    """
    Correlates a billing queue exit with an unclaimed POS transaction.

    Business rule:
    A visitor who was in the billing zone in the 5-minute window before
    a transaction timestamp counts as converted.

    Current implementation:
    When the visitor exits the billing queue, look backward 5 minutes
    for the latest unclaimed transaction in the same store.
    """

    window_start = exit_time - timedelta(minutes=5)

    transaction = (
        db.query(POSTransaction)
        .filter(
            POSTransaction.store_id == store_id,
            POSTransaction.claimed_by_visitor_id == None,
            POSTransaction.timestamp >= window_start,
            POSTransaction.timestamp <= exit_time,
        )
        .order_by(POSTransaction.timestamp.desc())
        .first()
    )

    if not transaction:
        return False

    transaction.claimed_by_visitor_id = visitor_id

    session = (
        db.query(VisitorSession)
        .filter(VisitorSession.visitor_id == visitor_id)
        .first()
    )

    if session:
        session.is_converted = True

    db.commit()

    logger.info(
        "Visitor %s correlated with POS transaction %s",
        visitor_id,
        transaction.transaction_id,
    )

    return True


# ---------------------------------------------------------------------
# FastAPI DB Dependency
# ---------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()