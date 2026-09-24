"""
Git Version Control Automation using pure Python (Dulwich).
Allows adding, committing, and pushing to https://github.com/pmunaswamireddy/My-JD-ChatBot.git
"""
import sys
import os
from pathlib import Path
import dulwich.porcelain as git
from dulwich.repo import Repo

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = Path(__file__).resolve().parent
REMOTE_URL = "https://github.com/pmunaswamireddy/My-JD-ChatBot.git"

def sync_repo(commit_message: str = "Initial commit: Complete JD & Resume ATS Matcher Bot"):
    print(f"📦 Git Repository Sync for {REMOTE_URL}")
    
    # 1. Initialize or load repo
    try:
        repo = Repo(str(REPO_DIR))
    except Exception:
        repo = git.init(str(REPO_DIR))
        print("✓ Initialized Git repository")

    # 2. Stage files
    files_to_add = [
        "requirements.txt",
        ".gitignore",
        ".env.example",
        "config.py",
        "parser.py",
        "analyzer.py",
        "dispatchers.py",
        "bot.py",
        "test_system.py",
        "README.md",
        "sample_data/sample_jd.txt",
        "sample_data/resume_alex_rivers.txt",
        "sample_data/resume_sarah_chen.txt",
        "git_sync.py"
    ]
    
    existing_files = [f for f in files_to_add if (REPO_DIR / f).exists()]
    git.add(str(REPO_DIR), existing_files)
    print(f"✓ Staged {len(existing_files)} project files")

    # 3. Commit
    try:
        commit_id = git.commit(
            str(REPO_DIR),
            message=commit_message.encode("utf-8"),
            committer=b"Antigravity AI <bot@hackathon.local>",
            author=b"Antigravity AI <bot@hackathon.local>"
        )
        print(f"✓ Committed files: {commit_id.decode()[:8]}")
    except Exception as e:
        print(f"ℹ️ Commit status: {e}")

    # 4. Set remote origin
    config_file = repo.get_config()
    config_file.set(("remote", "origin"), "url", REMOTE_URL.encode("utf-8"))
    config_file.write_to_path()
    print(f"✓ Configured remote origin: {REMOTE_URL}")

    print("\n🚀 Ready to push!")
    print("To push to your GitHub repo, run:")
    print("  python git_sync.py --push <YOUR_GITHUB_TOKEN_OR_PASSWORD>")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "feat: JD ATS Matcher with Telegram bot, Gemini AI & Multi-channel Dispatcher"
    sync_repo(msg)
    
    if "--push" in sys.argv:
        token_idx = sys.argv.index("--push") + 1
        if token_idx < len(sys.argv):
            token = sys.argv[token_idx]
            push_url = REMOTE_URL.replace("https://", f"https://{token}@")
            print(f"Pushing to {REMOTE_URL}...")
            try:
                git.push(str(REPO_DIR), push_url, refspecs=[b"HEAD:refs/heads/main"])
                print("🎉 Successfully pushed to GitHub!")
            except Exception as e:
                print(f"❌ Push error: {e}")
        else:
            print("⚠️ Please provide GitHub personal access token: python git_sync.py --push <TOKEN>")
