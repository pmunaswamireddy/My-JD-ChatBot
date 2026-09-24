# 🎯 AI Job Description & Resume ATS Matcher Bot

An AI-powered multi-channel recruiting assistant built for modern hiring teams. Upload your **Job Description (JD)** and batch upload **multiple candidate resumes** directly inside **Telegram**, and receive instant, high-impact **ATS Match Scores**, matched vs. missing skills, actionable resume improvement suggestions, and curated course recommendations with live direct hyperlinks.

Supports multi-channel broadcasts to **Telegram**, **Discord**, **Slack**, **Google Chat**, and **WhatsApp**.

---

## ⚡ Core Features

- 📄 **Universal Document Ingestion:** Supports `.pdf`, `.docx`, and `.txt` / `.md` files or raw text input.
- 🧠 **Google Gemini AI Evaluation:** Deep semantic analysis calculating precise ATS fit scores (0-100%).
- 🎯 **Direct & Organized Output:**
  - Concise Job Description overview (Role, Experience, Core Stack).
  - Candidates ranked by ATS compatibility.
  - Present vs. Missing skills breakdown.
  - Concrete feature improvements.
  - Curated course recommendations with verified direct URLs (Coursera, Udemy, edX, etc.).
- 🤖 **Telegram Bot Direct Interaction:** Upload files straight into chat with intuitive commands (`/start`, `/demo`, `/status`, `/analyze`, `/clear`).
- 📡 **Multi-Platform Dispatcher:** Real-time webhooks broadcasting results simultaneously to Discord, Slack, Google Chat, and WhatsApp.
- 🛡️ **Zero-Friction Hackathon Mode:** Built-in sample dataset and fallback engine so demos run seamlessly even offline or without API keys.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│             Job Description & Resumes Ingestion        │
│       (Telegram Bot Chat or Batch File System)         │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│              Document Parser (PDF, DOCX, TXT)          │
│               pypdf + python-docx + io.BytesIO         │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Gemini AI ATS Scoring Engine             │
│            Google Gemini 2.5 Flash + Heuristics        │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                 Multi-Channel Dispatcher               │
├──────────────┬──────────────┬──────────────┬───────────┤
│   Telegram   │   Discord    │    Slack     │ GoogleChat│
│  Bot Message │   Webhook    │   Webhook    │  Webhook  │
└──────────────┴──────────────┴──────────────┴───────────┘
```

---

## 🚀 Quick Setup (2 Minutes)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Copy `.env.example` to `.env` and fill in your keys:
```ini
# Free key: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key

# Get from @BotFather on Telegram (send /newbot)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# (Optional) Multi-platform webhook channels
DISCORD_WEBHOOK_URL=
SLACK_WEBHOOK_URL=
GOOGLE_CHAT_WEBHOOK_URL=
WHATSAPP_WEBHOOK_URL=
```

---

## 🧪 Testing & Instant Live Demo

### Instant Command-Line Test
Run the end-to-end pipeline test without opening Telegram:
```bash
python test_system.py
```

### Running the Live Telegram Bot
```bash
python bot.py
```
Then open your Telegram bot and use:
- `/start` — Start a fresh session.
- `/demo` — Run an instant demo using pre-loaded sample JD and 2 candidate resumes!
- Attach your **Job Description** file (`.pdf`, `.docx`, or `.txt`).
- Attach one or more **Candidate Resumes**.
- `/analyze` — Trigger Gemini ATS evaluation and receive the formatted report.
- `/status` — View currently uploaded files and active channels.
- `/clear` — Reset files to evaluate another role.

---

## 📡 Multi-Platform Expansion (Discord, Slack, etc.)

To forward every analysis automatically to your Discord server or Slack workspace:
1. In Discord: `Channel Settings` ➡️ `Integrations` ➡️ `Webhooks` ➡️ `New Webhook` ➡️ `Copy Webhook URL`.
2. Paste into `.env`:
   ```ini
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```
3. Any `/analyze` executed in Telegram will immediately broadcast a formatted report to Discord!

---

## 📦 Version Control (Git)

To stage, commit, and push updates:
```bash
python git_sync.py "Commit message"
# To push with personal access token:
python git_sync.py --push YOUR_GITHUB_TOKEN
```
Repository: [https://github.com/pmunaswamireddy/My-JD-ChatBot.git](https://github.com/pmunaswamireddy/My-JD-ChatBot.git)
