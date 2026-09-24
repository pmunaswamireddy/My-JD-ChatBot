import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand
)
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
    classify_document,
    extract_candidate_scores_for_chart
)
from charts import generate_ats_chart
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

# Persistent Main Keyboard
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🚀 Analyze Resumes"), KeyboardButton("📊 Status")],
        [KeyboardButton("🧪 Instant Demo"), KeyboardButton("🧹 Clear Session")],
        [KeyboardButton("ℹ️ Help & Guide")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# User sessions: {chat_id: {"history": [...], "files": [...]}}
user_sessions: Dict[int, Dict[str, Any]] = {}

def get_session(chat_id: int) -> Dict[str, Any]:
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            "history": [],
            "files": []
        }
    return user_sessions[chat_id]


async def post_init(application):
    """Register official bot commands with Telegram."""
    commands = [
        BotCommand("analyze", "Evaluate resumes against JD(s) (aliases: /analyse, /eval)"),
        BotCommand("status", "View uploaded JDs and Resumes count"),
        BotCommand("demo", "Run live demo with sample files"),
        BotCommand("clear", "Reset session and uploaded files"),
        BotCommand("help", "How to use this bot")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered successfully with Telegram!")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start and /new."""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"history": [], "files": []}
    
    welcome_text = (
        "👋 *Welcome to AI Job & Resume ATS Matcher Bot!*\n\n"
        "I evaluate multiple resumes against your Job Description(s) using Gemini AI, "
        "calculating exact ATS scores, missing skills, and curated courses with clickable links.\n\n"
        "⚡ *Quick Navigation:* Use the persistent buttons below or send files anytime!\n\n"
        "📁 *Supported Formats:* `.pdf`, `.docx`, `.doc`, `.txt`, `.rtf`, `.md`\n\n"
        "1️⃣ Drag & drop your **Job Description (JD)**\n"
        "2️⃣ Drag & drop **Candidate Resumes** (single or batch)\n"
        "3️⃣ Tap *🚀 Analyze Resumes* or send `/analyze` (or `/analyse`)!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /clear and '🧹 Clear Session'."""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"history": [], "files": []}
    await update.message.reply_text(
        "🧹 *Session cleared!* All previous files and chat memory have been reset.\n"
        "Upload your new JD and resumes to start fresh.",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /status and '📊 Status'."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    files = session.get("files", [])
    history_count = len(session.get("history", []))

    jds = [f["name"] for f in files if f["type"] == "job_description"]
    resumes = [f["name"] for f in files if f["type"] == "resume"]

    status_lines = [
        "📊 *Current Session Overview:*",
        f"• *Messages in Memory:* `{history_count}`",
        f"• *Job Descriptions ({len(jds)}):* {', '.join(jds) if jds else '_None uploaded yet_'}",
        f"• *Candidate Resumes ({len(resumes)}):* {', '.join(resumes) if resumes else '_None uploaded yet_'}"
    ]

    channels = ["Telegram"]
    if config.DISCORD_WEBHOOK_URL:
        channels.append("Discord")
    if config.SLACK_WEBHOOK_URL:
        channels.append("Slack")
    status_lines.append(f"• *Active Output Channels:* {', '.join(channels)}")

    if not files:
        status_lines.append("\n💡 _Drop your JD and resume files here or tap '🧪 Instant Demo'!_")
    else:
        status_lines.append("\n💡 _Tap '🚀 Analyze Resumes' to evaluate now!_")

    await update.message.reply_text("\n".join(status_lines), parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def demo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /demo and '🧪 Instant Demo'."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    sample_dir = Path(__file__).resolve().parent / "sample_data"

    jd_file = sample_dir / "sample_jd.txt"
    r1_file = sample_dir / "resume_alex_rivers.txt"
    r2_file = sample_dir / "resume_sarah_chen.txt"

    if not jd_file.exists() or not r1_file.exists():
        await update.message.reply_text("❌ Sample files not found.", reply_markup=MAIN_KEYBOARD)
        return

    session["files"] = [
        {"name": "Senior_AI_Engineer_JD.txt", "type": "job_description", "text": extract_text_from_file(str(jd_file))},
        {"name": "Alex_Rivers_Resume.docx", "type": "resume", "text": extract_text_from_file(str(r1_file))},
        {"name": "Sarah_Chen_Resume.docx", "type": "resume", "text": extract_text_from_file(str(r2_file))}
    ]

    await update.message.reply_text(
        "🚀 *Demo Loaded:* 1 Job Description + 2 Candidate Resumes.\n"
        "⏳ *Evaluating with Gemini AI...*",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD
    )

    prompt = "Please evaluate all candidate resumes against the Job Description and provide the structured ATS rankings, missing skills, and course recommendations."
    await process_ai_interaction(update, chat_id, session, prompt)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /help and 'ℹ️ Help & Guide'."""
    help_text = (
        "ℹ️ *How to use JD & Resume ATS Matcher Bot:*\n\n"
        "1. **Upload Files:** Drag & drop `.pdf`, `.docx`, `.doc`, or `.txt` files directly into this chat.\n"
        "2. **Auto-Detection:** The bot automatically recognizes which files are JDs and which are Resumes.\n"
        "3. **Analyze:** Tap **🚀 Analyze Resumes** or send `/analyze` (or `/analyse`).\n"
        "4. **Chat Naturally:** You can ask questions anytime (e.g. *\"Who has the best Python skills?\"* or *\"Why did candidate 2 score lower?\"*)\n\n"
        "🔘 *Persistent Buttons:*\n"
        "• **🚀 Analyze Resumes** — Triggers full ATS evaluation\n"
        "• **📊 Status** — Check loaded files\n"
        "• **🧪 Instant Demo** — Run 3-second demo\n"
        "• **🧹 Clear Session** — Start fresh"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles uploaded files (.pdf, .docx, .doc, .txt, .rtf, .md)."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    doc = update.message.document
    filename = doc.file_name or "document"
    ext = Path(filename).suffix.lower()

    if ext not in [".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".odt", ".csv", ".html"]:
        await update.message.reply_text(
            f"⚠️ Unsupported format `{ext}`. Supported formats: `.pdf`, `.docx`, `.doc`, `.txt`, `.rtf`, `.md`.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD
        )
        return

    wait_msg = await update.message.reply_text(f"📥 Reading `{filename}`...", parse_mode="Markdown")

    extracted_text = ""
    # Download with retry and extended timeout to handle parallel file uploads
    for attempt in range(2):
        try:
            tg_file = await doc.get_file(read_timeout=60, write_timeout=60, connect_timeout=30)
            file_bytes = await tg_file.download_as_bytearray()
            extracted_text = extract_text_from_bytes(bytes(file_bytes), filename)
            if extracted_text:
                break
        except Exception as e:
            if attempt == 1:
                logger.error(f"Error downloading {filename}: {e}")
                await wait_msg.edit_text(f"⚠️ Failed to download `{filename}` (timeout). Please send it again.")
                return
            await asyncio.sleep(1)

    if not extracted_text:
        await wait_msg.edit_text(f"❌ Could not extract text from `{filename}`.")
        return

    doc_type = classify_document(extracted_text, filename)
    label = "Job Description" if doc_type == "job_description" else "Candidate Resume"

    # Replace existing file with same name or add
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
        f"🔍 *Identified as:* `{label}`\n\n"
        f"📂 *Total Attachments:* `{len(jds)}` JD(s), `{len(resumes)}` Resume(s).\n\n"
        "👉 Tap *🚀 Analyze Resumes* or send more files!",
        parse_mode="Markdown"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text messages and button clicks."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    text = update.message.text.strip()
    text_lower = text.lower()

    # 1. Button or Command Aliases
    if text in ["🚀 Analyze Resumes", "Analyze", "Analyse", "/analyze", "/analyse", "/eval", "/evaluate", "/rank", "/match"] or text_lower in ["analyze", "analyse", "evaluate", "analyze these", "analyse these"]:
        files = session.get("files", [])
        if not files:
            await update.message.reply_text(
                "❌ No files uploaded yet!\n"
                "Please upload at least 1 Job Description and 1 Resume (or tap '🧪 Instant Demo').",
                reply_markup=MAIN_KEYBOARD
            )
            return
        await process_ai_interaction(update, chat_id, session, "Please evaluate all attached candidate resumes against the Job Description(s) and provide the structured ATS rankings, missing skills, and course recommendations.")
        return

    if text in ["📊 Status", "Status", "/status"] or text_lower == "status":
        await status_command(update, context)
        return

    if text in ["🧪 Instant Demo", "Demo", "/demo"] or text_lower == "demo":
        await demo_command(update, context)
        return

    if text in ["🧹 Clear Session", "Clear", "/clear", "/reset"] or text_lower in ["clear", "reset"]:
        await clear_command(update, context)
        return

    if text in ["ℹ️ Help & Guide", "Help", "/help"] or text_lower in ["help", "guide"]:
        await help_command(update, context)
        return

    # 2. Conversational greetings
    if text_lower in ["hi", "hello", "hey", "hola", "start", "good morning", "good evening"]:
        await update.message.reply_text(
            f"👋 Hello! Ready to help you review candidates and match resumes against your Job Descriptions.\n\n"
            f"You can attach files (PDF, DOCX, TXT) or tap any button below to get started!",
            reply_markup=MAIN_KEYBOARD
        )
        return

    # 3. General conversational queries
    await process_ai_interaction(update, chat_id, session, text)


async def process_ai_interaction(update: Update, chat_id: int, session: Dict[str, Any], user_text: str):
    """Processes conversational message with attached documents context."""
    attached_context = ""
    if session.get("files"):
        attached_context = "\n=== ATTACHED DOCUMENTS IN THIS SESSION ===\n"
        for idx, f in enumerate(session["files"], 1):
            type_label = "JOB DESCRIPTION" if f["type"] == "job_description" else "CANDIDATE RESUME"
            attached_context += f"\n--- DOCUMENT #{idx}: {f['name']} ({type_label}) ---\n{f['text']}\n"

    augmented_user_message = user_text
    if attached_context and len(session["history"]) == 0:
        augmented_user_message = f"{user_text}\n{attached_context}"
    elif attached_context:
        augmented_user_message = f"{user_text}\n(Note: Attached files context:\n{attached_context})"

    session["history"].append({"role": "user", "content": augmented_user_message})

    if len(session["history"]) > 10:
        session["history"] = session["history"][-10:]

    status_msg = await update.message.reply_text("🤔 *Analyzing context with Gemini AI...*", parse_mode="Markdown")

    loop = asyncio.get_running_loop()
    ai_response = await loop.run_in_executor(
        None,
        generate_conversational_response,
        session["history"],
        config.GEMINI_API_KEY,
        config.GEMINI_MODEL
    )

    session["history"].append({"role": "assistant", "content": ai_response})

    try:
        await status_msg.delete()
    except Exception:
        pass

    chunks = split_message(ai_response, max_length=4000)
    for chunk in chunks:
        try:
            await update.message.reply_text(
                chunk,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=MAIN_KEYBOARD
            )
        except Exception:
            await update.message.reply_text(
                chunk,
                disable_web_page_preview=True,
                reply_markup=MAIN_KEYBOARD
            )

    # Multi-channel broadcast & Visual Graph Generation
    if "ATS Score:" in ai_response or "CANDIDATE ATS RANKINGS" in ai_response:
        # Generate & Send High-Res Comparison Bar Chart
        try:
            candidates_for_chart = extract_candidate_scores_for_chart(ai_response)
            if candidates_for_chart:
                jds = [f["name"] for f in session.get("files", []) if f["type"] == "job_description"]
                chart_title = jds[0].replace(".txt", "").replace(".docx", "").replace(".pdf", "") if jds else "ATS Candidate Fit"
                chart_bytes = generate_ats_chart(candidates_for_chart, chart_title)
                if chart_bytes:
                    await update.message.reply_photo(
                        photo=chart_bytes,
                        caption="📊 *ATS Candidate Compatibility Chart* (Higher score = Better fit)",
                        parse_mode="Markdown"
                    )
        except Exception as e:
            logger.error(f"Error sending ATS chart: {e}")

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

    print("🤖 Starting Upgraded ATS Bot with persistent buttons & command aliases...")
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(30)
        .build()
    )

    # Command Handlers with full spelling and aliases support
    app.add_handler(CommandHandler(["start", "new"], start_command))
    app.add_handler(CommandHandler(["clear", "reset"], clear_command))
    app.add_handler(CommandHandler(["status"], status_command))
    app.add_handler(CommandHandler(["demo", "test"], demo_command))
    app.add_handler(CommandHandler(["help", "guide"], help_command))
    app.add_handler(CommandHandler(["analyze", "analyse", "eval", "evaluate", "rank", "match"], lambda u, c: handle_text(u, c)))

    # Document & Text handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Bot is LIVE with persistent buttons! Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
