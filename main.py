import os
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

# In-memory dictionary to store state per chat_id
# Note: For production on Vercel (serverless), in-memory state will not persist across requests.
# This requires a database (like Redis or Postgres) for production deployments.
user_state = {}

# Retrieve the bot token from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

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
    
    # Check if the update contains a message with text
    if "message" in update and "text" in update["message"]:
        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message["text"]
        
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
