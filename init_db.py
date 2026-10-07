"""
Database initialization and verification utility for FlightPulse.
Safely initializes tables, constraints, indexes, views, and seed data
in any PostgreSQL environment (local or managed cloud database like Render/Neon/Supabase).
"""

import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from pipeline.database import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("flightpulse.init_db")


def init_database() -> bool:
    schema_path = BASE_DIR / "database" / "schema.sql"
    seed_path = BASE_DIR / "database" / "seed.sql"

    if not schema_path.is_file():
        logger.error("schema.sql not found at %s", schema_path)
        return False

    if not seed_path.is_file():
        logger.error("seed.sql not found at %s", seed_path)
        return False

    logger.info("Connecting to PostgreSQL...")
    try:
        conn = get_db_connection()
    except Exception as exc:
        logger.error("Could not connect to PostgreSQL: %s", exc)
        return False

    try:
        with conn.cursor() as cur:
            # Check if tables already exist
            cur.execute("SELECT to_regclass('public.flights');")
            flights_exists = cur.fetchone()[0]

            if not flights_exists:
                logger.info("Applying schema.sql to initialize database...")
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                cur.execute(schema_sql)
                logger.info("Schema applied successfully.")

                logger.info("Applying seed.sql to populate baseline benchmark records...")
                with open(seed_path, "r", encoding="utf-8") as f:
                    seed_sql = f.read()
                cur.execute(seed_sql)
                logger.info("Seed data loaded successfully.")
            else:
                logger.info("Database tables already exist. Verifying required benchmark records...")
                cur.execute("SELECT COUNT(*) FROM flights WHERE data_source IN ('FLIGHTAWARE', 'FIXTURE_REPLAY');")
                count = cur.fetchone()[0]
                if count == 0:
                    logger.info("No benchmark records found. Applying seed.sql...")
                    with open(seed_path, "r", encoding="utf-8") as f:
                        seed_sql = f.read()
                    cur.execute(seed_sql)
                    logger.info("Seed data loaded successfully.")
                else:
                    logger.info("Database is already populated with %d demo flights.", count)

        conn.commit()

        # Sanity check
        with conn.cursor() as cur:
            cur.execute("SELECT data_source, COUNT(*) FROM flights GROUP BY data_source;")
            rows = cur.fetchall()
            logger.info("Current flight counts by source:")
            for r in rows:
                logger.info("  - %s: %s records", r[0], r[1])

        return True
    except Exception as exc:
        conn.rollback()
        logger.error("Database initialization failed: %s", exc)
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
