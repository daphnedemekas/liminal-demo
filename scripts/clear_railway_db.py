"""
Script to clear all data from the Railway database.

Usage:
    python scripts/clear_railway_db.py

This will delete all data from all tables but keep the schema intact.
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from src.database.models import Base

def clear_database(db_path: str = None):
    """Clear all data from the database."""
    if db_path is None:
        db_path = os.getenv("DATABASE_PATH", "data/liminal.db")
    
    print(f"Connecting to database at: {db_path}")
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    
    # Get all table names
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result if row[0] != 'sqlite_sequence']
    
    print(f"Found {len(tables)} tables to clear:")
    for table in tables:
        print(f"  - {table}")
    
    # Confirm
    response = input("\n⚠️  This will DELETE ALL DATA. Type 'yes' to confirm: ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return
    
    # Clear all tables
    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f"DELETE FROM {table}"))
            print(f"✓ Cleared {table}")
        
        # Reset auto-increment counters
        conn.execute(text("DELETE FROM sqlite_sequence"))
    
    print("\n✅ Database cleared successfully!")
    print("All tables are now empty but schema is intact.")

if __name__ == "__main__":
    clear_database()

