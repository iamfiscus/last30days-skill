"""TubeLab YouTube search module for last30days skill.

Searches YouTube for video content via TubeLab's outlier search API.
Requires a TubeLab account and API key (TUBELAB_API_KEY).
Note: Each search costs 5 credits.
"""

import math
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from . import http

TUBELAB_SEARCH_URL = "https://api.tubelab.net/search/outliers"

DEPTH_CONFIG = {
    "quick": 10,
    "default": 20,
    "deep": 50,
}


def search_youtube(
    api_key: str,
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    mock_response: Optional[dict] = None,
) -> Dict[str, Any]:
    """Search YouTube for videos via TubeLab.

    Args:
        api_key: TubeLab API key
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
        "Api-Key": api_key,
    }

    url = f"{TUBELAB_SEARCH_URL}?q={quote(topic)}&limit={limit}"

    return http.get(url, headers=headers, timeout=30)


def _compute_relevance(position: int, total: int, video: dict) -> float:
    """Compute relevance score for a YouTube video.

    40% position weight + 60% engagement weight (views-dominant for YouTube)

    Args:
        position: 0-indexed position in search results
        total: Total number of results
        video: Raw video dict

    Returns:
        Relevance score 0.0-1.0
    """
    # Position score: first result = 1.0, last = 0.1
    if total <= 1:
        pos_score = 1.0
    else:
        pos_score = max(0.1, 1.0 - (position / (total - 1)) * 0.9)

    # Engagement score (views-dominant for YouTube)
    views = video.get("views", 0) or 0
    likes = video.get("likes", 0) or 0
    comments = video.get("comments", 0) or 0

    eng_score = (
        0.50 * math.log1p(views) +
        0.30 * math.log1p(likes) +
        0.20 * math.log1p(comments)
    )

    # Normalize engagement to 0-1 range
    # log1p(100000) ~ 11.5, log1p(1000000) ~ 13.8 — cap at ~14
    eng_normalized = min(1.0, eng_score / 14.0)

    return 0.4 * pos_score + 0.6 * eng_normalized


def parse_youtube_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse TubeLab API response into normalized item dicts.

    Args:
        response: Raw API response

    Returns:
        List of normalized item dicts
    """
    videos = response.get("videos", [])
    if not videos:
        return []

    items = []
    total = len(videos)

    for i, video in enumerate(videos):
        if not isinstance(video, dict):
            continue

        video_id = video.get("id", f"YT{i+1}")
        title = video.get("title", "").strip()

        if not title or not video_id:
            continue

        url = f"https://www.youtube.com/watch?v={video_id}"

        # Parse date from publishedAt ISO format
        date_str = None
        published_at = video.get("publishedAt", "")
        if published_at and len(published_at) >= 10:
            date_str = published_at[:10]  # YYYY-MM-DD from ISO

        # Channel info
        channel_name = video.get("channelName", "")
        channel_id = video.get("channelId", "")

        # Duration in seconds
        duration = video.get("duration")

        # Thumbnail
        thumbnail = video.get("thumbnail", "")

        # Engagement
        views = video.get("views")
        likes = video.get("likes")
        comments = video.get("comments")

        engagement = {}
        if views is not None or likes is not None or comments is not None:
            engagement = {
                "views": views,
                "likes": likes,
                "num_comments": comments,
            }

        # Relevance
        relevance = _compute_relevance(i, total, video)

        items.append({
            "id": f"YT{i+1}",
            "title": title,
            "url": url,
            "channel_name": channel_name,
            "channel_id": channel_id,
            "date": date_str,
            "duration": duration,
            "thumbnail": thumbnail,
            "engagement": engagement if engagement else None,
            "why_relevant": "",
            "relevance": relevance,
        })

    return items
