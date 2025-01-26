from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./browser_history.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class HistoryEntry(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True)
    url = Column(String)
    title = Column(String)
    visit_time = Column(DateTime)
    domain = Column(String)
    markdown_content = Column(Text, nullable=True)
    last_content_update = Column(DateTime, nullable=True)

class Bookmark(Base):
    __tablename__ = "bookmarks"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    title = Column(String, nullable=True)
    added_time = Column(DateTime, index=True)
    folder = Column(String, index=True)
    domain = Column(String, index=True)

class BlacklistedDomain(Base):
    __tablename__ = "blacklisted_domains"

    id = Column(Integer, primary_key=True)
    domain = Column(String, unique=True, index=True)
    reason = Column(String, nullable=True)
    added_time = Column(DateTime, default=datetime.utcnow)

    @classmethod
    def is_blacklisted(cls, db: SessionLocal, domain: str) -> bool:
        """Check if a domain is blacklisted"""
        return db.query(cls).filter(cls.domain == domain.lower()).first() is not None

    @classmethod
    def add_to_blacklist(cls, db: SessionLocal, domain: str, reason: str = None):
        """Add a domain to the blacklist"""
        try:
            blacklist_entry = cls(
                domain=domain.lower(),
                reason=reason
            )
            db.add(blacklist_entry)
            db.commit()
        except:
            db.rollback()
            # If entry already exists, just update the reason
            existing = db.query(cls).filter(cls.domain == domain.lower()).first()
            if existing and reason:
                existing.reason = reason
                db.commit()

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()