import json
import re
from typing import List, Dict, Any
from google import genai
from google.genai import types

def analyze_resumes_with_gemini(
    jd_text: str,
    resumes: List[Dict[str, str]],
    api_key: str,
    model_name: str = "gemini-2.5-flash"
) -> Dict[str, Any]:
    """
    Analyze JD and batch of resumes using Google Gemini API.
    resumes format: [{'name': 'Candidate1.pdf', 'text': '...'}]
    Returns parsed JSON dictionary.
    """
    if not api_key:
        return mock_fallback_analysis(jd_text, resumes)

    client = genai.Client(api_key=api_key)

    # Format the prompt
    resumes_payload = []
    for idx, r in enumerate(resumes, 1):
        resumes_payload.append(f"--- RESUME #{idx} (File: {r['name']}) ---\n{r['text']}\n")

    combined_resumes = "\n".join(resumes_payload)

    prompt = f"""You are an elite, highly precise ATS (Applicant Tracking System) and Technical Recruiter.
Analyze the following Job Description (JD) and the candidate resumes.

CRITICAL INSTRUCTIONS:
- Be concise, direct, and actionable. No conversational filler, no polite intros or outros.
- Calculate an accurate ATS Match Score (0 to 100) based on skills, experience match, and domain relevance.
- List matched skills and missing skills specifically required by the JD.
- Give concrete feature improvements and resume suggestions.
- Provide 2-3 specific, reputable recommended courses with real, working direct URLs (Coursera, Udemy, edX, freeCodeCamp, Harvard CS50, or official tech documentation).
- Return ONLY valid JSON adhering strictly to the JSON schema below.

JSON SCHEMA:
{{
  "jd_summary": {{
    "role_title": "string",
    "experience_required": "string",
    "key_requirements": ["string", "string"]
  }},
  "total_resumes": {len(resumes)},
  "candidates": [
    {{
      "candidate_name": "string (extract name from resume or fallback to filename)",
      "file_name": "string",
      "ats_score": 85,
      "skills_matched": ["string"],
      "skills_missing": ["string"],
      "improvements": ["string"],
      "recommended_courses": [
        {{
          "title": "string",
          "url": "https://..."
        }}
      ]
    }}
  ]
}}

=== JOB DESCRIPTION ===
{jd_text}

=== CANDIDATE RESUMES ===
{combined_resumes}
"""

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        
        response_text = response.text.strip()
        # Clean any accidental markdown backticks
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        data = json.loads(response_text)
        return data

    except Exception as e:
        print(f"[Gemini Analysis Error]: {e}")
        # Fallback to local heuristic evaluator if API error occurs
        return mock_fallback_analysis(jd_text, resumes, error_note=str(e))


def mock_fallback_analysis(jd_text: str, resumes: List[Dict[str, str]], error_note: str = "") -> Dict[str, Any]:
    """Heuristic fallback evaluator for instant demos and offline/no-key testing."""
    jd_lower = jd_text.lower()
    
    # Common tech keywords to check
    keywords = [
        "python", "javascript", "typescript", "react", "next.js", "fastapi", "django", 
        "node.js", "docker", "kubernetes", "aws", "gcp", "postgresql", "redis", 
        "vector db", "pinecone", "gemini", "openai", "rag", "git", "ci/cd"
    ]
    
    jd_skills = [kw for kw in keywords if kw in jd_lower]
    if not jd_skills:
        jd_skills = ["Python", "FastAPI", "React", "Docker", "PostgreSQL"]

    # Extract role title
    lines = [l.strip() for l in jd_text.splitlines() if l.strip()]
    role_title = lines[0] if lines else "Target Position"
    if "title:" in role_title.lower():
        role_title = role_title.split(":", 1)[1].strip()

    candidates = []
    for r in resumes:
        r_lower = r["text"].lower()
        matched = [s.title() for s in jd_skills if s in r_lower]
        missing = [s.title() for s in jd_skills if s not in r_lower]

        score = int(round((len(matched) / max(len(jd_skills), 1)) * 100))
        score = min(max(score, 35), 96)

        # Name extraction attempt
        first_line = r["text"].split("\n")[0].strip()
        name = first_line if len(first_line) < 40 and not any(c in first_line for c in ["@", ":", "/"]) else r["name"]

        courses = []
        if missing:
            top_miss = missing[0].lower()
            if "docker" in top_miss or "kubernetes" in top_miss:
                courses.append({"title": "Docker & Kubernetes: The Practical Guide (Udemy)", "url": "https://www.udemy.com/course/docker-kubernetes-the-practical-guide/"})
            elif "react" in top_miss:
                courses.append({"title": "React - The Complete Guide (Udemy)", "url": "https://www.udemy.com/course/react-the-complete-guide-incl-redux/"})
            elif "fastapi" in top_miss or "python" in top_miss:
                courses.append({"title": "FastAPI Official Tutorial & Certification", "url": "https://fastapi.tiangolo.com/tutorial/"})
            else:
                courses.append({"title": f"Mastering {missing[0]} (Coursera)", "url": f"https://www.coursera.org/search?query={missing[0]}"})
        
        courses.append({"title": "Generative AI with Large Language Models (Coursera)", "url": "https://www.coursera.org/learn/generative-ai-with-llms"})

        candidates.append({
            "candidate_name": name,
            "file_name": r["name"],
            "ats_score": score,
            "skills_matched": matched if matched else ["General Programming"],
            "skills_missing": missing if missing else ["None detected"],
            "improvements": [
                f"Quantify impact with metrics in recent projects (e.g. reduced latency, increased user engagement).",
                f"Add dedicated section highlighting {', '.join(missing[:3]) if missing else 'advanced cloud architectures'}."
            ],
            "recommended_courses": courses
        })

    # Sort candidates by ATS score descending
    candidates.sort(key=lambda x: x["ats_score"], reverse=True)

    result = {
        "jd_summary": {
            "role_title": role_title[:60],
            "experience_required": "3+ Years" if "3" in jd_text or "5" in jd_text else "Not specified",
            "key_requirements": [s.title() for s in jd_skills[:6]]
        },
        "total_resumes": len(resumes),
        "candidates": candidates
    }
    if error_note:
        result["note"] = f"(Note: Local heuristic engine used due to: {error_note})"
    return result


def format_report_for_telegram(data: Dict[str, Any]) -> str:
    """
    Format report into neat, high-impact Telegram Markdown.
    Zero fluff, direct and organized.
    """
    jd = data.get("jd_summary", {})
    role = jd.get("role_title", "Job Role")
    exp = jd.get("experience_required", "N/A")
    reqs = jd.get("key_requirements", [])
    total = data.get("total_resumes", len(data.get("candidates", [])))

    lines = [
        f"🎯 *JOB DESCRIPTION SNAPSHOT*",
        f"• *Role:* {role}",
        f"• *Experience:* {exp}",
        f"• *Core Stack:* {', '.join(reqs)}",
        f"• *Resumes Evaluated:* `{total}`",
        "",
        "═══════════════════════════════",
        "📊 *CANDIDATE ATS RANKINGS & ANALYSIS*",
        "═══════════════════════════════"
    ]

    for idx, c in enumerate(data.get("candidates", []), 1):
        name = c.get("candidate_name", f"Candidate {idx}")
        fname = c.get("file_name", "")
        score = c.get("ats_score", 0)
        
        # Score badge
        if score >= 85:
            badge = "🟢 Strong Match"
        elif score >= 65:
            badge = "🟡 Moderate Match"
        else:
            badge = "🔴 Low Match"

        matched = ", ".join(c.get("skills_matched", [])) or "None"
        missing = ", ".join(c.get("skills_missing", [])) or "None"
        
        lines.append(f"\n*{idx}. {name}* (`{fname}`)")
        lines.append(f"🏆 *ATS Score:* `{score}%` — {badge}")
        lines.append(f"✅ *Skills Present:* {matched}")
        lines.append(f"❌ *Skills Missing:* {missing}")
        
        # Improvements
        improvements = c.get("improvements", [])
        if improvements:
            lines.append("💡 *Improvements:*")
            for imp in improvements:
                lines.append(f"  ▫️ {imp}")

        # Recommended Courses
        courses = c.get("recommended_courses", [])
        if courses:
            lines.append("📚 *Recommended Courses:*")
            for crs in courses:
                title = crs.get("title", "Course")
                url = crs.get("url", "#")
                lines.append(f"  🔗 [{title}]({url})")

        lines.append("───────────────────────────────")

    if data.get("note"):
        lines.append(f"\nℹ️ _{data['note']}_")

    return "\n".join(lines)


def format_report_for_discord(data: Dict[str, Any]) -> str:
    """Format report into clean Discord Markdown with hyperlinks."""
    jd = data.get("jd_summary", {})
    role = jd.get("role_title", "Job Role")
    exp = jd.get("experience_required", "N/A")
    reqs = jd.get("key_requirements", [])
    total = data.get("total_resumes", len(data.get("candidates", [])))

    msg = f"## 🎯 Job Description: {role}\n"
    msg += f"**Experience:** {exp} | **Key Stack:** {', '.join(reqs)} | **Total Resumes:** {total}\n\n"
    msg += "### 📊 Candidate ATS Evaluation\n"

    for idx, c in enumerate(data.get("candidates", []), 1):
        name = c.get("candidate_name", f"Candidate {idx}")
        score = c.get("ats_score", 0)
        badge = "🟢" if score >= 85 else ("🟡" if score >= 65 else "🔴")
        matched = ", ".join(c.get("skills_matched", [])) or "None"
        missing = ", ".join(c.get("skills_missing", [])) or "None"

        msg += f"**{idx}. {name}** — ATS Score: `{score}%` {badge}\n"
        msg += f"- **Matched Skills:** {matched}\n"
        msg += f"- **Missing Skills:** {missing}\n"
        
        improves = c.get("improvements", [])
        if improves:
            msg += f"- **Key Improvements:** {'; '.join(improves)}\n"
            
        courses = c.get("recommended_courses", [])
        if courses:
            course_links = [f"[{crs.get('title')}]({crs.get('url')})" for crs in courses]
            msg += f"- **Recommended Courses:** {' | '.join(course_links)}\n"
        msg += "\n"

    return msg
