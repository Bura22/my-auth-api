import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import random
import datetime
import secrets
from sqlalchemy.orm import Session
from database import get_db, User, OTP, Session as DBSession

app = FastAPI(title="My Auth API", description="Authentication API for Telegram Bot")

# Enable CORS (so your bot can call this API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class SendOTPRequest(BaseModel):
    user_id: str
    telegram_chat_id: str

class SendOTPResponse(BaseModel):
    success: bool
    message: str
    expires_in: int

class VerifyOTPRequest(BaseModel):
    user_id: str
    otp_code: str
    telegram_chat_id: str

class VerifyOTPResponse(BaseModel):
    verified: bool
    session_token: Optional[str] = None
    message: str

class UserDataRequest(BaseModel):
    session_token: str
    telegram_chat_id: str

class UserDataResponse(BaseModel):
    success: bool
    profile: Optional[dict] = None
    balance: Optional[float] = None
    transactions: Optional[list] = None
    message: str

# Helper Functions
def generate_otp():
    """Generate 6-digit OTP"""
    return f"{random.randint(100000, 999999)}"

def clean_expired_otps(db: Session):
    """Remove expired OTPs"""
    expired = db.query(OTP).filter(OTP.expires_at < datetime.datetime.now()).all()
    for otp in expired:
        db.delete(otp)
    db.commit()

# API Endpoints

@app.post("/send-otp", response_model=SendOTPResponse)
async def send_otp(request: SendOTPRequest, db: Session = Depends(get_db)):
    """
    Step 1: User sends ID, API sends OTP to their registered phone
    """
    # Clean expired OTPs first
    clean_expired_otps(db)
    
    # Find user by their ID
    user = db.query(User).filter(User.user_id == request.user_id).first()
    
    if not user:
        # For demo, create user if doesn't exist
        # In production, you'd have pre-registered users
        user = User(
            user_id=request.user_id,
            phone_number="+15551234567",  # Would come from your database
            name=f"User_{request.user_id}"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # Check if there's already an unverified OTP
    existing_otp = db.query(OTP).filter(
        OTP.user_id == request.user_id,
        OTP.is_verified == False,
        OTP.expires_at > datetime.datetime.now()
    ).first()
    
    if existing_otp:
        # Delete existing OTP to create new one
        db.delete(existing_otp)
        db.commit()
    
    # Generate new OTP
    otp_code = generate_otp()
    expires_at = datetime.datetime.now() + datetime.timedelta(minutes=2)
    
    # Store OTP in database
    new_otp = OTP(
        user_id=request.user_id,
        otp_code=otp_code,
        expires_at=expires_at
    )
    db.add(new_otp)
    db.commit()
    
    # TODO: ACTUALLY SEND SMS HERE
    # For now, we'll just print it (in production, use Twilio)
    print(f"📱 SIMULATED SMS to {user.phone_number}: Your OTP is {otp_code}")
    
    # In production with Twilio, uncomment this:
    # from twilio.rest import Client
    # client = Client(account_sid, auth_token)
    # client.messages.create(
    #     body=f"Your verification code is: {otp_code}",
    #     from_="+YourTwilioNumber",
    #     to=user.phone_number
    # )
    
    return SendOTPResponse(
        success=True,
        message=f"OTP sent to registered phone number",
        expires_in=120  # 2 minutes in seconds
    )

@app.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    """
    Step 2: User enters OTP, API verifies it and returns session token
    """
    # Find the OTP
    otp_record = db.query(OTP).filter(
        OTP.user_id == request.user_id,
        OTP.otp_code == request.otp_code,
        OTP.is_verified == False
    ).first()
    
    if not otp_record:
        return VerifyOTPResponse(
            verified=False,
            message="Invalid OTP code"
        )
    
    # Check if expired
    if otp_record.expires_at < datetime.datetime.now():
        return VerifyOTPResponse(
            verified=False,
            message="OTP has expired. Please request a new one."
        )
    
    # Check attempts (max 3)
    if otp_record.attempts >= 3:
        return VerifyOTPResponse(
            verified=False,
            message="Too many failed attempts. Please request a new OTP."
        )
    
    # Mark OTP as verified
    otp_record.is_verified = True
    otp_record.attempts += 1
    db.commit()
    
    # Generate session token
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.now() + datetime.timedelta(hours=24)
    
    # Store session
    new_session = DBSession(
        user_id=request.user_id,
        telegram_chat_id=request.telegram_chat_id,
        session_token=session_token,
        expires_at=expires_at
    )
    db.add(new_session)
    db.commit()
    
    return VerifyOTPResponse(
        verified=True,
        session_token=session_token,
        message="Verification successful! You are now authenticated."
    )

@app.post("/get-user-data", response_model=UserDataResponse)
async def get_user_data(request: UserDataRequest, db: Session = Depends(get_db)):
    """
    Step 3: Get app content after authentication
    """
    # Validate session token
    session = db.query(DBSession).filter(
        DBSession.session_token == request.session_token,
        DBSession.telegram_chat_id == request.telegram_chat_id
    ).first()
    
    if not session:
        return UserDataResponse(
            success=False,
            message="Invalid or expired session. Please authenticate again."
        )
    
    # Check if session expired
    if session.expires_at < datetime.datetime.now():
        db.delete(session)
        db.commit()
        return UserDataResponse(
            success=False,
            message="Session expired. Please authenticate again."
        )
    
    # Get user data
    user = db.query(User).filter(User.user_id == session.user_id).first()
    
    if not user:
        return UserDataResponse(
            success=False,
            message="User not found."
        )
    
    # Here's where you add YOUR app's custom data
    # This is the content you want to extract from your app
    
    profile = {
        "user_id": user.user_id,
        "name": user.name,
        "email": user.email or "Not provided",
        "phone": user.phone_number,
        "member_since": user.created_at.strftime("%Y-%m-%d")
    }
    
    # Example: Custom app data - REPLACE THIS WITH YOUR ACTUAL APP DATA
    custom_data = {
        "balance": 1250.75,
        "points": 340,
        "subscription_status": "active",
        "recent_orders": [
            {"id": "ORD-001", "date": "2026-05-25", "amount": 49.99},
            {"id": "ORD-002", "date": "2026-05-26", "amount": 29.99}
        ],
        "notifications": [
            "Your order has been shipped!",
            "New feature available!"
        ]
    }
    
    return UserDataResponse(
        success=True,
        profile=profile,
        balance=custom_data["balance"],
        transactions=custom_data["recent_orders"],
        message="Data retrieved successfully"
    )

@app.get("/health")
async def health_check():
    """Check if API is running"""
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

@app.post("/register-user")
async def register_user(user_id: str, phone_number: str, name: str, db: Session = Depends(get_db)):
    """Register a new user (so they can receive OTPs)"""
    existing = db.query(User).filter(User.user_id == user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="User ID already exists")
    
    new_user = User(
        user_id=user_id,
        phone_number=phone_number,
        name=name
    )
    db.add(new_user)
    db.commit()
    
    return {"success": True, "message": f"User {name} registered successfully"}

#if __name__ == "__main__":
 #   import uvicorn
  #  uvicorn.run(app, host="0.0.0.0", port=8000)