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

async def send_telegram_message(chat_id: int, text: str, reply_markup: dict = None, parse_mode: str = None):
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
    if parse_mode:
        payload["parse_mode"] = parse_mode
        
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

@app.post("/webhook")
async def receive_update(request: Request):
    """
    Endpoint to receive webhook updates from Telegram.
    """
    update = await request.json()
    
    # Handle callback queries from inline keyboards (interactive buttons)
    if "callback_query" in update:
        callback_query = update["callback_query"]
        chat_id = callback_query["message"]["chat"]["id"]
        data = callback_query.get("data", "")
        
        # When user taps an interactive job button
        if data.startswith("job_"):
            job_id = data.split("_")[1]
            await send_telegram_message(
                chat_id=chat_id,
                text=f"You selected Job **{job_id}**. Please wait while I pull up its details and invoice options...",
                parse_mode="Markdown"
            )
            
        return {"ok": True}
    
    # Check if the update contains a normal message
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
            text_lower = text.lower()
            view_jobs_triggers = ["view jobs", "show my schedule", "what are the tasks", "job list", "schedule", "jobs"]
            
            if any(trigger in text_lower for trigger in view_jobs_triggers):
                # Format using single asterisks for standard Markdown in Telegram
                jobs_text = (
                    "Here are the current jobs on the schedule:\n\n"
                    "1. *Job ID: #ST-10021*\n"
                    "   - *Type:* Plumbing Leak Detection\n"
                    "   - *Street:* Maple Avenue\n"
                    "   - *Time:* 09:00 AM\n\n"
                    "2. *Job ID: #ST-10022*\n"
                    "   - *Type:* Water Heater Inspection\n"
                    "   - *Street:* Oak Street\n"
                    "   - *Time:* 11:30 AM\n\n"
                    "3. *Job ID: #ST-10023*\n"
                    "   - *Type:* Routine Maintenance\n"
                    "   - *Street:* Pine Boulevard\n"
                    "   - *Time:* 02:00 PM\n\n"
                    "4. *Job ID: #ST-10024*\n"
                    "   - *Type:* Main Line Repair\n"
                    "   - *Street:* Cedar Lane\n"
                    "   - *Time:* 04:15 PM\n\n"
                    "5. *Job ID: #ST-10025*\n"
                    "   - *Type:* Emergency Drain Cleaning\n"
                    "   - *Street:* Elm Drive\n"
                    "   - *Time:* 06:00 PM\n\n"
                    "Would you like to view a specific job's details or generate an invoice for any of these?"
                )
                
                # Create interactive buttons for each job
                inline_keyboard = {
                    "inline_keyboard": [
                        [{"text": "Select #ST-10021", "callback_data": "job_#ST-10021"}],
                        [{"text": "Select #ST-10022", "callback_data": "job_#ST-10022"}],
                        [{"text": "Select #ST-10023", "callback_data": "job_#ST-10023"}],
                        [{"text": "Select #ST-10024", "callback_data": "job_#ST-10024"}],
                        [{"text": "Select #ST-10025", "callback_data": "job_#ST-10025"}]
                    ]
                }
                
                await send_telegram_message(
                    chat_id=chat_id, 
                    text=jobs_text,
                    reply_markup=inline_keyboard,
                    parse_mode="Markdown"
                )
            else:
                # Handle other text inputs if necessary
                pass
            
    return {"ok": True}
