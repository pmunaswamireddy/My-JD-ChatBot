import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import config
from parser import extract_text_from_bytes, extract_text_from_file
from analyzer import (
    generate_conversational_response,
    classify_document
)
from dispatchers import (
    dispatch_to_all_configured_channels,
    send_to_telegram,
    split_message
)

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# User sessions: {chat_id: {"history": [{"role": "user"|"assistant", "content": str}], "files": [{"name": str, "type": str, "text": str}]}}
user_sessions: Dict[int, Dict[str, Any]] = {}

def get_session(chat_id: int) -> Dict[str, Any]:
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            "history": [],
            "files": []
        }
    return user_sessions[chat_id]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start and /new."""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"history": [], "files": []}
    
    welcome_text = (
        "👋 *Hi! I am your AI Recruiter & ATS Intelligence Assistant.*\n\n"
        "You can chat with me naturally just like ChatGPT or Gemini!\n\n"
        "✨ *What you can do:*\n"
        "• Send **one or multiple Job Descriptions (JDs)** (as documents or text)\n"
        "• Send **multiple candidate resumes** (PDF, DOCX, TXT)\n"
        "• Talk to me naturally: *\"Analyze these resumes against the JD\"* or *\"Compare these 3 candidates\"*\n"
        "• Ask follow-ups: *\"Why did candidate X score lower?\"* or *\"Generate 5 interview questions for Alex\"*\n\n"
        "⚡ *Quick Shortcuts:*\n"
        "• `/demo` — Run an instant demo with preloaded JDs & resumes\n"
        "• `/status` — View your uploaded files and active channels\n"
        "• `/clear` — Reset conversation history and uploaded files"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /clear."""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"history": [], "files": []}
    await update.message.reply_text("🧹 *All conversation history and uploaded documents have been cleared!*", parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /status."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    files = session.get("files", [])
    history_count = len(session.get("history", []))

    jds = [f["name"] for f in files if f["type"] == "job_description"]
    resumes = [f["name"] for f in files if f["type"] == "resume"]

    status_lines = [
        "📊 *Current Session Overview:*",
        f"• *Messages in Context:* `{history_count}`",
        f"• *Job Descriptions ({len(jds)}):* {', '.join(jds) if jds else '_None uploaded yet_'}",
        f"• *Resumes ({len(resumes)}):* {', '.join(resumes) if resumes else '_None uploaded yet_'}"
    ]

    channels = ["Telegram"]
    if config.DISCORD_WEBHOOK_URL:
        channels.append("Discord")
    if config.SLACK_WEBHOOK_URL:
        channels.append("Slack")
    status_lines.append(f"• *Active Broadcast Channels:* {', '.join(channels)}")

    if not files:
        status_lines.append("\n💡 _Attach your JD and resume documents or paste text to begin!_")
    else:
        status_lines.append("\n💡 _You can ask me anything about these files or tell me to evaluate them!_")

    await update.message.reply_text("\n".join(status_lines), parse_mode="Markdown")


async def demo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Loads sample files and triggers conversational analysis."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    sample_dir = Path(__file__).resolve().parent / "sample_data"

    jd_file = sample_dir / "sample_jd.txt"
    r1_file = sample_dir / "resume_alex_rivers.txt"
    r2_file = sample_dir / "resume_sarah_chen.txt"

    if not jd_file.exists() or not r1_file.exists():
        await update.message.reply_text("❌ Sample files not found.")
        return

    session["files"] = [
        {"name": "Senior_AI_Engineer_JD.txt", "type": "job_description", "text": extract_text_from_file(str(jd_file))},
        {"name": "Alex_Rivers_Resume.docx", "type": "resume", "text": extract_text_from_file(str(r1_file))},
        {"name": "Sarah_Chen_Resume.docx", "type": "resume", "text": extract_text_from_file(str(r2_file))}
    ]

    await update.message.reply_text(
        "🚀 *Demo Loaded:* 1 Job Description + 2 Resumes (Alex Rivers & Sarah Chen).\n"
        "⏳ *Analyzing candidate fit with Gemini AI...*",
        parse_mode="Markdown"
    )

    prompt = "Please evaluate all candidate resumes against the Job Description and provide the structured ATS rankings, missing skills, and course recommendations."
    await process_ai_interaction(update, chat_id, session, prompt)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles uploaded files (.pdf, .docx, .txt)."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    doc = update.message.document
    filename = doc.file_name or "document"
    ext = Path(filename).suffix.lower()

    if ext not in [".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".odt", ".csv", ".html"]:
        await update.message.reply_text(
            f"⚠️ Unsupported format `{ext}`. Supported formats: `.pdf`, `.docx`, `.doc`, `.txt`, `.rtf`, `.md`.",
            parse_mode="Markdown"
        )
        return

    wait_msg = await update.message.reply_text(f"📥 Reading `{filename}`...", parse_mode="Markdown")

    try:
        tg_file = await doc.get_file()
        file_bytes = await tg_file.download_as_bytearray()
        extracted_text = extract_text_from_bytes(bytes(file_bytes), filename)

        if not extracted_text:
            await wait_msg.edit_text(f"❌ Could not extract readable text from `{filename}`.")
            return

        doc_type = classify_document(extracted_text, filename)
        label = "Job Description" if doc_type == "job_description" else "Candidate Resume"

        # Check if already added
        session["files"] = [f for f in session["files"] if f["name"] != filename]
        session["files"].append({
            "name": filename,
            "type": doc_type,
            "text": extracted_text
        })

        jds = [f["name"] for f in session["files"] if f["type"] == "job_description"]
        resumes = [f["name"] for f in session["files"] if f["type"] == "resume"]

        await wait_msg.edit_text(
            f"✅ *Received:* `{filename}`\n"
            f"🔍 *Detected as:* `{label}`\n\n"
            f"📂 *Current Attachments:* `{len(jds)}` JD(s), `{len(resumes)}` Resume(s).\n\n"
            "💬 You can upload more files, or type *\"Analyze these resumes\"* or ask any question!",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error handling document: {e}")
        await wait_msg.edit_text(f"❌ Error processing file: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles natural conversational text from the user."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    user_text = update.message.text.strip()

    await process_ai_interaction(update, chat_id, session, user_text)


async def process_ai_interaction(update: Update, chat_id: int, session: Dict[str, Any], user_text: str):
    """Processes conversational message with attached documents context."""
    # Build prompt incorporating current attached files if available
    attached_context = ""
    if session.get("files"):
        attached_context = "\n=== ATTACHED DOCUMENTS IN THIS SESSION ===\n"
        for idx, f in enumerate(session["files"], 1):
            type_label = "JOB DESCRIPTION" if f["type"] == "job_description" else "CANDIDATE RESUME"
            attached_context += f"\n--- DOCUMENT #{idx}: {f['name']} ({type_label}) ---\n{f['text']}\n"

    # User message payload
    augmented_user_message = user_text
    if attached_context and len(session["history"]) == 0:
        augmented_user_message = f"{user_text}\n{attached_context}"
    elif attached_context:
        augmented_user_message = f"{user_text}\n(Note: Current attached files:\n{attached_context})"

    # Append to history
    session["history"].append({"role": "user", "content": augmented_user_message})

    # Keep conversation history bounded to last 10 messages for speed & tokens
    if len(session["history"]) > 10:
        session["history"] = session["history"][-10:]

    status_msg = await update.message.reply_text("🤔 *Analyzing context...*", parse_mode="Markdown")

    loop = asyncio.get_running_loop()
    ai_response = await loop.run_in_executor(
        None,
        generate_conversational_response,
        session["history"],
        config.GEMINI_API_KEY,
        config.GEMINI_MODEL
    )

    # Save assistant response to history
    session["history"].append({"role": "assistant", "content": ai_response})

    # Send response to Telegram (chunked if long)
    await status_msg.delete()
    chunks = split_message(ai_response, max_length=4000)
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception:
            # Fallback to plain text if markdown formatting is invalid
            await update.message.reply_text(chunk, disable_web_page_preview=True)

    # If this was an ATS evaluation, broadcast to Discord / multi-channels as well
    if "ATS Score:" in ai_response or "CANDIDATE ATS RANKINGS" in ai_response:
        dispatched = dispatch_to_all_configured_channels(
            report_telegram=ai_response,
            report_discord=ai_response,
            config_obj=config,
            current_chat_id=None
        )
        active_dispatches = [k for k, v in dispatched.items() if v]
        if active_dispatches:
            await update.message.reply_text(f"📡 *Broadcast dispatched to:* {', '.join(active_dispatches)}", parse_mode="Markdown")


def main():
    """Main entrypoint for Telegram Bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN is missing in .env")
        return

    print("🤖 Starting Context-Aware Conversational ATS Bot...")
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler(["start", "new"], start_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("demo", demo_command))
    app.add_handler(CommandHandler("analyze", lambda u, c: process_ai_interaction(u, u.effective_chat.id, get_session(u.effective_chat.id), "Please analyze all attached resumes against the Job Description(s).")))

    # Natural conversation & file handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Bot is LIVE! Contextual chat active. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
