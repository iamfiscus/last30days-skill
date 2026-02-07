"""Output rendering for last30days skill."""

import json
from pathlib import Path
from typing import List, Optional

from . import schema

OUTPUT_DIR = Path.home() / ".local" / "share" / "last30days" / "out"


def ensure_output_dir():
    """Ensure output directory exists."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _assess_data_freshness(report: schema.Report) -> dict:
    """Assess how much data is actually from the last 30 days."""
    reddit_recent = sum(1 for r in report.reddit if r.date and r.date >= report.range_from)
    x_recent = sum(1 for x in report.x if x.date and x.date >= report.range_from)
    web_recent = sum(1 for w in report.web if w.date and w.date >= report.range_from)
    dailydev_recent = sum(1 for d in report.dailydev if d.date and d.date >= report.range_from)
    youtube_recent = sum(1 for y in report.youtube if y.date and y.date >= report.range_from)

    total_recent = reddit_recent + x_recent + web_recent + dailydev_recent + youtube_recent
    total_items = len(report.reddit) + len(report.x) + len(report.web) + len(report.dailydev) + len(report.youtube)

    return {
        "reddit_recent": reddit_recent,
        "x_recent": x_recent,
        "web_recent": web_recent,
        "dailydev_recent": dailydev_recent,
        "youtube_recent": youtube_recent,
        "total_recent": total_recent,
        "total_items": total_items,
        "is_sparse": total_recent < 5,
        "mostly_evergreen": total_items > 0 and total_recent < total_items * 0.3,
    }


def render_compact(report: schema.Report, limit: int = 15, missing_keys: str = "none") -> str:
    """Render compact output for Claude to synthesize.

    Args:
        report: Report data
        limit: Max items per source
        missing_keys: 'both', 'reddit', 'x', or 'none'

    Returns:
        Compact markdown string
    """
    lines = []

    # Header
    lines.append(f"## Research Results: {report.topic}")
    lines.append("")

    # Assess data freshness and add honesty warning if needed
    freshness = _assess_data_freshness(report)
    if freshness["is_sparse"]:
        lines.append("**⚠️ LIMITED RECENT DATA** - Few discussions from the last 30 days.")
        lines.append(f"Only {freshness['total_recent']} item(s) confirmed from {report.range_from} to {report.range_to}.")
        lines.append("Results below may include older/evergreen content. Be transparent with the user about this.")
        lines.append("")

    # Web-only mode banner (when no API keys)
    if report.mode == "web-only":
        lines.append("**🌐 WEB SEARCH MODE** - Claude will search blogs, docs & news")
        lines.append("")
        lines.append("---")
        lines.append("**⚡ Want better results?** Add API keys to unlock Reddit & X data:")
        lines.append("- `OPENAI_API_KEY` → Reddit threads with real upvotes & comments")
        lines.append("- `TWITTERAPI_IO_KEY` → X posts with real likes & reposts")
        lines.append("- Edit `~/.config/last30days/.env` to add keys")
        lines.append("---")
        lines.append("")

    # Cache indicator
    if report.from_cache:
        age_str = f"{report.cache_age_hours:.1f}h old" if report.cache_age_hours else "cached"
        lines.append(f"**⚡ CACHED RESULTS** ({age_str}) - use `--refresh` for fresh data")
        lines.append("")

    lines.append(f"**Date Range:** {report.range_from} to {report.range_to}")
    lines.append(f"**Mode:** {report.mode}")
    if report.openai_model_used:
        lines.append(f"**OpenAI Model:** {report.openai_model_used}")
    if report.xai_model_used:
        lines.append(f"**xAI Model:** {report.xai_model_used}")
    lines.append("")

    # Coverage note for partial coverage
    if report.mode == "reddit-only" and missing_keys == "x":
        lines.append("*💡 Tip: Add TWITTERAPI_IO_KEY for X/Twitter data and better triangulation.*")
        lines.append("")
    elif report.mode == "x-only" and missing_keys == "reddit":
        lines.append("*💡 Tip: Add OPENAI_API_KEY for Reddit data and better triangulation.*")
        lines.append("")

    # Reddit items
    if report.reddit_error:
        lines.append("### Reddit Threads")
        lines.append("")
        lines.append(f"**ERROR:** {report.reddit_error}")
        lines.append("")
    elif report.mode in ("both", "reddit-only") and not report.reddit:
        lines.append("### Reddit Threads")
        lines.append("")
        lines.append("*No relevant Reddit threads found for this topic.*")
        lines.append("")
    elif report.reddit:
        lines.append("### Reddit Threads")
        lines.append("")
        for item in report.reddit[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.score is not None:
                    parts.append(f"{eng.score}pts")
                if eng.num_comments is not None:
                    parts.append(f"{eng.num_comments}cmt")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else " (date unknown)"
            conf_str = f" [date:{item.date_confidence}]" if item.date_confidence != "high" else ""

            lines.append(f"**{item.id}** (score:{item.score}) r/{item.subreddit}{date_str}{conf_str}{eng_str}")
            lines.append(f"  {item.title}")
            lines.append(f"  {item.url}")
            if item.why_relevant:
                lines.append(f"  *{item.why_relevant}*")

            # Top comment insights
            if item.comment_insights:
                lines.append(f"  Insights:")
                for insight in item.comment_insights[:3]:
                    lines.append(f"    - {insight}")

            lines.append("")

    # X items
    if report.x_error:
        lines.append("### X Posts")
        lines.append("")
        lines.append(f"**ERROR:** {report.x_error}")
        lines.append("")
    elif report.mode in ("both", "x-only", "all", "x-web") and not report.x:
        lines.append("### X Posts")
        lines.append("")
        lines.append("*No relevant X posts found for this topic.*")
        lines.append("")
    elif report.x:
        lines.append("### X Posts")
        lines.append("")
        for item in report.x[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.likes is not None:
                    parts.append(f"{eng.likes}likes")
                if eng.reposts is not None:
                    parts.append(f"{eng.reposts}rt")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else " (date unknown)"
            conf_str = f" [date:{item.date_confidence}]" if item.date_confidence != "high" else ""

            lines.append(f"**{item.id}** (score:{item.score}) @{item.author_handle}{date_str}{conf_str}{eng_str}")
            lines.append(f"  {item.text[:200]}...")
            lines.append(f"  {item.url}")
            if item.why_relevant:
                lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # Web items (if any - populated by Claude)
    if report.web_error:
        lines.append("### Web Results")
        lines.append("")
        lines.append(f"**ERROR:** {report.web_error}")
        lines.append("")
    elif report.web:
        lines.append("### Web Results")
        lines.append("")
        for item in report.web[:limit]:
            date_str = f" ({item.date})" if item.date else " (date unknown)"
            conf_str = f" [date:{item.date_confidence}]" if item.date_confidence != "high" else ""

            lines.append(f"**{item.id}** [WEB] (score:{item.score}) {item.source_domain}{date_str}{conf_str}")
            lines.append(f"  {item.title}")
            lines.append(f"  {item.url}")
            lines.append(f"  {item.snippet[:150]}...")
            if item.why_relevant:
                lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # DailyDev items
    if report.dailydev_error:
        lines.append("### Developer Articles (daily.dev)")
        lines.append("")
        lines.append(f"**ERROR:** {report.dailydev_error}")
        lines.append("")
    elif report.dailydev:
        lines.append("### Developer Articles (daily.dev)")
        lines.append("")
        for item in report.dailydev[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.score is not None:
                    parts.append(f"{eng.score}pts")
                if eng.num_comments is not None:
                    parts.append(f"{eng.num_comments}cmt")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else " (date unknown)"
            conf_str = f" [date:{item.date_confidence}]" if item.date_confidence != "high" else ""
            tags_str = f" [{', '.join(item.tags[:3])}]" if item.tags else ""

            lines.append(f"**{item.id}** (score:{item.score}) {item.source_name}{date_str}{conf_str}{eng_str}")
            lines.append(f"  {item.title}")
            lines.append(f"  {item.url}")
            if item.summary:
                lines.append(f"  {item.summary[:150]}...")
            if item.author_username:
                lines.append(f"  by @{item.author_username}{tags_str}")
            if item.why_relevant:
                lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # YouTube items
    if report.youtube_error:
        lines.append("### YouTube Videos")
        lines.append("")
        lines.append(f"**ERROR:** {report.youtube_error}")
        lines.append("")
    elif report.youtube:
        lines.append("### YouTube Videos")
        lines.append("")
        for item in report.youtube[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.views is not None:
                    parts.append(f"{eng.views:,}views")
                if eng.likes is not None:
                    parts.append(f"{eng.likes:,}likes")
                if eng.num_comments is not None:
                    parts.append(f"{eng.num_comments:,}cmt")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else " (date unknown)"
            conf_str = f" [date:{item.date_confidence}]" if item.date_confidence != "high" else ""
            duration_str = ""
            if item.duration:
                mins = item.duration // 60
                secs = item.duration % 60
                duration_str = f" ({mins}:{secs:02d})"

            lines.append(f"**{item.id}** (score:{item.score}) {item.channel_name}{date_str}{conf_str}{eng_str}{duration_str}")
            lines.append(f"  {item.title}")
            lines.append(f"  {item.url}")
            if item.why_relevant:
                lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    return "\n".join(lines)


def render_context_snippet(report: schema.Report) -> str:
    """Render reusable context snippet.

    Args:
        report: Report data

    Returns:
        Context markdown string
    """
    lines = []
    lines.append(f"# Context: {report.topic} (Last 30 Days)")
    lines.append("")
    lines.append(f"*Generated: {report.generated_at[:10]} | Sources: {report.mode}*")
    lines.append("")

    # Key sources summary
    lines.append("## Key Sources")
    lines.append("")

    all_items = []
    for item in report.reddit[:5]:
        all_items.append((item.score, "Reddit", item.title, item.url))
    for item in report.x[:5]:
        all_items.append((item.score, "X", item.text[:50] + "...", item.url))
    for item in report.web[:5]:
        all_items.append((item.score, "Web", item.title[:50] + "...", item.url))
    for item in report.dailydev[:5]:
        all_items.append((item.score, "DailyDev", item.title[:50] + "...", item.url))
    for item in report.youtube[:5]:
        all_items.append((item.score, "YouTube", item.title[:50] + "...", item.url))

    all_items.sort(key=lambda x: -x[0])
    for score, source, text, url in all_items[:7]:
        lines.append(f"- [{source}] {text}")

    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("*See full report for best practices, prompt pack, and detailed sources.*")
    lines.append("")

    return "\n".join(lines)


def render_full_report(report: schema.Report) -> str:
    """Render full markdown report.

    Args:
        report: Report data

    Returns:
        Full report markdown
    """
    lines = []

    # Title
    lines.append(f"# {report.topic} - Last 30 Days Research Report")
    lines.append("")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append(f"**Date Range:** {report.range_from} to {report.range_to}")
    lines.append(f"**Mode:** {report.mode}")
    lines.append("")

    # Models
    lines.append("## Models Used")
    lines.append("")
    if report.openai_model_used:
        lines.append(f"- **OpenAI:** {report.openai_model_used}")
    if report.xai_model_used:
        lines.append(f"- **xAI:** {report.xai_model_used}")
    lines.append("")

    # Reddit section
    if report.reddit:
        lines.append("## Reddit Threads")
        lines.append("")
        for item in report.reddit:
            lines.append(f"### {item.id}: {item.title}")
            lines.append("")
            lines.append(f"- **Subreddit:** r/{item.subreddit}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'} (confidence: {item.date_confidence})")
            lines.append(f"- **Score:** {item.score}/100")
            if item.why_relevant:
                lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.score or '?'} points, {eng.num_comments or '?'} comments")

            if item.comment_insights:
                lines.append("")
                lines.append("**Key Insights from Comments:**")
                for insight in item.comment_insights:
                    lines.append(f"- {insight}")

            lines.append("")

    # X section
    if report.x:
        lines.append("## X Posts")
        lines.append("")
        for item in report.x:
            lines.append(f"### {item.id}: @{item.author_handle}")
            lines.append("")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'} (confidence: {item.date_confidence})")
            lines.append(f"- **Score:** {item.score}/100")
            if item.why_relevant:
                lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.likes or '?'} likes, {eng.reposts or '?'} reposts")

            lines.append("")
            lines.append(f"> {item.text}")
            lines.append("")

    # Web section
    if report.web:
        lines.append("## Web Results")
        lines.append("")
        for item in report.web:
            lines.append(f"### {item.id}: {item.title}")
            lines.append("")
            lines.append(f"- **Source:** {item.source_domain}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'} (confidence: {item.date_confidence})")
            lines.append(f"- **Score:** {item.score}/100")
            if item.why_relevant:
                lines.append(f"- **Relevance:** {item.why_relevant}")
            lines.append("")
            lines.append(f"> {item.snippet}")
            lines.append("")

    # DailyDev section
    if report.dailydev:
        lines.append("## Developer Articles (daily.dev)")
        lines.append("")
        for item in report.dailydev:
            lines.append(f"### {item.id}: {item.title}")
            lines.append("")
            lines.append(f"- **Source:** {item.source_name}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Author:** {item.author_name} (@{item.author_username})")
            lines.append(f"- **Date:** {item.date or 'Unknown'} (confidence: {item.date_confidence})")
            lines.append(f"- **Score:** {item.score}/100")
            if item.tags:
                lines.append(f"- **Tags:** {', '.join(item.tags)}")
            if item.read_time:
                lines.append(f"- **Read Time:** {item.read_time} min")
            if item.why_relevant:
                lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.score or '?'} upvotes, {eng.num_comments or '?'} comments")

            if item.summary:
                lines.append("")
                lines.append(f"> {item.summary}")

            lines.append("")

    # YouTube section
    if report.youtube:
        lines.append("## YouTube Videos")
        lines.append("")
        for item in report.youtube:
            lines.append(f"### {item.id}: {item.title}")
            lines.append("")
            lines.append(f"- **Channel:** {item.channel_name}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'} (confidence: {item.date_confidence})")
            lines.append(f"- **Score:** {item.score}/100")
            if item.duration:
                mins = item.duration // 60
                secs = item.duration % 60
                lines.append(f"- **Duration:** {mins}:{secs:02d}")
            if item.why_relevant:
                lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.views is not None:
                    parts.append(f"{eng.views:,} views")
                if eng.likes is not None:
                    parts.append(f"{eng.likes:,} likes")
                if eng.num_comments is not None:
                    parts.append(f"{eng.num_comments:,} comments")
                if parts:
                    lines.append(f"- **Engagement:** {', '.join(parts)}")

            lines.append("")

    # Placeholders for Claude synthesis
    lines.append("## Best Practices")
    lines.append("")
    lines.append("*To be synthesized by Claude*")
    lines.append("")

    lines.append("## Prompt Pack")
    lines.append("")
    lines.append("*To be synthesized by Claude*")
    lines.append("")

    return "\n".join(lines)


def write_outputs(
    report: schema.Report,
    raw_openai: Optional[dict] = None,
    raw_xai: Optional[dict] = None,
    raw_reddit_enriched: Optional[list] = None,
    raw_dailydev: Optional[dict] = None,
    raw_youtube: Optional[dict] = None,
):
    """Write all output files.

    Args:
        report: Report data
        raw_openai: Raw OpenAI API response
        raw_xai: Raw xAI API response
        raw_reddit_enriched: Raw enriched Reddit thread data
        raw_dailydev: Raw daily.dev API response
        raw_youtube: Raw TubeLab API response
    """
    ensure_output_dir()

    # report.json
    with open(OUTPUT_DIR / "report.json", 'w') as f:
        json.dump(report.to_dict(), f, indent=2)

    # report.md
    with open(OUTPUT_DIR / "report.md", 'w') as f:
        f.write(render_full_report(report))

    # last30days.context.md
    with open(OUTPUT_DIR / "last30days.context.md", 'w') as f:
        f.write(render_context_snippet(report))

    # Raw responses
    if raw_openai:
        with open(OUTPUT_DIR / "raw_openai.json", 'w') as f:
            json.dump(raw_openai, f, indent=2)

    if raw_xai:
        with open(OUTPUT_DIR / "raw_xai.json", 'w') as f:
            json.dump(raw_xai, f, indent=2)

    if raw_reddit_enriched:
        with open(OUTPUT_DIR / "raw_reddit_threads_enriched.json", 'w') as f:
            json.dump(raw_reddit_enriched, f, indent=2)

    if raw_dailydev:
        with open(OUTPUT_DIR / "raw_dailydev.json", 'w') as f:
            json.dump(raw_dailydev, f, indent=2)

    if raw_youtube:
        with open(OUTPUT_DIR / "raw_youtube.json", 'w') as f:
            json.dump(raw_youtube, f, indent=2)


def get_context_path() -> str:
    """Get path to context file."""
    return str(OUTPUT_DIR / "last30days.context.md")
