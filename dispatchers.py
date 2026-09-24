import requests
import json
from typing import Dict, Any, List

def split_message(text: str, max_length: int = 4000) -> List[str]:
    """Splits long text by line breaks to stay within platform character limits."""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    lines = text.split("\n")
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > max_length:
            if current:
                parts.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        parts.append(current)
    return parts


def send_to_telegram(bot_token: str, chat_id: str, markdown_text: str) -> bool:
    """Send message to Telegram via Bot API."""
    if not bot_token or not chat_id:
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = split_message(markdown_text, max_length=4000)
    success = True
    
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            if not r.ok:
                # Fallback to plain text if markdown formatting failed
                payload.pop("parse_mode", None)
                requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"[Telegram Dispatch Error]: {e}")
            success = False
            
    return success


def send_to_discord(webhook_url: str, markdown_text: str) -> bool:
    """Send formatted report to Discord via Incoming Webhook."""
    if not webhook_url:
        return False
    
    chunks = split_message(markdown_text, max_length=1950)
    success = True
    for chunk in chunks:
        payload = {
            "content": chunk,
            "username": "JD & ATS Match Bot",
            "avatar_url": "https://img.icons8.com/color/96/resume.png"
        }
        try:
            r = requests.post(webhook_url, json=payload, timeout=10)
            if not r.ok:
                print(f"[Discord Dispatch Failed]: {r.status_code} {r.text}")
                success = False
        except Exception as e:
            print(f"[Discord Dispatch Error]: {e}")
            success = False
            
    return success


def send_to_slack(webhook_url: str, markdown_text: str) -> bool:
    """Send formatted report to Slack via Incoming Webhook."""
    if not webhook_url:
        return False
    
    chunks = split_message(markdown_text, max_length=3500)
    success = True
    for chunk in chunks:
        payload = {
            "text": chunk,
            "mrkdwn": True
        }
        try:
            r = requests.post(webhook_url, json=payload, timeout=10)
            if not r.ok:
                print(f"[Slack Dispatch Failed]: {r.status_code} {r.text}")
                success = False
        except Exception as e:
            print(f"[Slack Dispatch Error]: {e}")
            success = False
            
    return success


def send_to_google_chat(webhook_url: str, text: str) -> bool:
    """Send report to Google Chat space via Incoming Webhook."""
    if not webhook_url:
        return False
    
    payload = {"text": text}
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        return r.ok
    except Exception as e:
        print(f"[Google Chat Dispatch Error]: {e}")
        return False


def send_to_whatsapp(api_url: str, text: str) -> bool:
    """Send to WhatsApp webhook/gateway."""
    if not api_url:
        return False
    
    try:
        payload = {"message": text}
        r = requests.post(api_url, json=payload, timeout=10)
        return r.ok
    except Exception as e:
        print(f"[WhatsApp Dispatch Error]: {e}")
        return False


def dispatch_to_all_configured_channels(
    report_telegram: str,
    report_discord: str,
    config_obj: Any,
    current_chat_id: str = None
) -> Dict[str, bool]:
    """
    Broadcasts the report to all enabled platforms in config.
    Returns status dictionary.
    """
    status = {}
    
    # 1. Telegram
    if config_obj.TELEGRAM_BOT_TOKEN and current_chat_id:
        status["Telegram"] = send_to_telegram(config_obj.TELEGRAM_BOT_TOKEN, current_chat_id, report_telegram)
        
    # 2. Discord
    if config_obj.DISCORD_WEBHOOK_URL:
        status["Discord"] = send_to_discord(config_obj.DISCORD_WEBHOOK_URL, report_discord)
        
    # 3. Slack
    if config_obj.SLACK_WEBHOOK_URL:
        status["Slack"] = send_to_slack(config_obj.SLACK_WEBHOOK_URL, report_discord)
        
    # 4. Google Chat
    if config_obj.GOOGLE_CHAT_WEBHOOK_URL:
        status["Google Chat"] = send_to_google_chat(config_obj.GOOGLE_CHAT_WEBHOOK_URL, report_discord)
        
    # 5. WhatsApp
    if config_obj.WHATSAPP_WEBHOOK_URL:
        status["WhatsApp"] = send_to_whatsapp(config_obj.WHATSAPP_WEBHOOK_URL, report_discord)
        
    return status
