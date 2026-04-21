import sqlite3
import os

db_path = os.path.join("app", "database", "settings.db")
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

columns_to_add = [
    "mult_long_prob",
    "mult_short_prob",
    "mult_long_pnl",
    "mult_short_pnl",
    "mult_res_long",
    "mult_res_short"
]

for col in columns_to_add:
    try:
        cursor.execute(f"ALTER TABLE strategy_settings ADD COLUMN {col} FLOAT DEFAULT 1.0")
        print(f"Added column {col}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"Column {col} already exists")
        else:
            print(f"Error adding column {col}: {e}")

conn.commit()
conn.close()
print("Migration finished")
