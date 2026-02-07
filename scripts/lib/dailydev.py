"""DailyDev search module for last30days skill.

Searches daily.dev for developer articles with real engagement metrics.
Requires a daily.dev Plus subscription and API key (DAILYDEV_API_KEY).
"""

import math
from typing import Any, Dict, List, Optional

from . import http

DAILYDEV_SEARCH_URL = "https://api.daily.dev/public/v1/search/posts"

DEPTH_CONFIG = {
    "quick": 10,
    "default": 20,
    "deep": 50,
}


def search_dailydev(
    api_key: str,
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    mock_response: Optional[dict] = None,
) -> Dict[str, Any]:
    """Search daily.dev for developer articles.

    Args:
        api_key: daily.dev API key (Bearer token)
        topic: Search query
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: Search depth (quick/default/deep)
        mock_response: If provided, return this instead of making API call

    Returns:
        Raw API response dict
    """
    if mock_response is not None:
        return mock_response

    limit = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    url = f"{DAILYDEV_SEARCH_URL}?q={topic}&time=month&limit={limit}"

    return http.get(url, headers=headers, timeout=30)


def _compute_relevance(position: int, total: int, post: dict) -> float:
    """Compute relevance score for a daily.dev post.

    50% position weight (search order = relevance)
    50% engagement weight

    Args:
        position: 0-indexed position in search results
        total: Total number of results
        post: Raw post dict

    Returns:
        Relevance score 0.0-1.0
    """
    # Position score: first result = 1.0, last = 0.1
    if total <= 1:
        pos_score = 1.0
    else:
        pos_score = max(0.1, 1.0 - (position / (total - 1)) * 0.9)

    # Engagement score
    upvotes = post.get("upvotes", 0) or 0
    comments = post.get("comments", 0) or 0
    read_time = min(post.get("readTime", 0) or 0, 20)

    eng_score = (
        0.55 * math.log1p(upvotes) +
        0.40 * math.log1p(comments) +
        0.05 * (read_time / 20)
    )

    # Normalize engagement to 0-1 range (rough scale based on typical values)
    # log1p(100) ~ 4.6, log1p(500) ~ 6.2 — cap at ~7 for normalization
    eng_normalized = min(1.0, eng_score / 7.0)

    return 0.5 * pos_score + 0.5 * eng_normalized


def parse_dailydev_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse daily.dev API response into normalized item dicts.

    Args:
        response: Raw API response

    Returns:
        List of normalized item dicts
    """
    posts = response.get("posts", [])
    if not posts:
        return []

    items = []
    total = len(posts)

    for i, post in enumerate(posts):
        if not isinstance(post, dict):
            continue

        post_id = post.get("id", f"DD{i+1}")
        title = post.get("title", "").strip()
        url = post.get("url", "").strip()

        if not title or not url:
            continue

        # Parse date from createdAt ISO format
        date_str = None
        created_at = post.get("createdAt", "")
        if created_at and len(created_at) >= 10:
            date_str = created_at[:10]  # YYYY-MM-DD from ISO

        # Author info
        author = post.get("author", {}) or {}
        author_name = author.get("name", "")
        author_username = author.get("username", "")

        # Source info
        source = post.get("source", {}) or {}
        source_name = source.get("name", "")

        # Engagement
        upvotes = post.get("upvotes")
        comments = post.get("comments")

        engagement = {}
        if upvotes is not None or comments is not None:
            engagement = {
                "score": upvotes,
                "num_comments": comments,
            }

        # Tags
        tags = post.get("tags", []) or []

        # Read time
        read_time = post.get("readTime")

        # Relevance
        relevance = _compute_relevance(i, total, post)

        items.append({
            "id": f"DD{i+1}",
            "title": title,
            "url": url,
            "source_name": source_name,
            "author_name": author_name,
            "author_username": author_username,
            "date": date_str,
            "summary": post.get("summary", ""),
            "tags": tags,
            "read_time": read_time,
            "engagement": engagement if engagement else None,
            "why_relevant": "",
            "relevance": relevance,
        })

    return items
