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
    # Enable write-ahead logging and set a larger pool size
    pool_size=1,  # Single connection pool since we're using one connection
    max_overflow=0,  # Prevent additional connections
    pool_recycle=3600,  # Recycle connection every hour
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

    # Create FTS table for history content
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS history_fts USING fts5(
            title,
            markdown_content,
            content='history',
            content_rowid='id',
            tokenize='porter unicode61'
        )
    """)

    # Create triggers to keep FTS index up to date
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS history_ai AFTER INSERT ON history BEGIN
            INSERT INTO history_fts(rowid, title, markdown_content)
            VALUES (new.id, new.title, new.markdown_content);
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS history_ad AFTER DELETE ON history BEGIN
            INSERT INTO history_fts(history_fts, rowid, title, markdown_content)
            VALUES('delete', old.id, old.title, old.markdown_content);
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS history_au AFTER UPDATE ON history BEGIN
            INSERT INTO history_fts(history_fts, rowid, title, markdown_content)
            VALUES('delete', old.id, old.title, old.markdown_content);
            INSERT INTO history_fts(rowid, title, markdown_content)
            VALUES (new.id, new.title, new.markdown_content);
        END;
    """)

    conn.commit()
    cursor.close()
    conn.close()

# Initialize FTS tables
init_fts()

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