"""
Git Version Control Automation using pure Python (Dulwich).
Allows adding, committing, and pushing to https://github.com/pmunaswamireddy/My-JD-ChatBot.git
"""
import sys
import os
import getpass
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

    # 2. Stage all project files (excluding .env, venv, caches)
    files_to_add = [
        "requirements.txt",
        ".gitignore",
        ".env.example",
        "config.py",
        "parser.py",
        "analyzer.py",
        "charts.py",
        "pdf_report.py",
        "dispatchers.py",
        "bot.py",
        "generate_pdfs.py",
        "test_system.py",
        "start_bot.bat",
        "open_test_files.bat",
        "README.md",
        "git_sync.py"
    ]
    
    # Add files from ready_to_upload and sample_data
    for p in (REPO_DIR / "sample_data").glob("*.*"):
        files_to_add.append(str(p.relative_to(REPO_DIR)).replace("\\", "/"))
    for p in (REPO_DIR / "ready_to_upload").rglob("*.*"):
        files_to_add.append(str(p.relative_to(REPO_DIR)).replace("\\", "/"))

    existing_files = [f for f in set(files_to_add) if (REPO_DIR / f).exists()]
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
    print("  python git_sync.py --push <YOUR_GITHUB_TOKEN>")


def push_to_github(token: str):
    token = token.strip()
    if token.startswith("http"):
        print("\n❌ Error: You passed the repository URL instead of your Personal Access Token!")
        print("To push, GitHub requires an access token (format: ghp_xxxxxxxxxxxxxxxxxxxx)")
        print("\n👉 How to generate one in 20 seconds:")
        print("1. Open: https://github.com/settings/tokens")
        print("2. Click 'Generate new token (classic)'")
        print("3. Check the 'repo' scope and click Generate")
        print("4. Run: python git_sync.py --push <YOUR_TOKEN>\n")
        return

    push_url = REMOTE_URL.replace("https://", f"https://{token}@")
    print(f"\nPushing to {REMOTE_URL} (branch: main)...")
    try:
        git.push(str(REPO_DIR), push_url, refspecs=[b"HEAD:refs/heads/main"])
        print("\n🎉 SUCCESS! All files have been pushed to https://github.com/pmunaswamireddy/My-JD-ChatBot.git")
    except Exception as e:
        # Try pushing to master if main branch does not exist on remote
        try:
            print("Trying master branch...")
            git.push(str(REPO_DIR), push_url, refspecs=[b"HEAD:refs/heads/master"])
            print("\n🎉 SUCCESS! All files have been pushed to master branch on GitHub!")
        except Exception as e2:
            print(f"❌ Push error: {e2}")
            print("Tip: Make sure your token has 'repo' permissions enabled.")


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "feat: complete JD ATS recruiter bot with Telegram, charts, PDF dossier, and multi-channel"
    sync_repo(msg)
    
    if "--push" in sys.argv:
        token_idx = sys.argv.index("--push") + 1
        if token_idx < len(sys.argv):
            token = sys.argv[token_idx]
            push_to_github(token)
        else:
            token = input("\nEnter your GitHub Personal Access Token (ghp_...): ").strip()
            if token:
                push_to_github(token)
            else:
                print("⚠️ Token cannot be empty.")
