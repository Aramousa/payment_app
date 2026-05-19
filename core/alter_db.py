#!/usr/bin/env python
import sqlite3
import os

# Connect to database
db_path = os.path.join(os.path.dirname(__file__), 'db.sqlite3')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check current schema
    cursor.execute("PRAGMA table_info(payments_invoicerecord)")
    columns = cursor.fetchall()
    print("Current columns:")
    for col in columns:
        print(f"  {col}")

    # Check if amount is nullable
    amount_col = next((col for col in columns if col[1] == 'amount'), None)
    if amount_col:
        print(f"Amount column notnull: {amount_col[3]} (0=nullable, 1=not null)")

    # If amount is not nullable, recreate table
    if amount_col and amount_col[3] == 1:
        print("Recreating table to make amount nullable...")

        # Create new table
        cursor.execute("""
        CREATE TABLE payments_invoicerecord_new (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED,
            uploaded_by_id INTEGER REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED,
            amount BIGINT,
            invoice_date DATE,
            invoice_number VARCHAR(80),
            reference_number VARCHAR(80),
            attachment VARCHAR(100) NOT NULL,
            customer_visible_note TEXT,
            internal_note TEXT,
            customer_note TEXT,
            customer_note_updated_at DATETIME,
            customer_seen_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)

        # Copy data
        cursor.execute("""
        INSERT INTO payments_invoicerecord_new
        SELECT * FROM payments_invoicerecord
        """)

        # Drop old table
        cursor.execute("DROP TABLE payments_invoicerecord")

        # Rename new table
        cursor.execute("ALTER TABLE payments_invoicerecord_new RENAME TO payments_invoicerecord")

        print("Table recreated successfully!")

        # Update django_migrations table
        cursor.execute("""
        INSERT OR REPLACE INTO django_migrations (app, name, applied)
        VALUES ('payments', '0030_alter_invoicerecord_fields', datetime('now'))
        """)

    else:
        print("Amount column is already nullable or no migration is needed.")

    conn.commit()

except Exception as e:
    print("Error:", e)
    conn.rollback()

finally:
    conn.close()