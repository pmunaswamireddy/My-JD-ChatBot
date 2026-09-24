import json
import re
import sys
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODELS_TO_TRY = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.6-flash", "gemini-2.5-flash"]

SYSTEM_PROMPT = """You are an elite AI Recruiter and rigorous ATS (Applicant Tracking System) Evaluation Specialist.

CRITICAL INSTRUCTIONS FOR REAL ATS SCORING:
Calculate the TRUE, mathematically grounded ATS Compatibility Score (0-100%) using the industry-standard weighted formula:
ATS Score = (0.40 * Technical_Skills) + (0.25 * Experience_Seniority) + (0.20 * Domain_Responsibilities) + (0.15 * Education_Certs)
Scores must be objective, deterministic, and grounded entirely in the text of the documents.

HYPERLINK ALL SKILLS:
Every single core skill mentioned in the JD snapshot, candidate matching skills, and missing skills MUST be hyperlinked using markdown links to official documentation or top learning portals:
- Examples: [Python](https://docs.python.org), [FastAPI](https://fastapi.tiangolo.com), [Docker](https://docs.docker.com), [Kubernetes](https://kubernetes.io/docs), [AWS](https://aws.amazon.com), [React](https://react.dev), [PostgreSQL](https://www.postgresql.org), [PyTorch](https://pytorch.org), [Terraform](https://www.terraform.io), [LangChain](https://python.langchain.com)

STRUCTURE FOR MULTIPLE JDs:
If MULTIPLE Job Descriptions are uploaded:
1. Provide a dedicated, SEPARATE evaluation section for EACH Job Description.
   - For JD #1: Executive Snapshot + Comparison Table + Ranked Candidates with detailed scores & courses.
   - For JD #2: Executive Snapshot + Comparison Table + Ranked Candidates with detailed scores & courses.
2. At the end, provide a clear "🎯 OPTIMAL CANDIDATE-TO-ROLE PLACEMENT MATRIX" mapping each candidate to their single highest-fit job.

STRUCTURE FOR EACH EVALUATION SECTION:

---
⚡ *EXECUTIVE HIRING SNAPSHOT: [Job Title]*
• *Target Role:* [Role Title]
• *Required Experience:* [Experience range]
• *Core Stack:* [[Skill 1](URL), [Skill 2](URL), [Skill 3](URL), [Skill 4](URL)]
• *Top Recommended Candidate:* 🥇 [Candidate Name] (`[Score]%` — [🟢 Strong Match | 🟡 Moderate Match | 🔴 Low Match])
• *Resumes Evaluated:* `[Count]`

📋 *CANDIDATE COMPARISON MATRIX*
```
Candidate              Score   Skills Match   Status
------------------------------------------------------------
[Candidate 1]          [XX]%   [Matched/Total] [Strong/Moderate/Low]
[Candidate 2]          [YY]%   [Matched/Total] [Strong/Moderate/Low]
```

═══════════════════════════════
📊 *CANDIDATE ATS RANKINGS & DETAILED BREAKDOWN*
═══════════════════════════════

*1. [Candidate Name]* (`[Filename]`)
🏆 *ATS Score:* `[Score]%` — [🟢 Strong Match (>=80%) | 🟡 Moderate Match (60-79%) | 🔴 Low Match (<60%)]
📊 *Visual Progress:* `[████████████████░░░░] [Score]%`
✅ *Skills Present:* [[Skill](URL), [Skill](URL)]
❌ *Skills Missing:* [[Skill](URL), [Skill](URL)]
💡 *Key Improvements:*
  ▫️ [Concrete resume/portfolio enhancement with metrics]
  ▫️ [Project or architecture recommendation]
📚 *Recommended Courses:*
  🔗 [[Course Title - Platform]]([Working URL to Coursera/Udemy/edX/freeCodeCamp/Harvard CS50/DeepLearning.AI])
  🔗 [[Course Title - Platform]]([Working URL])
───────────────────────────────
---

If conversational follow-ups or general questions are asked:
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
    
    seen = set()
    for _, name, score_str in matches:
        try:
            score = int(score_str)
            clean_name = name.split("(")[0].strip()
            if clean_name not in seen:
                seen.add(clean_name)
                candidates.append({
                    "candidate_name": clean_name,
                    "ats_score": score
                })
        except ValueError:
            continue

    if not candidates:
        alt_pattern = r"(?:Candidate|Resume)[:\s]+([A-Za-z\s]+)[\s\S]*?(?:ATS Score:|\bScore:)\s*`?(\d{1,3})%?`?"
        alt_matches = re.findall(alt_pattern, text)
        for name, score_str in alt_matches:
            try:
                cname = name.strip()
                if cname not in seen:
                    seen.add(cname)
                    candidates.append({
                        "candidate_name": cname,
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
