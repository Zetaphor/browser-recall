import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
import threading

class Database:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Database, cls).__new__(cls)
                cls._instance._initialize_db()
            return cls._instance

    def _initialize_db(self):
        """Initialize the database connection and create tables if they don't exist."""
        self.conn = sqlite3.connect('history.db', check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        try:
            # Set WAL mode first, before any other operations
            self.conn.execute('PRAGMA journal_mode=WAL')

            # Other performance and reliability optimizations
            self.conn.execute('PRAGMA synchronous=NORMAL')  # Balance between safety and speed
            self.conn.execute('PRAGMA temp_store=MEMORY')   # Store temp tables and indices in memory
            self.conn.execute('PRAGMA cache_size=-64000')   # Use 64MB of memory for page cache
            self.conn.execute('PRAGMA foreign_keys=ON')     # Enable foreign key constraints
        except Exception as e:
            print(f"Error setting database PRAGMA options: {e}")
            # Optionally re-raise the exception if you want to halt execution
            raise

        self.cursor = self.conn.cursor()

        # Create history table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created TIMESTAMP NOT NULL,
                updated TIMESTAMP NOT NULL
            )
        ''')
        self.conn.commit()

    def add_history(self, url: str, title: str, content: str) -> int:
        """Add a new history entry."""
        now = datetime.utcnow()
        with self._lock:
            self.cursor.execute('''
                INSERT INTO history (url, title, content, created, updated)
                VALUES (?, ?, ?, ?, ?)
            ''', (url, title, content, now, now))
            self.conn.commit()
            return self.cursor.lastrowid

    def get_history(self, limit: int = 100) -> List[Dict]:
        """Get history entries, ordered by most recent first."""
        self.cursor.execute('''
            SELECT * FROM history
            ORDER BY created DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in self.cursor.fetchall()]

    def update_history(self, id: int, title: Optional[str] = None,
                      content: Optional[str] = None) -> bool:
        """Update an existing history entry."""
        update_fields = []
        values = []

        if title is not None:
            update_fields.append("title = ?")
            values.append(title)
        if content is not None:
            update_fields.append("content = ?")
            values.append(content)

        if not update_fields:
            return False

        update_fields.append("updated = ?")
        values.append(datetime.utcnow())
        values.append(id)

        with self._lock:
            self.cursor.execute(f'''
                UPDATE history
                SET {", ".join(update_fields)}
                WHERE id = ?
            ''', values)
            self.conn.commit()
            return self.cursor.rowcount > 0

    def delete_history(self, id: int) -> bool:
        """Delete a history entry."""
        with self._lock:
            self.cursor.execute('DELETE FROM history WHERE id = ?', (id,))
            self.conn.commit()
            return self.cursor.rowcount > 0

    def __del__(self):
        """Cleanup database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()