"""twitterapi.io client for X (Twitter) discovery."""

import math
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import http


def _log_error(msg: str):
    """Log error to stderr."""
    sys.stderr.write(f"[X ERROR] {msg}\n")
    sys.stderr.flush()


TWITTERAPI_SEARCH_URL = "https://api.twitterapi.io/twitter/tweet/advanced_search"

# Depth configurations: (min_faves, max_pages)
DEPTH_CONFIG = {
    "quick": (5, 1),
    "default": (3, 2),
    "deep": (2, 3),
}

# Engagement weights (same as score.py)
ENGAGEMENT_WEIGHTS = {
    "likes": 0.55,
    "reposts": 0.25,
    "replies": 0.15,
    "quotes": 0.05,
}


def build_query(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> str:
    """Build Twitter advanced search query string.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: Research depth - "quick", "default", or "deep"

    Returns:
        Twitter advanced search query string
    """
    min_faves, _ = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    return f"{topic} since:{from_date} until:{to_date} lang:en -filter:retweets min_faves:{min_faves}"


def search_x(
    api_key: str,
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    mock_response: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Search X for relevant posts using twitterapi.io.

    Args:
        api_key: twitterapi.io API key
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: Research depth - "quick", "default", or "deep"
        mock_response: Mock response for testing

    Returns:
        Combined API response with all tweets

    Raises:
        http.HTTPError: On first page failure
    """
    if mock_response is not None:
        return mock_response

    _, max_pages = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    query = build_query(topic, from_date, to_date, depth)

    headers = {
        "X-API-Key": api_key,
    }

    all_tweets = []
    cursor = None

    for page in range(max_pages):
        params = {
            "query": query,
            "queryType": "Top",
        }
        if cursor:
            params["cursor"] = cursor

        url = f"{TWITTERAPI_SEARCH_URL}?{urlencode(params)}"

        try:
            response = http.get(url, headers=headers, timeout=30)
        except http.HTTPError:
            if page == 0:
                raise
            # Subsequent page failures are tolerated
            break

        tweets = response.get("tweets", [])
        if not tweets:
            break

        all_tweets.extend(tweets)

        if not response.get("has_next_page"):
            break

        cursor = response.get("next_cursor")
        if not cursor:
            break

    return {"tweets": all_tweets}


def _parse_created_at(created_at: Any) -> Optional[str]:
    """Parse Twitter date format to YYYY-MM-DD.

    Handles:
        - Twitter format: "Wed Jan 15 14:30:00 +0000 2026"
        - ISO format: "2026-01-15T14:30:00Z"
        - None/empty

    Returns:
        Date string in YYYY-MM-DD format, or None
    """
    if not created_at or not isinstance(created_at, str):
        return None

    created_at = created_at.strip()

    # Try ISO format first
    iso_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})', created_at)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}-{iso_match.group(3)}"

    # Try Twitter format: "Wed Jan 15 14:30:00 +0000 2026"
    try:
        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass

    return None


def _compute_relevance(position: int, total: int, tweet: Dict[str, Any]) -> float:
    """Compute relevance score for a tweet.

    60% position weight (1st in "Top" results = 1.0, last = 0.5)
    40% engagement weight (log-scaled)

    Args:
        position: 0-based position in results
        total: Total number of results
        tweet: Raw tweet dict

    Returns:
        Relevance score between 0.0 and 1.0
    """
    # Position score: linear interpolation from 1.0 (first) to 0.5 (last)
    if total <= 1:
        position_score = 1.0
    else:
        position_score = 1.0 - 0.5 * (position / (total - 1))

    # Engagement score: log-scaled with same weights as score.py
    likes = math.log1p(max(0, tweet.get("likeCount", 0) or 0))
    reposts = math.log1p(max(0, tweet.get("retweetCount", 0) or 0))
    replies = math.log1p(max(0, tweet.get("replyCount", 0) or 0))
    quotes = math.log1p(max(0, tweet.get("quoteCount", 0) or 0))

    raw_engagement = (
        ENGAGEMENT_WEIGHTS["likes"] * likes
        + ENGAGEMENT_WEIGHTS["reposts"] * reposts
        + ENGAGEMENT_WEIGHTS["replies"] * replies
        + ENGAGEMENT_WEIGHTS["quotes"] * quotes
    )

    # Normalize engagement to 0-1 (log1p(1000) ~ 6.9, so cap around 7)
    engagement_score = min(1.0, raw_engagement / 7.0)

    return 0.6 * position_score + 0.4 * engagement_score


def parse_x_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse twitterapi.io response to extract X items.

    Args:
        response: Raw API response

    Returns:
        List of item dicts in the same format as xai_x.parse_x_response()
    """
    items = []

    tweets = response.get("tweets", [])
    if not tweets:
        return items

    total = len(tweets)

    for i, tweet in enumerate(tweets):
        if not isinstance(tweet, dict):
            continue

        url = tweet.get("url", "")
        if not url:
            # Build URL from author and id
            author = tweet.get("author", {})
            username = author.get("userName", "") if isinstance(author, dict) else ""
            tweet_id = tweet.get("id", "")
            if username and tweet_id:
                url = f"https://x.com/{username}/status/{tweet_id}"
            else:
                continue

        # Extract author handle
        author = tweet.get("author", {})
        author_handle = ""
        if isinstance(author, dict):
            author_handle = author.get("userName", "")
        author_handle = str(author_handle).strip().lstrip("@")

        # Parse date
        date = _parse_created_at(tweet.get("createdAt"))

        # Map engagement fields
        engagement = {
            "likes": int(tweet.get("likeCount", 0) or 0),
            "reposts": int(tweet.get("retweetCount", 0) or 0),
            "replies": int(tweet.get("replyCount", 0) or 0),
            "quotes": int(tweet.get("quoteCount", 0) or 0),
        }

        # Compute relevance
        relevance = _compute_relevance(i, total, tweet)

        clean_item = {
            "id": f"X{i + 1}",
            "text": str(tweet.get("text", "")).strip()[:500],
            "url": url,
            "author_handle": author_handle,
            "date": date,
            "engagement": engagement,
            "why_relevant": "",
            "relevance": min(1.0, max(0.0, relevance)),
        }

        items.append(clean_item)

    return items
