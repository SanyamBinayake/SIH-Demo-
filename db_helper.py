import os
import psycopg2
import json

class DatabaseHelper:
    def __init__(self):
        """
        Initializes the database helper, getting the connection URL
        from environment variables.
        """
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            print("🔴 FATAL: DATABASE_URL environment variable not found!")
        self.init_db()

    def get_connection(self):
        """Establishes and returns a database connection."""
        try:
            return psycopg2.connect(self.db_url)
        except psycopg2.OperationalError as e:
            print(f"🔴 ERROR: Could not connect to the database: {e}")
            return None

    def init_db(self):
        """
        Initializes the database by creating the 'fhir_bundles' table
        if it does not already exist.
        """
        conn = self.get_connection()
        if conn is None:
            return

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fhir_bundles (
                        id SERIAL PRIMARY KEY,
                        patient_id VARCHAR(255),
                        namaste_code VARCHAR(50),
                        bundle JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
                print("✅ [INFO] Database table 'fhir_bundles' initialized successfully.")
        except Exception as e:
            print(f"🔴 ERROR: Failed to initialize database table: {e}")
        finally:
            conn.close()

    def save_bundle(self, bundle_data):
        """
        Saves a processed FHIR bundle to the database.
        It extracts key information for dedicated columns and stores
        the full bundle as a JSONB object.
        """
        conn = self.get_connection()
        if conn is None:
            return False

        try:
            # Extract key info from the first condition resource
            condition_resource = bundle_data['stored'][0]
            patient_id = condition_resource.get('subject', {}).get('reference', 'Unknown')
            namaste_code = next(
                (c.get('code') for c in condition_resource.get('code', {}).get('coding', [])
                 if 'namaste' in c.get('system', '')),
                'Unknown'
            )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO fhir_bundles (patient_id, namaste_code, bundle)
                    VALUES (%s, %s, %s);
                    """,
                    (patient_id, namaste_code, json.dumps(bundle_data))
                )
                conn.commit()
                print(f"✅ [INFO] Successfully saved bundle for patient {patient_id} to the database.")
                return True
        except Exception as e:
            conn.rollback()
            print(f"🔴 ERROR: Failed to save bundle to database: {e}")
            return False
        finally:
            conn.close()
