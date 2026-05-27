from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

# Create SQLite database (file-based, no setup needed)
engine = create_engine("sqlite:///./auth.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# Define User table
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)  # The ID user sends to bot
    phone_number = Column(String)  # Phone number for SMS
    name = Column(String)  # User's name
    email = Column(String, nullable=True)  # Optional email
    created_at = Column(DateTime, default=datetime.datetime.now)

# Define OTP table for temporary codes
class OTP(Base):
    __tablename__ = "otps"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)  # Which user this OTP is for
    otp_code = Column(String)  # 6-digit code
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    expires_at = Column(DateTime)  # When OTP expires (2 minutes)
    attempts = Column(Integer, default=0)  # Failed attempts

# Define Session table for authenticated users
class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    telegram_chat_id = Column(String, index=True)
    session_token = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    expires_at = Column(DateTime)  # 24 hours from creation

# Create all tables
Base.metadata.create_all(bind=engine)

# Helper function to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()