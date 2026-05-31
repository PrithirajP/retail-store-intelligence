import csv
import logging
from datetime import datetime
from database import SessionLocal, POSTransaction, engine, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_pos_data(csv_file_path: str):
    """Reads the POS CSV, deduplicates receipts, and populates the database."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(POSTransaction).count() > 0:
        logger.info("Database already seeded with POS transactions. Skipping.")
        db.close()
        return

    logger.info(f"Seeding POS data from {csv_file_path}...")
    
    unique_transactions = {}

    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            transaction_id = str(row.get('order_id', '')).strip()
            
            if not transaction_id or transaction_id in unique_transactions:
                continue

            try:
                dt_str = f"{row['order_date']} {row['order_time']}"
                dt_obj = datetime.strptime(dt_str, "%d-%m-%Y %H:%M:%S")
                
                txn = POSTransaction(
                    transaction_id=transaction_id,
                    store_id=row['store_id'],
                    timestamp=dt_obj,
                    basket_value_inr=float(row['total_amount'] or 0.0)
                )
                unique_transactions[transaction_id] = txn
                
            except Exception as e:
                logger.warning(f"Skipping row due to parsing error: {e}")
                continue
                
    try:
        # Bulk save all unique transactions
        db.bulk_save_objects(list(unique_transactions.values()))
        db.commit()
        logger.info(f"Successfully seeded {len(unique_transactions)} unique POS transactions.")
    except Exception as e:
        logger.error(f"Failed to save POS data: {e}")
        db.rollback()
    finally:
        db.close()