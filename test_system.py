"""
Quick system test script for the hackathon demo.
Verifies parsing of sample JD and resumes, executes Gemini ATS evaluation,
and prints the exact formatted report.
"""
from pathlib import Path
import sys
import io

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config
from parser import extract_text_from_file
from analyzer import (
    analyze_resumes_with_gemini,
    format_report_for_telegram,
    format_report_for_discord
)
from dispatchers import dispatch_to_all_configured_channels

def main():
    print("=" * 60)
    print("🚀 TESTING JD & RESUME ATS MATCH PIPELINE")
    print("=" * 60)

    sample_dir = Path(__file__).resolve().parent / "sample_data"
    jd_file = sample_dir / "sample_jd.txt"
    r1_file = sample_dir / "resume_alex_rivers.txt"
    r2_file = sample_dir / "resume_sarah_chen.txt"

    print(f"\n1. Loading files...")
    jd_text = extract_text_from_file(str(jd_file))
    r1_text = extract_text_from_file(str(r1_file))
    r2_text = extract_text_from_file(str(r2_file))

    print(f"   ✓ JD loaded ({len(jd_text.split())} words)")
    print(f"   ✓ Resume 1 loaded: Alex Rivers ({len(r1_text.split())} words)")
    print(f"   ✓ Resume 2 loaded: Sarah Chen ({len(r2_text.split())} words)")

    resumes = [
        {"name": "resume_alex_rivers.txt", "text": r1_text},
        {"name": "resume_sarah_chen.txt", "text": r2_text}
    ]

    print("\n2. Running AI ATS Evaluation (Gemini 2.5 Flash)...")
    analysis = analyze_resumes_with_gemini(
        jd_text=jd_text,
        resumes=resumes,
        api_key=config.GEMINI_API_KEY,
        model_name=config.GEMINI_MODEL
    )

    print("\n3. Generating High-Impact Formatted Output...")
    report_tg = format_report_for_telegram(analysis)
    report_discord = format_report_for_discord(analysis)

    print("\n" + "=" * 30 + " TELEGRAM FORMAT " + "=" * 30)
    print(report_tg)
    print("=" * 77)

    # Multi-channel broadcast test if webhooks exist
    print("\n4. Testing Multi-Channel Broadcast:")
    if config.DISCORD_WEBHOOK_URL:
        print("   -> Dispatching to Discord...")
    else:
        print("   ℹ️ Discord Webhook URL not set in .env (Skipping)")

    if config.SLACK_WEBHOOK_URL:
        print("   -> Dispatching to Slack...")
    else:
        print("   ℹ️ Slack Webhook URL not set in .env (Skipping)")

    dispatched = dispatch_to_all_configured_channels(
        report_telegram=report_tg,
        report_discord=report_discord,
        config_obj=config
    )
    if dispatched:
        print(f"   ✓ Successfully sent to: {list(dispatched.keys())}")
    else:
        print("   ℹ️ No external webhooks configured yet. Ready when you add them!")

    print("\n✅ System test complete! Ready for live deployment.")

if __name__ == "__main__":
    main()
