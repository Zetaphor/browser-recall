from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import sqlite3

SQLALCHEMY_DATABASE_URL = "sqlite:///./browser_history.db"

# Create engine with custom configuration
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "timeout": 30,  # Connection timeout in seconds
        "check_same_thread": False,  # Allow multi-threaded access
    },
    # Update pool configuration for better concurrency
    pool_size=5,  # Increase pool size to handle concurrent requests
    max_overflow=10,  # Allow some overflow connections
    pool_timeout=30,  # Connection timeout from pool
    pool_recycle=3600,  # Recycle connections every hour
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Prevent unnecessary reloads
)

Base = declarative_base()

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Configure SQLite for better performance"""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()

        # Enable WAL mode for better write performance and concurrency
        cursor.execute("PRAGMA journal_mode=WAL")

        # Set page size to 4KB for better performance
        cursor.execute("PRAGMA page_size=4096")

        # Set cache size to 32MB (-32000 pages * 4KB per page = ~32MB)
        cursor.execute("PRAGMA cache_size=-32000")

        # Enable memory-mapped I/O for better performance
        cursor.execute("PRAGMA mmap_size=268435456")  # 256MB

        # Set synchronous mode to NORMAL for better write performance
        cursor.execute("PRAGMA synchronous=NORMAL")

        # Enable foreign key support
        cursor.execute("PRAGMA foreign_keys=ON")

        cursor.close()

class HistoryEntry(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True)
    url = Column(String, index=True)  # Add index for URL lookups
    title = Column(String)
    visit_time = Column(DateTime, index=True)  # Add index for time-based queries
    domain = Column(String, index=True)  # Add index for domain filtering
    markdown_content = Column(Text, nullable=True)
    last_content_update = Column(DateTime, nullable=True)

    __table_args__ = (
        # Composite index for common query patterns
        {'sqlite_with_rowid': True}  # Ensure we have rowids for better performance
    )

class Bookmark(Base):
    __tablename__ = "bookmarks"

    id = Column(Integer, primary_key=True)
    url = Column(String, index=True)
    title = Column(String, nullable=True)
    added_time = Column(DateTime, index=True)
    folder = Column(String, index=True)
    domain = Column(String, index=True)

    __table_args__ = (
        # Composite index for common query patterns
        {'sqlite_with_rowid': True}  # Ensure we have rowids for better performance
    )

# Create tables
Base.metadata.create_all(bind=engine)

# Initialize FTS tables for full-text search
def init_fts():
    """Initialize Full Text Search tables"""
    conn = engine.raw_connection()
    cursor = conn.cursor()

    # Create FTS table with content and title columns
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS history_fts USING fts5(
            title,
            markdown_content,
            domain,  -- Add domain for filtering
            visit_time UNINDEXED,  -- Add visit_time but don't index it
            content='history',
            content_rowid='id',
            tokenize='trigram'
        )
    """)

    # Update triggers to include domain and visit_time
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS history_ai AFTER INSERT ON history BEGIN
            INSERT INTO history_fts(rowid, title, markdown_content, domain, visit_time)
            VALUES (new.id, new.title, new.markdown_content, new.domain, new.visit_time);
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS history_ad AFTER DELETE ON history BEGIN
            INSERT INTO history_fts(history_fts, rowid, title, markdown_content, domain, visit_time)
            VALUES('delete', old.id, old.title, old.markdown_content, old.domain, old.visit_time);
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS history_au AFTER UPDATE ON history BEGIN
            INSERT INTO history_fts(history_fts, rowid, title, markdown_content, domain, visit_time)
            VALUES('delete', old.id, old.title, old.markdown_content, old.domain, old.visit_time);
            INSERT INTO history_fts(rowid, title, markdown_content, domain, visit_time)
            VALUES (new.id, new.title, new.markdown_content, new.domain, new.visit_time);
        END;
    """)

    conn.commit()
    cursor.close()
    conn.close()

# Initialize FTS tables
init_fts()

def reindex_fts():
    """Reindex the FTS tables"""
    conn = engine.raw_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history_fts(history_fts) VALUES('rebuild')")
    conn.commit()
    cursor.close()
    conn.close()

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_last_processed_timestamp(source):
    """
    Get last processed timestamp for a source (e.g., 'chrome_history', 'chrome_bookmarks')
    """
    db = next(get_db())
    try:
        result = db.execute(
            text('SELECT last_timestamp FROM last_processed WHERE source = :source'),
            {'source': source}
        ).fetchone()
        return result[0] if result else 0
    finally:
        db.close()

def update_last_processed_timestamp(source, timestamp):
    """
    Update last processed timestamp for a source
    """
    db = next(get_db())
    try:
        db.execute(
            text('''
                INSERT OR REPLACE INTO last_processed (source, last_timestamp)
                VALUES (:source, :timestamp)
            '''),
            {'source': source, 'timestamp': timestamp}
        )
        db.commit()
    finally:
        db.close()

def create_tables():
    db = next(get_db())
    try:
        db.execute(
            text('''
                CREATE TABLE IF NOT EXISTS last_processed (
                    source TEXT PRIMARY KEY,
                    last_timestamp INTEGER
                )
            ''')
        )
        db.commit()
    finally:
        db.close()

def search_history(query, domain=None, start_date=None, end_date=None, db=None):
    """
    Search history using FTS5 with proper ranking
    """
    if db is None:
        db = next(get_db())

    try:
        # Build the FTS query
        fts_query = f'"{query}"'  # Exact phrase
        if domain:
            fts_query += f' AND domain:"{domain}"'

        # Build date filter conditions
        date_conditions = []
        params = {'query': query}

        if start_date:
            date_conditions.append("visit_time >= :start_date")
            params['start_date'] = start_date
        if end_date:
            date_conditions.append("visit_time <= :end_date")
            params['end_date'] = end_date

        date_filter = f"AND {' AND '.join(date_conditions)}" if date_conditions else ""

        # Execute the search query
        sql_query = f"""
            SELECT
                h.*,
                bm25(history_fts) as rank,
                highlight(history_fts, 0, '<mark>', '</mark>') as title_highlight,
                highlight(history_fts, 1, '<mark>', '</mark>') as content_highlight
            FROM history_fts
            JOIN history h ON history_fts.rowid = h.id
            WHERE history_fts MATCH :query
            {date_filter}
            ORDER BY rank, visit_time DESC
            LIMIT 100
        """

        results = db.execute(text(sql_query), params).fetchall()
        return results

    except Exception as e:
        print(f"Search error: {e}")
        return []

def recreate_fts_tables():
    """Drop and recreate the FTS tables"""
    conn = engine.raw_connection()
    cursor = conn.cursor()
    try:
        # Drop existing FTS table and triggers
        cursor.execute("DROP TRIGGER IF EXISTS history_ai")
        cursor.execute("DROP TRIGGER IF EXISTS history_ad")
        cursor.execute("DROP TRIGGER IF EXISTS history_au")
        cursor.execute("DROP TABLE IF EXISTS history_fts")

        # Recreate FTS tables and triggers
        init_fts()

        # Reindex all existing content
        cursor.execute("""
            INSERT INTO history_fts(rowid, title, markdown_content, domain, visit_time)
            SELECT id, title, markdown_content, domain, visit_time FROM history
        """)

        conn.commit()
        print("Successfully recreated FTS tables and reindexed content")

    except Exception as e:
        conn.rollback()
        print(f"Error recreating FTS tables: {e}")
    finally:
        cursor.close()
        conn.close()