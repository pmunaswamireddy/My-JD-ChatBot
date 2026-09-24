import asyncio
import io
import logging
import sys
import re
from pathlib import Path
from typing import Dict, Any, List

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from google import genai
import config
from parser import extract_text_from_bytes, extract_text_from_file
from analyzer import (
    generate_conversational_response,
    classify_document,
    extract_candidate_scores_for_chart
)
from charts import generate_ats_chart
from pdf_report import generate_audit_pdf
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

# Persistent Main Bottom Keyboard
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🚀 Analyze Resumes"), KeyboardButton("📊 Status")],
        [KeyboardButton("🧪 Instant Demo"), KeyboardButton("🧹 Clear Session")],
        [KeyboardButton("🔑 Set API Key"), KeyboardButton("ℹ️ Help & Guide")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

# Interactive Inline Action Buttons (Attached directly under analysis message)
def get_evaluation_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 View Score Chart", callback_data="cb_chart"),
            InlineKeyboardButton("📋 Matrix Comparison", callback_data="cb_matrix")
        ],
        [
            InlineKeyboardButton("🎯 Interview Questions", callback_data="cb_interview"),
            InlineKeyboardButton("💡 Recommended Courses", callback_data="cb_courses")
        ],
        [
            InlineKeyboardButton("📄 Download PDF Dossier", callback_data="cb_pdf")
        ]
    ])

# User sessions: {chat_id: {"history": [...], "files": [...], "latest_report": str, "awaiting_key": bool}}
user_sessions: Dict[int, Dict[str, Any]] = {}

def get_session(chat_id: int) -> Dict[str, Any]:
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            "history": [],
            "files": [],
            "latest_report": "",
            "awaiting_key": False
        }
    return user_sessions[chat_id]


async def post_init(application):
    """Register official bot commands with Telegram."""
    commands = [
        BotCommand("analyze", "Evaluate candidates against JDs (or /analyse)"),
        BotCommand("status", "View uploaded JDs and Resumes count"),
        BotCommand("setkey", "Update Gemini API key: /setkey <YOUR_KEY>"),
        BotCommand("demo", "Run live demo with sample files"),
        BotCommand("clear", "Reset session and uploaded files"),
        BotCommand("help", "How to use this bot")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered successfully with Telegram!")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start and /new."""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"history": [], "files": [], "latest_report": "", "awaiting_key": False}
    
    welcome_text = (
        "👋 *Welcome to AI Multi-JD & Resume ATS Intelligence Bot!*\n\n"
        "I evaluate multiple resumes against single or multiple Job Descriptions using Gemini AI, "
        "calculating exact ATS scores, missing skills, and hyperlinked courses.\n\n"
        "⚡ *Quick Navigation:* Use the buttons below or upload files anytime!\n\n"
        "📁 *Supported Formats:* `.pdf`, `.docx`, `.doc`, `.txt`, `.rtf`, `.md`\n\n"
        "1️⃣ Drag & drop your **Job Description(s)**\n"
        "2️⃣ Drag & drop **Candidate Resumes** (single or batch)\n"
        "3️⃣ Tap *🚀 Analyze Resumes* or send `/analyze` (or `/analyse`)!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def set_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /setkey <NEW_KEY> or prompts for key."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)

    # Check if key was passed as argument: /setkey AIzaSy...
    if context.args and len(context.args) > 0:
        new_key = context.args[0].strip()
        await verify_and_save_api_key(update, new_key)
    else:
        session["awaiting_key"] = True
        await update.message.reply_text(
            "🔑 *Update Gemini API Key*\n\n"
            "Please paste your new Gemini API key below, or type:\n"
            "`/setkey YOUR_NEW_KEY`\n\n"
            "_(Free key from: https://aistudio.google.com/app/apikey)_",
            parse_mode="Markdown"
        )


async def verify_and_save_api_key(update: Update, new_key: str):
    """Verifies and persists new Gemini API key."""
    wait_msg = await update.message.reply_text("⏳ *Validating Gemini API key with Google AI Studio...*", parse_mode="Markdown")

    try:
        test_client = genai.Client(api_key=new_key)
        resp = test_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents="Say 'OK'"
        )
        if not resp.text:
            raise Exception("No response received from model.")
    except Exception as e:
        await wait_msg.edit_text(
            f"❌ *Invalid API Key:* The key could not be verified by Google Gemini.\n\n"
            f"Details: `{e}`\n\n"
            f"Please double check and try again.",
            parse_mode="Markdown"
        )
        return

    # Update in memory
    config.GEMINI_API_KEY = new_key

    # Persist in .env file
    env_path = Path(__file__).resolve().parent / ".env"
    try:
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "GEMINI_API_KEY=" in content:
                content = re.sub(r"GEMINI_API_KEY=.*", f"GEMINI_API_KEY={new_key}", content)
            else:
                content = f"GEMINI_API_KEY={new_key}\n" + content
            env_path.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving key to .env: {e}")

    session = get_session(update.effective_chat.id)
    session["awaiting_key"] = False

    await wait_msg.edit_text(
        "✅ *Gemini API Key Verified & Updated Successfully!*\n\n"
        "Your new key is now active and saved permanently.",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /clear and '🧹 Clear Session'."""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"history": [], "files": [], "latest_report": "", "awaiting_key": False}
    await update.message.reply_text(
        "🧹 *Session cleared!* All previous files and chat memory have been reset.\n"
        "Upload your new JDs and resumes to start fresh.",
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

    key_status = "✅ Active" if config.GEMINI_API_KEY else "❌ Missing"
    status_lines.append(f"• *Gemini Key Status:* {key_status}")

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
        "2. **Multi-JD Support:** If you send multiple JDs, the bot separates each evaluation and provides candidate-to-role matching.\n"
        "3. **Analyze:** Tap **🚀 Analyze Resumes** or send `/analyze` (or `/analyse`).\n"
        "4. **Change API Key:** Send `/setkey YOUR_KEY` or tap **🔑 Set API Key**.\n"
        "5. **Interactive Buttons:** Tap the buttons below evaluation messages to view Charts, Matrix comparisons, or download PDF Dossiers!\n\n"
        "🔘 *Persistent Buttons:*\n"
        "• **🚀 Analyze Resumes** — Triggers ATS evaluation\n"
        "• **📊 Status** — Check loaded files\n"
        "• **🧪 Instant Demo** — Run 3-second demo\n"
        "• **🔑 Set API Key** — Update Gemini key on the fly\n"
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
    """Handles text messages, button clicks, and key updates."""
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    text = update.message.text.strip()
    text_lower = text.lower()

    # Check if awaiting API key
    if session.get("awaiting_key"):
        if text.startswith("/"):
            session["awaiting_key"] = False
        else:
            await verify_and_save_api_key(update, text)
            return

    if text in ["🔑 Set API Key", "Set API Key", "/setkey", "/apikey"]:
        await set_key_command(update, context)
        return

    if text in ["🚀 Analyze Resumes", "Analyze", "Analyse", "/analyze", "/analyse", "/eval", "/evaluate", "/rank", "/match"] or text_lower in ["analyze", "analyse", "evaluate", "analyze these", "analyse these"]:
        files = session.get("files", [])
        if not files:
            await update.message.reply_text(
                "❌ No files uploaded yet!\n"
                "Please upload at least 1 Job Description and 1 Resume (or tap '🧪 Instant Demo').",
                reply_markup=MAIN_KEYBOARD
            )
            return
        await process_ai_interaction(update, chat_id, session, "Please evaluate all candidate resumes against the Job Description(s). If multiple JDs are uploaded, separate the evaluations for each JD, and provide candidate-to-role placement.")
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

    if text_lower in ["hi", "hello", "hey", "hola", "start", "good morning", "good evening"]:
        await update.message.reply_text(
            "👋 Hello! Ready to evaluate candidate resumes against your Job Descriptions with real ATS scoring.\n\n"
            "Drop files (.pdf, .docx, .txt) or tap any button below to get started!",
            reply_markup=MAIN_KEYBOARD
        )
        return

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
    session["latest_report"] = ai_response

    try:
        await status_msg.delete()
    except Exception:
        pass

    chunks = split_message(ai_response, max_length=4000)
    for idx, chunk in enumerate(chunks):
        is_last_chunk = (idx == len(chunks) - 1)
        inline_kb = get_evaluation_inline_keyboard() if (is_last_chunk and ("ATS Score:" in ai_response or "SNAPSHOT" in ai_response)) else None

        try:
            await update.message.reply_text(
                chunk,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=inline_kb or MAIN_KEYBOARD
            )
        except Exception:
            await update.message.reply_text(
                chunk,
                disable_web_page_preview=True,
                reply_markup=inline_kb or MAIN_KEYBOARD
            )

    # Multi-channel broadcast & Visual Graph Generation
    if "ATS Score:" in ai_response or "CANDIDATE ATS RANKINGS" in ai_response:
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


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles clicks on interactive inline buttons below messages."""
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    latest_report = session.get("latest_report", "")

    if query.data == "cb_chart":
        candidates = extract_candidate_scores_for_chart(latest_report)
        if candidates:
            jds = [f["name"] for f in session.get("files", []) if f["type"] == "job_description"]
            title = jds[0] if jds else "Candidate Fit Ranking"
            chart_bytes = generate_ats_chart(candidates, title)
            await query.message.reply_photo(
                photo=chart_bytes,
                caption="📊 *Candidate ATS Compatibility Chart*",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text("ℹ️ Please run an analysis first by tapping '🚀 Analyze Resumes'.")

    elif query.data == "cb_matrix":
        if latest_report:
            # Extract or display the candidate comparison matrix
            matrix_match = re.search(r"📋 \*CANDIDATE COMPARISON MATRIX\*[\s\S]*?```([\s\S]*?)```", latest_report)
            if matrix_match:
                table_text = matrix_match.group(1).strip()
                await query.message.reply_text(
                    f"📋 *CANDIDATE COMPARISON MATRIX:*\n\n```\n{table_text}\n```",
                    parse_mode="Markdown"
                )
            else:
                prompt = "Please output ONLY the Candidate Comparison Matrix table comparing all evaluated candidates with their ATS Scores, Tech fit %, and status."
                await process_ai_interaction(query, chat_id, session, prompt)
        else:
            await query.message.reply_text("ℹ️ Please run an analysis first to view the matrix.")

    elif query.data == "cb_pdf":
        if latest_report:
            wait = await query.message.reply_text("📄 *Compiling Executive Audit PDF Report...*", parse_mode="Markdown")
            jds = [f["name"] for f in session.get("files", []) if f["type"] == "job_description"]
            title = jds[0] if jds else "Executive ATS Dossier"
            pdf_bytes = generate_audit_pdf(latest_report, title)
            await wait.delete()
            await query.message.reply_document(
                document=io.BytesIO(pdf_bytes),
                filename="Executive_ATS_Audit_Report.pdf",
                caption="📄 *Executive ATS Candidate Audit Report (PDF)*",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text("ℹ️ Run an analysis first before downloading PDF.")

    elif query.data == "cb_interview":
        if latest_report:
            prompt = "Based on the candidates evaluated and their specific missing skills, generate 3 rigorous technical interview questions and 2 behavioral questions tailored to vet their weak areas, along with model answers."
            await process_ai_interaction(query, chat_id, session, prompt)
        else:
            await query.message.reply_text("ℹ️ Run an analysis first to generate tailored interview questions.")

    elif query.data == "cb_courses":
        if latest_report:
            prompt = "Provide an enriched master learning curriculum with direct working hyperlinks (Coursera, edX, Udemy, freeCodeCamp, Harvard CS50, DeepLearning.AI) for all missing skills found across candidates."
            await process_ai_interaction(query, chat_id, session, prompt)
        else:
            await query.message.reply_text("ℹ️ Run an analysis first to see course recommendations.")


def main():
    """Main entrypoint for Telegram Bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN is missing in .env")
        return

    print("🤖 Starting Upgraded ATS Bot with Inline Buttons, Key Switcher & Matrix Button...")
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(30)
        .build()
    )

    # Command Handlers
    app.add_handler(CommandHandler(["start", "new"], start_command))
    app.add_handler(CommandHandler(["clear", "reset"], clear_command))
    app.add_handler(CommandHandler(["status"], status_command))
    app.add_handler(CommandHandler(["demo", "test"], demo_command))
    app.add_handler(CommandHandler(["help", "guide"], help_command))
    app.add_handler(CommandHandler(["setkey", "apikey"], set_key_command))
    app.add_handler(CommandHandler(["analyze", "analyse", "eval", "evaluate", "rank", "match"], lambda u, c: handle_text(u, c)))

    # Inline Button Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Document & Text handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Bot is LIVE with Matrix Comparison and Key Changer! Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
