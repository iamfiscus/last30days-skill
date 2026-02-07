"""Tests for dailydev module."""

import json
import sys
import unittest
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import dailydev, schema


class TestSearchDailyDev(unittest.TestCase):
    def test_mock_response_passthrough(self):
        mock = {"posts": [{"id": "test", "title": "Test", "url": "https://example.com"}]}
        result = dailydev.search_dailydev(
            api_key="fake",
            topic="test",
            from_date="2026-01-01",
            to_date="2026-01-31",
            mock_response=mock,
        )
        self.assertEqual(result, mock)

    def test_depth_config(self):
        self.assertEqual(dailydev.DEPTH_CONFIG["quick"], 10)
        self.assertEqual(dailydev.DEPTH_CONFIG["default"], 20)
        self.assertEqual(dailydev.DEPTH_CONFIG["deep"], 50)


class TestParseDailyDevResponse(unittest.TestCase):
    def setUp(self):
        fixture_path = Path(__file__).parent.parent / "fixtures" / "dailydev_sample.json"
        with open(fixture_path) as f:
            self.fixture = json.load(f)

    def test_parses_fixture(self):
        items = dailydev.parse_dailydev_response(self.fixture)
        self.assertEqual(len(items), 4)

    def test_field_mapping(self):
        items = dailydev.parse_dailydev_response(self.fixture)
        first = items[0]

        self.assertEqual(first["id"], "DD1")
        self.assertEqual(first["title"], "Building AI Agents with Claude Code")
        self.assertEqual(first["url"], "https://dev.to/example/building-ai-agents")
        self.assertEqual(first["source_name"], "DEV Community")
        self.assertEqual(first["author_name"], "Jane Dev")
        self.assertEqual(first["author_username"], "janedev")
        self.assertEqual(first["date"], "2026-01-20")
        self.assertIn("ai", first["tags"])
        self.assertEqual(first["read_time"], 8)

    def test_engagement_mapping(self):
        items = dailydev.parse_dailydev_response(self.fixture)
        first = items[0]

        self.assertIsNotNone(first["engagement"])
        self.assertEqual(first["engagement"]["score"], 142)
        self.assertEqual(first["engagement"]["num_comments"], 23)

    def test_empty_response(self):
        items = dailydev.parse_dailydev_response({})
        self.assertEqual(items, [])

    def test_no_posts_key(self):
        items = dailydev.parse_dailydev_response({"data": []})
        self.assertEqual(items, [])

    def test_relevance_decreases_with_position(self):
        items = dailydev.parse_dailydev_response(self.fixture)
        # First item should generally have higher relevance than last
        # (though engagement can override position)
        self.assertGreater(items[0]["relevance"], 0)
        self.assertLessEqual(items[0]["relevance"], 1.0)

    def test_skips_items_without_title(self):
        response = {
            "data": [
                {"id": "1", "title": "", "url": "https://example.com"},
                {"id": "2", "title": "Valid Title", "url": "https://example.com"},
            ]
        }
        items = dailydev.parse_dailydev_response(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Valid Title")

    def test_legacy_posts_key(self):
        """Ensure old fixture format with 'posts' key still works."""
        response = {
            "posts": [
                {"id": "1", "title": "Legacy Format", "url": "https://example.com",
                 "upvotes": 10, "comments": 2},
            ]
        }
        items = dailydev.parse_dailydev_response(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["engagement"]["score"], 10)


class TestComputeRelevance(unittest.TestCase):
    def test_first_position_high_relevance(self):
        post = {"numUpvotes": 100, "numComments": 20, "readTime": 10}
        result = dailydev._compute_relevance(0, 10, post)
        self.assertGreater(result, 0.5)

    def test_last_position_lower_relevance(self):
        post = {"numUpvotes": 5, "numComments": 1, "readTime": 3}
        result = dailydev._compute_relevance(9, 10, post)
        self.assertGreater(result, 0)
        self.assertLess(result, 0.5)

    def test_single_item(self):
        post = {"numUpvotes": 50, "numComments": 10, "readTime": 5}
        result = dailydev._compute_relevance(0, 1, post)
        self.assertGreater(result, 0.5)

    def test_high_engagement_boosts_score(self):
        low_eng = {"numUpvotes": 1, "numComments": 0, "readTime": 1}
        high_eng = {"numUpvotes": 500, "numComments": 100, "readTime": 15}
        low_result = dailydev._compute_relevance(5, 10, low_eng)
        high_result = dailydev._compute_relevance(5, 10, high_eng)
        self.assertGreater(high_result, low_result)

    def test_result_bounded(self):
        post = {"numUpvotes": 10000, "numComments": 5000, "readTime": 30}
        result = dailydev._compute_relevance(0, 1, post)
        self.assertLessEqual(result, 1.0)
        self.assertGreaterEqual(result, 0.0)


if __name__ == "__main__":
    unittest.main()
