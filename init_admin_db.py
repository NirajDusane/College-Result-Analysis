import sqlite3
import os
from werkzeug.security import generate_password_hash

# फिक्स पाथ लॉजिक
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'college_results.db')

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # १. अ‍ॅडमिन कॉन्फिगरेशन टेबल
        cursor.execute('''CREATE TABLE IF NOT EXISTS admin_config (
            id INTEGER PRIMARY KEY,
            admin_username TEXT NOT NULL,
            admin_password_hash TEXT NOT NULL,
            secondary_password_hash TEXT NOT NULL
        )''')

        # २. अ‍ॅक्टिव्हिटी लॉग्स टेबल
        cursor.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT,
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        # डिफॉल्ट क्रेडेंशियल्स
        u = "admin_principal"
        p = generate_password_hash("Admin@123")
        s = generate_password_hash("Secure#Delete")
        
        cursor.execute("INSERT OR REPLACE INTO admin_config (id, admin_username, admin_password_hash, secondary_password_hash) VALUES (1, ?, ?, ?)", (u, p, s))
        
        conn.commit()
        conn.close()
        print(f"Success: Database created at {DB_PATH}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    init_db()