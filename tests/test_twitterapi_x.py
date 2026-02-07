"""Tests for twitterapi_x module."""

import json
import sys
import unittest
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import twitterapi_x


class TestBuildQuery(unittest.TestCase):
    def test_default_depth(self):
        result = twitterapi_x.build_query("Claude Code", "2026-01-01", "2026-01-31")
        self.assertEqual(
            result,
            "Claude Code since:2026-01-01 until:2026-01-31 lang:en -filter:retweets min_faves:3"
        )

    def test_quick_depth(self):
        result = twitterapi_x.build_query("AI tools", "2026-01-01", "2026-01-31", depth="quick")
        self.assertIn("min_faves:5", result)

    def test_deep_depth(self):
        result = twitterapi_x.build_query("AI tools", "2026-01-01", "2026-01-31", depth="deep")
        self.assertIn("min_faves:2", result)

    def test_query_structure(self):
        result = twitterapi_x.build_query("test topic", "2026-01-01", "2026-01-31", depth="default")
        self.assertIn("test topic", result)
        self.assertIn("since:2026-01-01", result)
        self.assertIn("until:2026-01-31", result)
        self.assertIn("lang:en", result)
        self.assertIn("-filter:retweets", result)


class TestParseCreatedAt(unittest.TestCase):
    def test_twitter_format(self):
        result = twitterapi_x._parse_created_at("Wed Jan 15 14:30:00 +0000 2026")
        self.assertEqual(result, "2026-01-15")

    def test_iso_format(self):
        result = twitterapi_x._parse_created_at("2026-01-15T14:30:00Z")
        self.assertEqual(result, "2026-01-15")

    def test_iso_date_only(self):
        result = twitterapi_x._parse_created_at("2026-01-15")
        self.assertEqual(result, "2026-01-15")

    def test_none_input(self):
        result = twitterapi_x._parse_created_at(None)
        self.assertIsNone(result)

    def test_empty_string(self):
        result = twitterapi_x._parse_created_at("")
        self.assertIsNone(result)

    def test_non_string(self):
        result = twitterapi_x._parse_created_at(12345)
        self.assertIsNone(result)

    def test_invalid_format(self):
        result = twitterapi_x._parse_created_at("not a date")
        self.assertIsNone(result)


class TestComputeRelevance(unittest.TestCase):
    def test_first_position_high_engagement(self):
        tweet = {"likeCount": 1000, "retweetCount": 200, "replyCount": 50, "quoteCount": 10}
        result = twitterapi_x._compute_relevance(0, 10, tweet)
        # Should be high: position 1.0 * 0.6 + engagement * 0.4
        self.assertGreater(result, 0.8)

    def test_last_position_no_engagement(self):
        tweet = {"likeCount": 0, "retweetCount": 0, "replyCount": 0, "quoteCount": 0}
        result = twitterapi_x._compute_relevance(9, 10, tweet)
        # Position score: 0.5, engagement: 0
        self.assertAlmostEqual(result, 0.3, places=1)

    def test_single_result(self):
        tweet = {"likeCount": 100, "retweetCount": 10, "replyCount": 5, "quoteCount": 1}
        result = twitterapi_x._compute_relevance(0, 1, tweet)
        # Position = 1.0 for single result
        self.assertGreater(result, 0.6)

    def test_middle_position(self):
        tweet = {"likeCount": 50, "retweetCount": 5, "replyCount": 2, "quoteCount": 0}
        result = twitterapi_x._compute_relevance(4, 10, tweet)
        self.assertGreater(result, 0.3)
        self.assertLess(result, 0.8)

    def test_handles_none_engagement(self):
        tweet = {"likeCount": None, "retweetCount": None, "replyCount": None, "quoteCount": None}
        result = twitterapi_x._compute_relevance(0, 5, tweet)
        # Should not crash, position score only
        self.assertAlmostEqual(result, 0.6, places=1)


class TestSearchX(unittest.TestCase):
    def test_mock_response_passthrough(self):
        mock = {"tweets": [{"id": "1", "text": "test", "url": "https://x.com/test/status/1"}]}
        result = twitterapi_x.search_x("fake-key", "topic", "2026-01-01", "2026-01-31", mock_response=mock)
        self.assertEqual(result, mock)


class TestParseXResponse(unittest.TestCase):
    def test_parse_fixture(self):
        fixture_path = Path(__file__).parent.parent / "fixtures" / "twitterapi_sample.json"
        with open(fixture_path) as f:
            response = json.load(f)

        items = twitterapi_x.parse_x_response(response)

        self.assertEqual(len(items), 4)

        # Check first item
        self.assertEqual(items[0]["id"], "X1")
        self.assertIn("Claude Code skill", items[0]["text"])
        self.assertEqual(items[0]["author_handle"], "devuser1")
        self.assertEqual(items[0]["date"], "2026-01-15")
        self.assertEqual(items[0]["engagement"]["likes"], 542)
        self.assertEqual(items[0]["engagement"]["reposts"], 87)
        self.assertEqual(items[0]["engagement"]["replies"], 34)
        self.assertEqual(items[0]["engagement"]["quotes"], 12)
        self.assertEqual(items[0]["why_relevant"], "")
        self.assertGreater(items[0]["relevance"], 0.0)
        self.assertLessEqual(items[0]["relevance"], 1.0)

    def test_output_format_compat(self):
        """Ensure output dict has same keys as xai_x.parse_x_response()."""
        response = {"tweets": [
            {
                "id": "123",
                "text": "test tweet",
                "url": "https://x.com/user/status/123",
                "createdAt": "Wed Jan 15 14:30:00 +0000 2026",
                "author": {"userName": "testuser"},
                "likeCount": 10,
                "retweetCount": 2,
                "replyCount": 1,
                "quoteCount": 0,
            }
        ]}

        items = twitterapi_x.parse_x_response(response)
        self.assertEqual(len(items), 1)

        expected_keys = {"id", "text", "url", "author_handle", "date", "engagement", "why_relevant", "relevance"}
        self.assertEqual(set(items[0].keys()), expected_keys)

        eng_keys = {"likes", "reposts", "replies", "quotes"}
        self.assertEqual(set(items[0]["engagement"].keys()), eng_keys)

    def test_empty_tweets(self):
        result = twitterapi_x.parse_x_response({"tweets": []})
        self.assertEqual(result, [])

    def test_missing_tweets_key(self):
        result = twitterapi_x.parse_x_response({})
        self.assertEqual(result, [])

    def test_non_dict_tweet_skipped(self):
        result = twitterapi_x.parse_x_response({"tweets": ["not a dict"]})
        self.assertEqual(result, [])

    def test_tweet_without_url_builds_from_author(self):
        response = {"tweets": [
            {
                "id": "456",
                "text": "tweet without url",
                "author": {"userName": "user1"},
                "likeCount": 5,
                "retweetCount": 0,
                "replyCount": 0,
                "quoteCount": 0,
            }
        ]}
        items = twitterapi_x.parse_x_response(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://x.com/user1/status/456")

    def test_tweet_without_url_or_author_skipped(self):
        response = {"tweets": [
            {
                "id": "789",
                "text": "orphan tweet",
                "likeCount": 5,
            }
        ]}
        items = twitterapi_x.parse_x_response(response)
        self.assertEqual(len(items), 0)

    def test_iso_date_parsed(self):
        """Last fixture item uses ISO format."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "twitterapi_sample.json"
        with open(fixture_path) as f:
            response = json.load(f)

        items = twitterapi_x.parse_x_response(response)
        # 4th item has ISO format date
        self.assertEqual(items[3]["date"], "2026-01-05")

    def test_relevance_decreases_with_position(self):
        """First item should have higher relevance than last."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "twitterapi_sample.json"
        with open(fixture_path) as f:
            response = json.load(f)

        items = twitterapi_x.parse_x_response(response)
        # Item 2 has highest engagement but is 2nd position
        # Item 1 is first position - should still score high
        self.assertGreater(items[0]["relevance"], items[3]["relevance"])


if __name__ == "__main__":
    unittest.main()
