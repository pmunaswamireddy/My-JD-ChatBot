import json
import re
import sys
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODELS_TO_TRY = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-flash"]

SYSTEM_PROMPT = """You are an elite, contextual AI Recruiter and ATS Evaluation Agent, designed to interact naturally like ChatGPT/Gemini, but with specialized precision for technical hiring.

CAPABILITIES:
1. Contextual Conversations: Understand user intent dynamically. Chat naturally, answer questions, provide advice, compare candidates, or create technical interview questions based on candidate gaps.
2. Multi-JD & Multi-Resume Processing: The user may send one or multiple Job Descriptions, and one or multiple resumes simultaneously. You must intelligently distinguish JDs from Resumes, match candidates to their respective or best-fit JD, and evaluate them thoroughly.
3. High-Impact Output Format:
Whenever evaluating or analyzing JDs and Resumes, ALWAYS present the evaluation in this clean, structured, and punchy format (zero fluffy filler, clear markdown):

---
🎯 *JOB DESCRIPTION SNAPSHOT*
• *Role:* [Title]
• *Experience:* [Required Experience]
• *Core Stack:* [Top 4-6 Technologies]
• *Resumes Evaluated:* `[Count]`

═══════════════════════════════
📊 *CANDIDATE ATS RANKINGS & ANALYSIS*
═══════════════════════════════

*1. [Candidate Name]* (`[Filename]`)
🏆 *ATS Score:* `[Score]%` — [🟢 Strong Match (>=85%) | 🟡 Moderate Match (60-84%) | 🔴 Low Match (<60%)]
✅ *Skills Present:* [Comma-separated skills]
❌ *Skills Missing:* [Comma-separated skills missing from JD]
💡 *Improvements:*
  ▫️ [Specific resume or portfolio improvement suggestion]
  ▫️ [Concrete project or metric to add]
📚 *Recommended Courses:*
  🔗 [[Course Title - Platform]]([Working URL to Coursera/Udemy/edX/freeCodeCamp/Harvard/Official Docs])
  🔗 [[Course Title - Platform]]([Working URL])
───────────────────────────────
---

If multiple JDs are provided:
Repeat the neat snapshot and candidate evaluations for each JD, or clearly state candidate-to-role matching recommendations.

If the user asks follow-up questions (e.g. "Why did candidate X score lower?", "Generate 3 interview questions for Candidate Y", "Can you recommend free YouTube playlists for Docker?"):
Respond conversationally, helpfully, and concisely with direct answers.
"""

def generate_conversational_response(
    messages: List[Dict[str, str]],
    api_key: str,
    active_model: str = "gemini-3.6-flash"
) -> str:
    """
    Handles conversational turns with multi-message context using Google Gemini.
    messages format: [{'role': 'user'|'assistant', 'content': '...'}]
    """
    if not api_key:
        return "⚠️ Gemini API key is missing. Please add it to your `.env` file."

    client = genai.Client(api_key=api_key)

    # Format history into a single cohesive prompt with system instructions
    conversation_text = ""
    for msg in messages:
        role_label = "USER" if msg["role"] == "user" else "ASSISTANT"
        conversation_text += f"\n\n[{role_label}]:\n{msg['content']}"

    full_prompt = f"{SYSTEM_PROMPT}\n\n=== CONVERSATION HISTORY ==={conversation_text}\n\n[ASSISTANT]:"

    # Try models in fallback order
    models_to_attempt = [active_model] + [m for m in MODELS_TO_TRY if m != active_model]
    
    last_err = None
    for model_name in models_to_attempt:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3
                )
            )
            return response.text.strip()
        except Exception as e:
            last_err = e
            print(f"[Gemini attempt with {model_name} failed]: {e}")
            continue

    # If all models fail, return safe fallback
    return (
        f"⚠️ *Gemini API temporary notice:* The AI service is currently experiencing high demand.\n\n"
        f"Details: `{last_err}`\n\n"
        f"Please try sending your message again in a few moments."
    )


def classify_document(text: str, filename: str) -> str:
    """Intelligently detects whether an uploaded document is a JD or a Resume."""
    text_lower = text.lower()
    
    jd_indicators = [
        "job description", "responsibilities", "requirements", "we are looking for",
        "qualifications", "role overview", "what you will do", "what we offer",
        "job title", "compensation", "benefits", "equal opportunity employer"
    ]
    
    resume_indicators = [
        "education", "work experience", "professional summary", "curriculum vitae",
        "gpa", "bachelor of", "master of", "skills", "projects", "certifications",
        "contact:", "github.com", "linkedin.com/in/"
    ]
    
    jd_score = sum(1 for ind in jd_indicators if ind in text_lower)
    resume_score = sum(1 for ind in resume_indicators if ind in text_lower)

    if "jd" in filename.lower() or "job" in filename.lower():
        jd_score += 3
    if "resume" in filename.lower() or "cv" in filename.lower():
        resume_score += 3

    return "job_description" if jd_score > resume_score else "resume"
