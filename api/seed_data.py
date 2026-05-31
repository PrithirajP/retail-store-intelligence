import csv
import logging
from datetime import datetime
from database import SessionLocal, POSTransaction, engine, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_pos_data(csv_file_path: str):
    """Reads the POS CSV and populates the database."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Skip if already seeded
    if db.query(POSTransaction).count() > 0:
        logger.info("Database already seeded with POS transactions. Skipping.")
        db.close()
        return

    logger.info(f"Seeding POS data from {csv_file_path}...")
    
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            try:
                # Parse "10-04-2026" and "16:55:36" into a datetime object
                dt_str = f"{row['order_date']} {row['order_time']}"
                dt_obj = datetime.strptime(dt_str, "%d-%m-%Y %H:%M:%S")
                
                # Create the transaction record
                txn = POSTransaction(
                    transaction_id=row['order_id'],
                    store_id=row['store_id'],
                    timestamp=dt_obj,
                    basket_value_inr=float(row['total_amount'] or 0.0)
                )
                
                # Use merge to silently overwrite duplicates instead of crashing
                db.merge(txn)
                
            except Exception as e:
                logger.warning(f"Skipping row due to parsing error: {e}")
                continue
                
        db.commit()
    
    logger.info(f"Successfully seeded {db.query(POSTransaction).count()} POS transactions.")
    db.close()

if __name__ == "__main__":
    seed_pos_data("../data/Brigade_Bangalore_10_April_26.csv")