from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# Use SQLite for zero-configuration persistence
SQLALCHEMY_DATABASE_URL = "sqlite:///./store_intelligence.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- ORM Models ---

class EventRecord(Base):
    """Stores raw events to ensure idempotency."""
    __tablename__ = "events"
    event_id = Column(String, primary_key=True, index=True)
    store_id = Column(String, index=True)
    visitor_id = Column(String, index=True)
    event_type = Column(String)
    timestamp = Column(DateTime, index=True)

class VisitorSession(Base):
    """Materialized view of a visitor's journey for fast funnel/metric queries."""
    __tablename__ = "sessions"
    visitor_id = Column(String, primary_key=True, index=True)
    store_id = Column(String, index=True)
    entry_time = Column(DateTime)
    billing_exit_time = Column(DateTime, nullable=True)
    is_converted = Column(Boolean, default=False)
    is_staff = Column(Boolean, default=False)

class POSTransaction(Base):
    """Digital transaction records."""
    __tablename__ = "pos_transactions"
    transaction_id = Column(String, primary_key=True, index=True)
    store_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    basket_value_inr = Column(Float)
    claimed_by_visitor_id = Column(String, nullable=True) # Prevents double-counting

# Create all tables in the database
Base.metadata.create_all(bind=engine)

# --- Core Business Logic ---

def correlate_billing_exit(db, visitor_id: str, store_id: str, exit_time):
    """
    Finds an unclaimed POS transaction within 5 minutes prior to the visitor 
    leaving the billing queue and marks them as converted.
    """
    window_start = exit_time - timedelta(minutes=5)
    
    # Find the closest unclaimed transaction in the 5-minute window
    transaction = db.query(POSTransaction).filter(
        POSTransaction.store_id == store_id,
        POSTransaction.claimed_by_visitor_id == None,
        POSTransaction.timestamp >= window_start,
        POSTransaction.timestamp <= exit_time
    ).order_by(POSTransaction.timestamp.desc()).first()

    if transaction:
        # Claim it to prevent double counting in crowded queues
        transaction.claimed_by_visitor_id = visitor_id
        
        # Update session
        session = db.query(VisitorSession).filter(VisitorSession.visitor_id == visitor_id).first()
        if session:
            session.is_converted = True
        
        db.commit()
        logger.info(f"Visitor {visitor_id} correlated with POS transaction {transaction.transaction_id}")
        return True
    
    return False

# Dependency to get DB session in FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()