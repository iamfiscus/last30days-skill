"""Tests for tubelab_yt module."""

import json
import sys
import unittest
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import tubelab_yt, schema


class TestSearchYouTube(unittest.TestCase):
    def test_mock_response_passthrough(self):
        mock = {"videos": [{"id": "test", "title": "Test"}]}
        result = tubelab_yt.search_youtube(
            api_key="fake",
            topic="test",
            from_date="2026-01-01",
            to_date="2026-01-31",
            mock_response=mock,
        )
        self.assertEqual(result, mock)

    def test_depth_config(self):
        self.assertEqual(tubelab_yt.DEPTH_CONFIG["quick"], 10)
        self.assertEqual(tubelab_yt.DEPTH_CONFIG["default"], 20)
        self.assertEqual(tubelab_yt.DEPTH_CONFIG["deep"], 50)


class TestParseYouTubeResponse(unittest.TestCase):
    def setUp(self):
        fixture_path = Path(__file__).parent.parent / "fixtures" / "tubelab_sample.json"
        with open(fixture_path) as f:
            self.fixture = json.load(f)

    def test_parses_fixture(self):
        items = tubelab_yt.parse_youtube_response(self.fixture)
        self.assertEqual(len(items), 4)

    def test_field_mapping(self):
        items = tubelab_yt.parse_youtube_response(self.fixture)
        first = items[0]

        self.assertEqual(first["id"], "YT1")
        self.assertEqual(first["title"], "Building Production AI Agents - Complete Tutorial")
        self.assertEqual(first["url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(first["channel_name"], "Fireship")
        self.assertEqual(first["channel_id"], "UCsBjURrPoezykLs9EqgamOA")
        self.assertEqual(first["date"], "2026-01-22")
        self.assertEqual(first["duration"], 720)

    def test_engagement_mapping(self):
        items = tubelab_yt.parse_youtube_response(self.fixture)
        first = items[0]

        self.assertIsNotNone(first["engagement"])
        self.assertEqual(first["engagement"]["views"], 245000)
        self.assertEqual(first["engagement"]["likes"], 12400)
        self.assertEqual(first["engagement"]["num_comments"], 890)

    def test_empty_response(self):
        items = tubelab_yt.parse_youtube_response({})
        self.assertEqual(items, [])

    def test_no_videos_key(self):
        items = tubelab_yt.parse_youtube_response({"data": []})
        self.assertEqual(items, [])

    def test_url_construction(self):
        items = tubelab_yt.parse_youtube_response(self.fixture)
        for item in items:
            self.assertTrue(item["url"].startswith("https://www.youtube.com/watch?v="))

    def test_relevance_scores(self):
        items = tubelab_yt.parse_youtube_response(self.fixture)
        for item in items:
            self.assertGreater(item["relevance"], 0)
            self.assertLessEqual(item["relevance"], 1.0)

    def test_skips_items_without_title(self):
        response = {
            "videos": [
                {"id": "1", "title": ""},
                {"id": "2", "title": "Valid Title"},
            ]
        }
        items = tubelab_yt.parse_youtube_response(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Valid Title")


class TestComputeRelevance(unittest.TestCase):
    def test_first_position_high_relevance(self):
        video = {"views": 100000, "likes": 5000, "comments": 500}
        result = tubelab_yt._compute_relevance(0, 10, video)
        self.assertGreater(result, 0.5)

    def test_last_position_lower_relevance(self):
        video = {"views": 100, "likes": 5, "comments": 1}
        result = tubelab_yt._compute_relevance(9, 10, video)
        self.assertGreater(result, 0)

    def test_single_item(self):
        video = {"views": 50000, "likes": 2000, "comments": 200}
        result = tubelab_yt._compute_relevance(0, 1, video)
        self.assertGreater(result, 0.5)

    def test_high_views_boosts_score(self):
        low_eng = {"views": 100, "likes": 5, "comments": 1}
        high_eng = {"views": 1000000, "likes": 50000, "comments": 5000}
        low_result = tubelab_yt._compute_relevance(5, 10, low_eng)
        high_result = tubelab_yt._compute_relevance(5, 10, high_eng)
        self.assertGreater(high_result, low_result)

    def test_result_bounded(self):
        video = {"views": 10000000, "likes": 500000, "comments": 50000}
        result = tubelab_yt._compute_relevance(0, 1, video)
        self.assertLessEqual(result, 1.0)
        self.assertGreaterEqual(result, 0.0)


if __name__ == "__main__":
    unittest.main()
