import os
import httpx
import tempfile
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from openai import AsyncOpenAI

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

# OpenAI API Client setup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

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
            job_id = data.split("_")[1].strip()
            
            # State management for the job selection
            if chat_id not in user_state:
                user_state[chat_id] = {"jobs": get_initial_jobs()}
            user_state[chat_id]["selected_job"] = job_id
            user_state[chat_id]["status"] = "awaiting_voice"
            
            await send_telegram_message(
                chat_id=chat_id,
                text=f"You selected Job **{job_id}**.\n\nPlease record a voice message describing what you have done in the job (e.g. hours worked, job done there).",
                parse_mode="Markdown"
            )
            
        elif data == "confirm_job":
            if user_state.get(chat_id, {}).get("status") == "awaiting_confirmation":
                user_state[chat_id]["status"] = "confirmed"
                await send_telegram_message(
                    chat_id=chat_id,
                    text="✅ Confirmed! Moving to the next step..."
                )
        
        elif data == "retry_job":
            if user_state.get(chat_id, {}).get("status") == "awaiting_confirmation":
                user_state[chat_id]["status"] = "awaiting_voice"
                await send_telegram_message(
                    chat_id=chat_id,
                    text="Please record your voice message again."
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
        # HANDLE VOICE MESSAGES (STEP 3)
        # -------------------------------------------------------------
        if "voice" in message:
            state = user_state.get(chat_id, {})
            if state.get("status") == "awaiting_voice":
                await send_telegram_message(chat_id=chat_id, text="🎙️ Voice note received! Transcribing and summarizing...")
                
                try:
                    file_id = message["voice"]["file_id"]
                    
                    # Fetch file info from Telegram
                    file_info_url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(file_info_url)
                        file_info = resp.json()
                        
                    if not file_info.get("ok"):
                        await send_telegram_message(chat_id=chat_id, text="Failed to get voice file info from Telegram.")
                        return {"ok": True}
                        
                    file_path = file_info["result"]["file_path"]
                    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                    
                    # Download actual voice bytes
                    async with httpx.AsyncClient() as client:
                        file_resp = await client.get(download_url)
                        voice_bytes = file_resp.content
                        
                    # Save temporarily for Whisper
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp_file:
                        tmp_file.write(voice_bytes)
                        tmp_filename = tmp_file.name
                        
                    # Transcribe with OpenAI
                    if not openai_client:
                        await send_telegram_message(chat_id=chat_id, text="OpenAI API key missing. Cannot process voice.")
                        return {"ok": True}
                        
                    with open(tmp_filename, "rb") as audio_file:
                        transcription = await openai_client.audio.transcriptions.create(
                            model="whisper-1", 
                            file=audio_file
                        )
                    os.remove(tmp_filename)
                    
                    transcribed_text = transcription.text
                    
                    # Summarize with GPT
                    system_prompt = (
                        "Extract the key details from the plumber's transcription into standard bullet points. "
                        "Focus strictly on: Hours worked, and the specific Job(s) done there. "
                        "Keep it concise. Format as Markdown bullets."
                    )
                    completion = await openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Transcription:\n{transcribed_text}"}
                        ]
                    )
                    
                    summary_bullets = completion.choices[0].message.content
                    
                    # Send for confirmation
                    user_state[chat_id]["status"] = "awaiting_confirmation"
                    user_state[chat_id]["current_summary"] = summary_bullets
                    
                    confirm_text = (
                        f"*Job Summary Draft:*\n\n"
                        f"{summary_bullets}\n\n"
                        f"Does this look correct?"
                    )
                    
                    inline_keyboard = {
                        "inline_keyboard": [
                            [{"text": "✅ Confirm", "callback_data": "confirm_job"}],
                            [{"text": "🔄 Re-record", "callback_data": "retry_job"}]
                        ]
                    }
                    
                    await send_telegram_message(
                        chat_id=chat_id, 
                        text=confirm_text,
                        reply_markup=inline_keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    await send_telegram_message(chat_id=chat_id, text=f"Error processing voice note: {str(e)}")
            else:
                await send_telegram_message(chat_id=chat_id, text="Voice note received! But you need to select a job first.")
            
            return {"ok": True}
        
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
                jobs_data = [
                    {"id": "#ST-10021", "type": "Plumbing Leak Detection", "street": "Maple Avenue", "time": "09:00 AM"},
                    {"id": "#ST-10022", "type": "Water Heater Inspection", "street": "Oak Street", "time": "11:30 AM"},
                    {"id": "#ST-10023", "type": "Routine Maintenance", "street": "Pine Boulevard", "time": "02:00 PM"},
                    {"id": "#ST-10024", "type": "Main Line Repair", "street": "Cedar Lane", "time": "04:15 PM"},
                    {"id": "#ST-10025", "type": "Emergency Drain Cleaning", "street": "Elm Drive", "time": "06:00 PM"},
                ]
                
                # Send the heading first
                await send_telegram_message(
                    chat_id=chat_id, 
                    text="Here are the current jobs on the schedule:\n",
                    parse_mode="Markdown"
                )
                
                # Loop through and send each job as its own distinct message with its own button attached
                for idx, job in enumerate(jobs_data, 1):
                    job_text = (
                        f"*{idx}. Job ID: {job['id']}*\n"
                        f"   - *Type:* {job['type']}\n"
                        f"   - *Street:* {job['street']}\n"
                        f"   - *Time:* {job['time']}"
                    )
                    
                    inline_keyboard = {
                        "inline_keyboard": [
                            [{"text": f"✅ Choose {job['id']}", "callback_data": f"job_{job['id']} "}]
                        ]
                    }
                    
                    await send_telegram_message(
                        chat_id=chat_id, 
                        text=job_text,
                        reply_markup=inline_keyboard,
                        parse_mode="Markdown"
                    )
                
                # Send the final follow up prompt
                await send_telegram_message(
                    chat_id=chat_id, 
                    text="Would you like to view a specific job's details or generate an invoice for any of these?",
                    parse_mode="Markdown"
                )
            else:
                # Handle other text inputs if necessary
                pass
            
    return {"ok": True}
