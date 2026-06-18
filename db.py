from datetime import datetime, date
from sqlalchemy import (create_engine, String, Integer, Text, DateTime, Date,
                        UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from config import DATABASE_URL

url = DATABASE_URL
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+psycopg://", 1)
elif url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)
Session = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    email: Mapped[str] = mapped_column(String(300))
    website: Mapped[str] = mapped_column(String(500), default="")
    niche: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="new")
    draft_subject: Mapped[str] = mapped_column(Text, default="")
    draft_body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("email", name="uq_lead_email"),)

class SendLog(Base):
    __tablename__ = "send_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, default=date.today)
    count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("day", name="uq_send_day"),)

Base.metadata.create_all(engine)

def sent_today() -> int:
    with Session() as s:
        row = s.query(SendLog).filter_by(day=date.today()).first()
        return row.count if row else 0

def bump_sent(n=1):
    with Session() as s:
        row = s.query(SendLog).filter_by(day=date.today()).first()
        if not row:
            row = SendLog(day=date.today(), count=0); s.add(row)
        row.count += n
        s.commit()
