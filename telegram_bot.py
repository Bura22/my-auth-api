from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import datetime
import httpx
import json

TOKEN = "8671963553:AAHYOpgs4ClQ_1CSQSRr2TstJKBApmFek2U"

# YOUR API URL (running locally)
API_BASE_URL = "https://my-auth-api.onrender.com"  # Use YOUR actual Render URL

user_sessions = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_sessions:
        del user_sessions[chat_id]
    await update.message.reply_text(
        "🔐 Welcome to Your App!\n\n"
        "Please send me your ID number to begin authentication."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = update.message.text.strip()
    
    # Validate numbers only
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
            }
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

async def handle_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    otp_code = update.message.text.strip()
    
    if chat_id not in user_sessions or user_sessions[chat_id].get("step") != "awaiting_otp":
        await update.message.reply_text("Please send your ID first using /start")
        return
    
    user_id = user_sessions[chat_id]["user_id"]
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/verify-otp",
            json={
                "user_id": user_id,
                "otp_code": otp_code,
                "telegram_chat_id": str(chat_id)
            }
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
        else:
            await update.message.reply_text("❌ Verification failed. Please try again.")

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
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["success"]:
                # Format the response nicely
                message = f"📱 **Your App Data**\n\n"
                message += f"👤 **Profile:**\n"
                message += f"  Name: {data['profile']['name']}\n"
                message += f"  ID: {data['profile']['user_id']}\n"
                message += f"  Phone: {data['profile']['phone']}\n"
                message += f"  Email: {data['profile']['email']}\n\n"
                message += f"💰 **Balance:** ${data['balance']}\n\n"
                message += f"📦 **Recent Orders:**\n"
                for order in data['transactions']:
                    message += f"  • {order['id']}: ${order['amount']} ({order['date']})\n"
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ {data['message']}")
        else:
            await update.message.reply_text("❌ Failed to get data")

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

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("content", get_content))
    
    # Message handler needs to distinguish between ID and OTP
    # For simplicity, we'll assume first message is ID, subsequent are OTP
    # (You can enhance this with state tracking)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()