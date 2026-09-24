"""
Visual Chart Generator for Candidate ATS Scores.
Produces sleek, modern high-resolution comparison charts for Telegram and Discord.
"""
import io
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

def generate_ats_chart(candidates: list, role_title: str = "Target Position") -> bytes:
    """
    Generates a horizontal bar chart comparing candidate ATS scores.
    Returns PNG image bytes.
    """
    if not candidates:
        return b""

    # Sort descending by score
    sorted_candidates = sorted(candidates, key=lambda c: c.get("ats_score", 0), reverse=False)

    names = [c.get("candidate_name", "Unknown")[:22] for c in sorted_candidates]
    scores = [c.get("ats_score", 0) for c in sorted_candidates]

    # Dynamic colors: Green for high, Amber for moderate, Red/Coral for low
    colors = []
    for s in scores:
        if s >= 80:
            colors.append("#10B981")  # Emerald Green
        elif s >= 60:
            colors.append("#F59E0B")  # Amber
        else:
            colors.append("#EF4444")  # Coral Red

    fig, ax = plt.subplots(figsize=(9, max(4.5, len(candidates) * 0.8)), dpi=180)
    fig.patch.set_facecolor("#0F172A")  # Deep Slate Navy
    ax.set_facecolor("#1E293B")

    bars = ax.barh(names, scores, color=colors, height=0.55, edgecolor="none", zorder=3)

    # Threshold line at 80% (Strong Match Cutoff)
    ax.axvline(80, color="#34D399", linestyle="--", linewidth=1.5, alpha=0.7, zorder=4)
    ax.text(80.5, len(names) - 0.5, "Strong Match (80%)", color="#34D399", fontsize=9, fontweight="bold", va="center")

    # Add score text on each bar
    for bar, score in zip(bars, scores):
        width = bar.get_width()
        status_text = "Strong" if score >= 80 else ("Moderate" if score >= 60 else "Low")
        ax.text(
            width + 1.5,
            bar.get_y() + bar.get_height() / 2,
            f"{score}% ({status_text})",
            va="center",
            ha="left",
            color="#F8FAFC",
            fontsize=10,
            fontweight="bold"
        )

    # Styling
    ax.set_xlim(0, 115)
    ax.set_xlabel("ATS Compatibility Score (%)", color="#94A3B8", fontsize=11, labelpad=10)
    ax.set_title(f"ATS Ranking: {role_title[:45]}", color="#FFFFFF", fontsize=13, fontweight="bold", pad=15)

    ax.tick_params(colors="#CBD5E1", labelsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#334155")
    ax.spines["bottom"].set_color("#334155")
    ax.grid(axis="x", color="#334155", linestyle=":", alpha=0.6, zorder=0)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
