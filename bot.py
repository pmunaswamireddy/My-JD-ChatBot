import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any

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
    analyze_resumes_with_gemini,
    format_report_for_telegram,
    format_report_for_discord
)
from dispatchers import dispatch_to_all_configured_channels, send_to_telegram

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# User sessions stored in-memory: {chat_id: {"jd": str, "resumes": [{"name": str, "text": str}]}}
user_sessions: Dict[int, Dict[str, Any]] = {}

def get_session(chat_id: int) -> Dict[str, Any]:
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {"jd": "", "resumes": []}
    return user_sessions[chat_id]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start and /new."""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"jd": "", "resumes": []}
    
    welcome_text = (
        "🤖 *Welcome to JD & Resume ATS Matcher Bot!*\n\n"
        "I evaluate multiple resumes against your Job Description with Gemini AI, "
        "calculating ATS match scores, missing skills, improvement tips, and curated courses with direct links.\n\n"
        "📋 *Quick Workflow:*\n"
        "1️⃣ Send your *Job Description (JD)* (as a message or attach `.pdf`, `.docx`, `.txt`)\n"
        "2️⃣ Send *Candidate Resumes* (attach 1 or multiple `.pdf`, `.docx`, `.txt` files)\n"
        "3️⃣ Type /analyze to process and generate rankings!\n\n"
        "💡 *Bonus Commands:*\n"
        "• /demo — Test instantly with built-in sample JD & 2 resumes\n"
        "• /status — Check current uploaded JD & resumes count\n"
        "• /clear — Reset session"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /help."""
    help_text = (
        "📖 *How to use this Bot:*\n\n"
        "1. *Upload Job Description:* Send a document (`.pdf`, `.docx`, `.txt`) or paste text.\n"
        "2. *Upload Resumes:* Send candidate resume documents one by one.\n"
        "3. *Analyze:* Send `/analyze` when you're ready.\n"
        "4. *Multi-platform Broadcast:* If Discord or Slack webhooks are configured in `.env`, "
        "the final rankings will also be automatically pushed there!\n\n"
        "• /start - Begin new session\n"
        "• /demo - Run instant demo with sample data\n"
        "• /status - View uploaded count\n"
        "• /clear - Clear files and start over"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /status."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    jd = session.get("jd", "")
    resumes = session.get("resumes", [])

    jd_status = f"✅ Loaded ({len(jd.split())} words)" if jd else "❌ Not provided yet"
    resumes_status = f"{len(resumes)} file(s) attached" if resumes else "0 attached"
    
    # Active integrations
    integrations = ["Telegram"]
    if config.DISCORD_WEBHOOK_URL:
        integrations.append("Discord")
    if config.SLACK_WEBHOOK_URL:
        integrations.append("Slack")
    if config.GOOGLE_CHAT_WEBHOOK_URL:
        integrations.append("Google Chat")
    if config.WHATSAPP_WEBHOOK_URL:
        integrations.append("WhatsApp")

    status_text = (
        "📊 *Current Session Status:*\n"
        f"• *Job Description:* {jd_status}\n"
        f"• *Resumes Uploaded:* `{resumes_status}`\n"
        f"• *Active Output Channels:* {', '.join(integrations)}\n\n"
        + ("Ready! Type /analyze to process." if (jd and resumes) else "Please upload your JD and at least 1 resume.")
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /clear."""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"jd": "", "resumes": []}
    await update.message.reply_text("🧹 Session cleared! Send a new Job Description to begin.", parse_mode="Markdown")


async def demo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instantly loads sample JD and 2 resumes and runs analysis."""
    chat_id = update.effective_chat.id
    sample_dir = Path(__file__).resolve().parent / "sample_data"
    
    jd_file = sample_dir / "sample_jd.txt"
    r1_file = sample_dir / "resume_alex_rivers.txt"
    r2_file = sample_dir / "resume_sarah_chen.txt"

    if not jd_file.exists() or not r1_file.exists():
        await update.message.reply_text("❌ Sample files not found in `sample_data/` folder.", parse_mode="Markdown")
        return

    jd_text = extract_text_from_file(str(jd_file))
    r1_text = extract_text_from_file(str(r1_file))
    r2_text = extract_text_from_file(str(r2_file))

    session = get_session(chat_id)
    session["jd"] = jd_text
    session["resumes"] = [
        {"name": "Alex_Rivers_Resume.txt", "text": r1_text},
        {"name": "Sarah_Chen_Resume.txt", "text": r2_text}
    ]

    await update.message.reply_text(
        "🚀 *Demo Loaded Successfully!*\n"
        "• *JD:* Senior Full-Stack AI Engineer\n"
        "• *Resumes:* Alex Rivers (Senior), Sarah Chen (Junior)\n\n"
        "⏳ *Analyzing candidate ATS scores & recommended courses with Gemini AI...*",
        parse_mode="Markdown"
    )

    await run_analysis(update, chat_id, session)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming file uploads (PDF, DOCX, TXT)."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    doc = update.message.document
    filename = doc.file_name or "document"
    
    # Check supported extensions
    ext = Path(filename).suffix.lower()
    if ext not in [".pdf", ".docx", ".doc", ".txt", ".md"]:
        await update.message.reply_text(
            f"⚠️ Unsupported format `{ext}`. Please upload `.pdf`, `.docx`, or `.txt` files.",
            parse_mode="Markdown"
        )
        return

    # Download file in memory
    status_msg = await update.message.reply_text(f"📥 Downloading `{filename}`...", parse_mode="Markdown")
    try:
        tg_file = await doc.get_file()
        file_bytes = await tg_file.download_as_bytearray()
        extracted_text = extract_text_from_bytes(bytes(file_bytes), filename)
        
        if not extracted_text:
            await status_msg.edit_text(f"❌ Could not extract text from `{filename}`. Please check the file.")
            return

        # Assign to JD if not already set, otherwise add to resumes
        if not session["jd"]:
            session["jd"] = extracted_text
            await status_msg.edit_text(
                f"✅ *Job Description Loaded!* (`{filename}`)\n\n"
                f"Now send candidate resumes (PDF, DOCX, TXT). You can send multiple files.\n"
                f"When done, type /analyze.",
                parse_mode="Markdown"
            )
        else:
            session["resumes"].append({"name": filename, "text": extracted_text})
            count = len(session["resumes"])
            await status_msg.edit_text(
                f"📄 *Resume Added #{count}:* `{filename}`\n\n"
                f"Send another resume or type /analyze to evaluate.",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Error processing file: {e}")
        await status_msg.edit_text(f"❌ Error downloading file: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles plain text messages (used for pasting JD)."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    text = update.message.text.strip()

    if not session["jd"]:
        session["jd"] = text
        await update.message.reply_text(
            "✅ *Job Description Text Received!*\n\n"
            "Now upload candidate resumes (`.pdf`, `.docx`, or `.txt` files).\n"
            "Send /analyze when ready.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "💡 You have already loaded a Job Description.\n"
            f"Currently holding `{len(session['resumes'])}` resume(s).\n\n"
            "• Attach a resume file (`.pdf`/`.docx`/`.txt`) to add candidates.\n"
            "• Type /analyze to process.\n"
            "• Type /clear to reset.",
            parse_mode="Markdown"
        )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /analyze command."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)

    if not session.get("jd"):
        await update.message.reply_text(
            "❌ No Job Description found! Please send your JD first (text or document).",
            parse_mode="Markdown"
        )
        return

    if not session.get("resumes"):
        await update.message.reply_text(
            "❌ No candidate resumes found! Please upload at least one resume (`.pdf`, `.docx`, or `.txt`).",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"⏳ *Processing {len(session['resumes'])} resume(s) with Gemini AI...*\n"
        "Calculating ATS scores, missing skills, and course recommendations...",
        parse_mode="Markdown"
    )

    await run_analysis(update, chat_id, session)


async def run_analysis(update: Update, chat_id: int, session: Dict[str, Any]):
    """Executes the analysis, replies in Telegram and broadcasts to configured channels."""
    jd_text = session["jd"]
    resumes = session["resumes"]

    # Run analysis (synchronous call offloaded to thread)
    loop = asyncio.get_running_loop()
    analysis_data = await loop.run_in_executor(
        None,
        analyze_resumes_with_gemini,
        jd_text,
        resumes,
        config.GEMINI_API_KEY,
        config.GEMINI_MODEL
    )

    # Format reports
    telegram_report = format_report_for_telegram(analysis_data)
    discord_report = format_report_for_discord(analysis_data)

    # Send directly to the Telegram user
    send_to_telegram(config.TELEGRAM_BOT_TOKEN, str(chat_id), telegram_report)

    # Broadcast to other channels (Discord, Slack, Google Chat, WhatsApp)
    dispatched = dispatch_to_all_configured_channels(
        report_telegram=telegram_report,
        report_discord=discord_report,
        config_obj=config,
        current_chat_id=None # Already sent above
    )

    # Notify if multi-platform dispatch occurred
    active_dispatches = [k for k, v in dispatched.items() if v]
    if active_dispatches:
        await update.message.reply_text(
            f"📡 *Multi-channel broadcast sent to:* {', '.join(active_dispatches)}",
            parse_mode="Markdown"
        )


def main():
    """Main entrypoint for Telegram Bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        print("\n" + "="*60)
        print("⚠️  TELEGRAM_BOT_TOKEN is not set in .env!")
        print("1. Open Telegram and search for @BotFather")
        print("2. Send /newbot, give it a name, and copy the HTTP API token")
        print("3. Paste it into .env: TELEGRAM_BOT_TOKEN=your_token_here")
        print("="*60 + "\n")
        return

    print("🤖 Starting Telegram ATS Match Bot...")
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler(["start", "new"], start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("demo", demo_command))
    app.add_handler(CommandHandler("analyze", analyze_command))

    # Document & Text handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Bot is LIVE and listening for messages! Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
