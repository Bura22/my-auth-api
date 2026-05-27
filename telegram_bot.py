from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import datetime
import httpx
import os
import asyncio

# Get configuration from environment variables (Render will set these)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_BASE_URL = os.environ.get("API_BASE_URL", "https://your-api-url.onrender.com")

# Make sure token exists
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

# Store user sessions (in production, use Redis - but for free tier, memory is fine)
user_sessions = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_sessions:
        del user_sessions[chat_id]
    await update.message.reply_text(
        "🔐 Welcome to Your App!\n\n"
        "Please send me your ID number to begin authentication."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/start - Start authentication\n"
        "/content - View your app data\n"
        "/help - Show this help\n"
        "/cancel - Logout"
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_sessions:
        del user_sessions[chat_id]
    await update.message.reply_text("Logged out. Type /start to begin again.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_sessions:
        await update.message.reply_text("No active session. Type /start to begin.")
    elif user_sessions[chat_id].get("authenticated"):
        await update.message.reply_text("✅ You are authenticated! Type /content to get your data.")
    else:
        await update.message.reply_text("⏳ Waiting for OTP verification.")

async def get_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if chat_id not in user_sessions or not user_sessions[chat_id].get("authenticated"):
        await update.message.reply_text("❌ Please authenticate first using /start")
        return
    
    session_token = user_sessions[chat_id]["session_token"]
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/get-user-data",
            json={
                "session_token": session_token,
                "telegram_chat_id": str(chat_id)
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["success"]:
                message = f"📱 **Your App Data**\n\n"
                message += f"👤 **Profile:**\n"
                message += f"  Name: {data['profile']['name']}\n"
                message += f"  ID: {data['profile']['user_id']}\n"
                message += f"  Phone: {data['profile']['phone']}\n\n"
                message += f"💰 **Balance:** ${data['balance']}\n\n"
                message += f"📦 **Recent Orders:**\n"
                for order in data['transactions']:
                    message += f"  • {order['id']}: ${order['amount']} ({order['date']})\n"
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ {data['message']}")
        else:
            await update.message.reply_text("❌ Failed to get data from server")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = update.message.text.strip()
    
    # Check if user is already authenticated
    if chat_id in user_sessions and user_sessions[chat_id].get("authenticated"):
        await update.message.reply_text(
            "You are already authenticated! Use /content to get your data or /cancel to logout."
        )
        return
    
    # Check if user is waiting for OTP
    if chat_id in user_sessions and user_sessions[chat_id].get("step") == "awaiting_otp":
        # This is an OTP submission
        await handle_otp(update, context, message_text)
        return
    
    # Otherwise, treat as ID submission
    if not message_text.isdigit():
        await update.message.reply_text("❌ Please enter a valid ID with numbers only.")
        return
    
    # Store ID and request OTP
    user_sessions[chat_id] = {"user_id": message_text, "step": "awaiting_otp"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/send-otp",
            json={
                "user_id": message_text,
                "telegram_chat_id": str(chat_id)
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            await update.message.reply_text(
                f"✅ ID {message_text} received!\n"
                f"📱 An OTP has been sent to your registered phone.\n"
                f"🔢 Please enter the 6-digit code.\n\n"
                f"⏰ Code expires in {data['expires_in']} seconds."
            )
        else:
            await update.message.reply_text("❌ Failed to send OTP. Please try again.")
            del user_sessions[chat_id]

async def handle_otp(update: Update, context: ContextTypes.DEFAULT_TYPE, otp_code: str):
    chat_id = update.effective_chat.id
    
    if chat_id not in user_sessions:
        await update.message.reply_text("Session expired. Please send your ID again.")
        return
    
    user_id = user_sessions[chat_id]["user_id"]
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/verify-otp",
            json={
                "user_id": user_id,
                "otp_code": otp_code,
                "telegram_chat_id": str(chat_id)
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["verified"]:
                user_sessions[chat_id]["authenticated"] = True
                user_sessions[chat_id]["session_token"] = data["session_token"]
                user_sessions[chat_id]["step"] = "authenticated"
                await update.message.reply_text(
                    f"✅ {data['message']}\n\n"
                    f"Type /content to view your app data!\n"
                    f"Type /help for commands."
                )
            else:
                await update.message.reply_text(f"❌ {data['message']}")
                # Allow retry - don't delete session
        else:
            await update.message.reply_text("❌ Verification failed. Please try again.")

def main():
    # Create the bot application
    app = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("content", get_content))
    
    # Add message handler for all text messages (non-commands)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print(f"🤖 Bot is starting...")
    print(f"📡 Connected to API: {API_BASE_URL}")
    print(f"✅ Bot is running! Press Ctrl+C to stop.")
    
    # Start the bot (polling mode)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()