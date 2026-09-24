import json
import re
import sys
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODELS_TO_TRY = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.6-flash", "gemini-2.5-flash"]

SYSTEM_PROMPT = """You are an elite, contextual AI Recruiter and rigorous ATS (Applicant Tracking System) Evaluation Specialist.

CRITICAL INSTRUCTIONS FOR REAL ATS SCORING:
Calculate the TRUE, mathematically grounded ATS Compatibility Score (0-100%) using the industry-standard weighted rubric:
1. Technical Skills Match (40% Weight): Exact match ratio of JD required technologies, frameworks, and programming languages present in the resume.
2. Experience & Seniority Fit (25% Weight): Years of relevant domain experience and role seniority (Junior/Mid/Senior/Lead) vs. JD requirements.
3. Core Responsibilities & Domain Fit (20% Weight): Demonstrated production achievements directly matching the JD's primary job duties.
4. Education & Certifications (15% Weight): Degree relevance (BS/MS in CS, Engineering, Data) and industry certifications (AWS, CKA, GCP, etc.).

FORMULA:
ATS Score = (0.40 * Skills_Score) + (0.25 * Experience_Score) + (0.20 * Domain_Score) + (0.15 * Education_Score)
Scores must be objective, deterministic, and grounded entirely in the text of the documents. No inflated or arbitrary numbers.

HIGH-IMPACT VISUAL OUTPUT FORMAT:
Whenever evaluating JDs and Resumes, ALWAYS present the evaluation in this clean, structured format:

---
🎯 *JOB DESCRIPTION SNAPSHOT*
• *Role:* [Title]
• *Experience Required:* [Experience range]
• *Core Stack:* [Top 4-6 Technologies]
• *Resumes Evaluated:* `[Count]`

📋 *CANDIDATE COMPARISON MATRIX*
```
Candidate              Score   Skills Match   Status
------------------------------------------------------------
[Candidate 1]          [XX]%   [Matched/Total] [Strong/Moderate/Low]
[Candidate 2]          [YY]%   [Matched/Total] [Strong/Moderate/Low]
```

═══════════════════════════════
📊 *DETAILED ATS CANDIDATE BREAKDOWN*
═══════════════════════════════

*1. [Candidate Name]* (`[Filename]`)
🏆 *ATS Score:* `[Score]%` — [🟢 Strong Match (>=80%) | 🟡 Moderate Match (60-79%) | 🔴 Low Match (<60%)]
📊 *Visual Score:* `[████████████████░░░░] [Score]%`
✅ *Skills Present:* [Comma-separated skills verified in resume]
❌ *Skills Missing:* [Comma-separated skills required by JD but absent]
💡 *Key Improvements:*
  ▫️ [Concrete resume/portfolio improvement]
  ▫️ [Specific production metric or project to add]
📚 *Recommended Courses:*
  🔗 [[Course Title - Platform]]([Direct working URL to Coursera/Udemy/edX/freeCodeCamp/Harvard/Official Docs])
  🔗 [[Course Title - Platform]]([Direct working URL])
───────────────────────────────
---

If multiple JDs are provided:
Repeat the evaluation for each JD, or provide a role-mapping matrix showing which candidate is the best fit for which specific role.

If the user asks conversational questions, interview questions, or follow-ups:
Answer conversationally, precisely, and helpfully like ChatGPT/Gemini!
"""

def generate_conversational_response(
    messages: List[Dict[str, str]],
    api_key: str,
    active_model: str = "gemini-3.5-flash"
) -> str:
    """
    Handles conversational turns with multi-message context using Google Gemini.
    messages format: [{'role': 'user'|'assistant', 'content': '...'}]
    """
    if not api_key:
        return "⚠️ Gemini API key is missing. Please add it to your `.env` file."

    client = genai.Client(api_key=api_key)

    conversation_text = ""
    for msg in messages:
        role_label = "USER" if msg["role"] == "user" else "ASSISTANT"
        conversation_text += f"\n\n[{role_label}]:\n{msg['content']}"

    full_prompt = f"{SYSTEM_PROMPT}\n\n=== CONVERSATION HISTORY ==={conversation_text}\n\n[ASSISTANT]:"

    models_to_attempt = [active_model] + [m for m in MODELS_TO_TRY if m != active_model]
    
    last_err = None
    for model_name in models_to_attempt:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2
                )
            )
            return response.text.strip()
        except Exception as e:
            last_err = e
            print(f"[Gemini attempt with {model_name} failed]: {e}")
            continue

    return (
        f"⚠️ *Gemini API notice:* The AI service is currently busy.\n\n"
        f"Details: `{last_err}`\n\n"
        f"Please tap '🚀 Analyze Resumes' again to retry."
    )


def extract_candidate_scores_for_chart(text: str) -> List[Dict[str, Any]]:
    """
    Extracts candidate names and ATS scores from the AI response
    to generate graphical charts.
    """
    candidates = []
    
    # Pattern: *1. Name* (`file`) ... ATS Score:* `88%`
    pattern = r"\*(\d+)\.\s*([^*]+)\*[\s\S]*?(?:ATS Score:|\bScore:)\s*`?(\d{1,3})%?`?"
    matches = re.findall(pattern, text)
    
    for _, name, score_str in matches:
        try:
            score = int(score_str)
            clean_name = name.split("(")[0].strip()
            candidates.append({
                "candidate_name": clean_name,
                "ats_score": score
            })
        except ValueError:
            continue

    # Fallback pattern if numbered format wasn't strictly followed
    if not candidates:
        alt_pattern = r"(?:Candidate|Resume)[:\s]+([A-Za-z\s]+)[\s\S]*?(?:ATS Score:|\bScore:)\s*`?(\d{1,3})%?`?"
        alt_matches = re.findall(alt_pattern, text)
        for name, score_str in alt_matches:
            try:
                candidates.append({
                    "candidate_name": name.strip(),
                    "ats_score": int(score_str)
                })
            except ValueError:
                continue

    return candidates


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
