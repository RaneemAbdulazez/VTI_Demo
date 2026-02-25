import os
import httpx
from fastapi import FastAPI, Request
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# In-memory dictionary to store state per chat_id
# Note: For production on Vercel (serverless), in-memory state will not persist across requests.
# This requires a database (like Redis or Postgres) for production deployments.
user_state = {}

# Retrieve the bot token from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# System Admin identifier for unrestricted developer access
ADMIN_PHONE_NUMBER = os.getenv("ADMIN_PHONE_NUMBER", "+12865471304")

# ==========================================
# INSTRUCTIONS TO SET THE WEBHOOK MANUALLY
# ==========================================
# Once you deploy to Vercel and have your public URL (e.g., https://your-app.vercel.app),
# you need to tell Telegram to send updates to your /webhook endpoint.
# 
# Open your web browser or use curl to visit this URL (replace placeholders):
# https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<YOUR_VERCEL_APP_URL>/webhook
#
# To verify it worked, you can visit:
# https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/getWebhookInfo
# ==========================================

def get_initial_jobs():
    return [
        "Job 101 | 123 Main St - Pipe Leak",
        "Job 102 | 456 Oak Ave - Water Heater",
        "Job 103 | 789 Pine Rd - Clogged Drain",
        "Job 104 | 321 Elm St - Toilet Repair",
        "Job 105 | 654 Maple Dr - Faucet Replacement"
    ]

@app.get("/")
async def health_check():
    """
    Health check endpoint to verify the bot is running.
    """
    return {"status": "Bot is running"}

async def send_telegram_message(chat_id: int, text: str, reply_markup: dict = None):
    """
    Helper function to send a message to a Telegram chat.
    """
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

@app.post("/webhook")
async def receive_update(request: Request):
    """
    Endpoint to receive webhook updates from Telegram.
    """
    update = await request.json()
    
    # Check if the update contains a message
    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        
        # Check if the user shared their contact information
        contact_number = None
        if "contact" in message:
            contact_number = message["contact"].get("phone_number")
            # Ensure number formatting consistently has a '+' prefix
            if contact_number and not contact_number.startswith('+'):
                contact_number = '+' + contact_number
                
        # We can also attempt to read phone number if explicitly sent in text (for testing)
        text = message.get("text", "")
        
        # -------------------------------------------------------------
        # ADMIN BYPASS LOGIC
        # -------------------------------------------------------------
        if contact_number == ADMIN_PHONE_NUMBER or text == ADMIN_PHONE_NUMBER:
            # Bypass all standard flows for the System Admin/Developer
            admin_text = (
                "🔧 *Admin Flow Initiated*\n"
                "I recognize you as the System Admin/Developer.\n"
                "Awaiting direct commands or testing prompts. Standard workflows bypassed."
            )
            # Remove persistent keyboard
            reply_markup = {"remove_keyboard": True}
            await send_telegram_message(
                chat_id=chat_id, 
                text=admin_text, 
                reply_markup=reply_markup
            )
            return {"ok": True}
        # -------------------------------------------------------------
        
        # Initialize state and mock data for new interaction
        if chat_id not in user_state:
            user_state[chat_id] = {
                "jobs": get_initial_jobs(),
                "status": "active"
            }
            
        if text.startswith("/start"):
            welcome_text = (
                "Welcome to the Voice-to-Invoice Bot! 🛠️\n"
                "I'm here to help you manage your plumbing jobs."
            )
            
            # Persistent Keyboard with exactly three buttons
            reply_markup = {
                "keyboard": [
                    [{"text": "View Jobs"}],
                    [{"text": "Finish"}, {"text": "Restart"}]
                ],
                "resize_keyboard": True,
                "is_persistent": True
            }
            
            await send_telegram_message(
                chat_id=chat_id, 
                text=welcome_text, 
                reply_markup=reply_markup
            )
        else:
            # Handle other text inputs if necessary, for now just acknowledge
            # (In future steps, we can handle "View Jobs", "Finish", etc.)
            pass
            
    return {"ok": True}
