#!/usr/bin/env python3
"""
last30days - Research a topic from the last 30 days on Reddit + X.

Usage:
    python3 last30days.py <topic> [options]

Options:
    --mock              Use fixtures instead of real API calls
    --emit=MODE         Output mode: compact|json|md|context|path (default: compact)
    --sources=MODE      Source selection: auto|reddit|x|both (default: auto)
    --quick             Faster research with fewer sources (8-12 each)
    --deep              Comprehensive research with more sources (50-70 Reddit, 40-60 X)
    --debug             Enable verbose debug logging
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Add lib to path
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from lib import (
    dailydev,
    dates,
    dedupe,
    env,
    http,
    models,
    normalize,
    openai_reddit,
    reddit_enrich,
    render,
    schema,
    score,
    tubelab_yt,
    twitterapi_x,
    ui,
    websearch,
)


def load_fixture(name: str) -> dict:
    """Load a fixture file."""
    fixture_path = SCRIPT_DIR.parent / "fixtures" / name
    if fixture_path.exists():
        with open(fixture_path) as f:
            return json.load(f)
    return {}


def _search_reddit(
    topic: str,
    config: dict,
    selected_models: dict,
    from_date: str,
    to_date: str,
    depth: str,
    mock: bool,
) -> tuple:
    """Search Reddit via OpenAI (runs in thread).

    Returns:
        Tuple of (reddit_items, raw_openai, error)
    """
    raw_openai = None
    reddit_error = None

    if mock:
        raw_openai = load_fixture("openai_sample.json")
    else:
        try:
            raw_openai = openai_reddit.search_reddit(
                config["OPENAI_API_KEY"],
                selected_models["openai"],
                topic,
                from_date,
                to_date,
                depth=depth,
            )
        except http.HTTPError as e:
            raw_openai = {"error": str(e)}
            reddit_error = f"API error: {e}"
        except Exception as e:
            raw_openai = {"error": str(e)}
            reddit_error = f"{type(e).__name__}: {e}"

    # Parse response
    reddit_items = openai_reddit.parse_reddit_response(raw_openai or {})

    # Quick retry with simpler query if few results
    if len(reddit_items) < 5 and not mock and not reddit_error:
        core = openai_reddit._extract_core_subject(topic)
        if core.lower() != topic.lower():
            try:
                retry_raw = openai_reddit.search_reddit(
                    config["OPENAI_API_KEY"],
                    selected_models["openai"],
                    core,
                    from_date, to_date,
                    depth=depth,
                )
                retry_items = openai_reddit.parse_reddit_response(retry_raw)
                # Add items not already found (by URL)
                existing_urls = {item.get("url") for item in reddit_items}
                for item in retry_items:
                    if item.get("url") not in existing_urls:
                        reddit_items.append(item)
            except Exception:
                pass

    return reddit_items, raw_openai, reddit_error


def _search_x(
    topic: str,
    config: dict,
    selected_models: dict,
    from_date: str,
    to_date: str,
    depth: str,
    mock: bool,
) -> tuple:
    """Search X via twitterapi.io (runs in thread).

    Returns:
        Tuple of (x_items, raw_xai, error)
    """
    raw_xai = None
    x_error = None

    if mock:
        raw_xai = load_fixture("twitterapi_sample.json")
    else:
        try:
            raw_xai = twitterapi_x.search_x(
                config["TWITTERAPI_IO_KEY"],
                topic,
                from_date,
                to_date,
                depth=depth,
            )
        except http.HTTPError as e:
            raw_xai = {"error": str(e)}
            x_error = f"API error: {e}"
        except Exception as e:
            raw_xai = {"error": str(e)}
            x_error = f"{type(e).__name__}: {e}"

    # Parse response
    x_items = twitterapi_x.parse_x_response(raw_xai or {})

    return x_items, raw_xai, x_error


def _search_dailydev(
    topic: str,
    config: dict,
    from_date: str,
    to_date: str,
    depth: str,
    mock: bool,
) -> tuple:
    """Search daily.dev for developer articles (runs in thread).

    Returns:
        Tuple of (dailydev_items, raw_dailydev, error)
    """
    raw_dailydev = None
    dailydev_error = None

    if mock:
        raw_dailydev = load_fixture("dailydev_sample.json")
    else:
        try:
            raw_dailydev = dailydev.search_dailydev(
                config["DAILYDEV_API_KEY"],
                topic,
                from_date,
                to_date,
                depth=depth,
            )
        except http.HTTPError as e:
            raw_dailydev = {"error": str(e)}
            dailydev_error = f"API error: {e}"
        except Exception as e:
            raw_dailydev = {"error": str(e)}
            dailydev_error = f"{type(e).__name__}: {e}"

    # Parse response
    dailydev_items = dailydev.parse_dailydev_response(raw_dailydev or {})

    return dailydev_items, raw_dailydev, dailydev_error


def _search_youtube(
    topic: str,
    config: dict,
    from_date: str,
    to_date: str,
    depth: str,
    mock: bool,
) -> tuple:
    """Search YouTube via TubeLab (runs in thread).

    Returns:
        Tuple of (youtube_items, raw_youtube, error)
    """
    raw_youtube = None
    youtube_error = None

    if mock:
        raw_youtube = load_fixture("tubelab_sample.json")
    else:
        try:
            raw_youtube = tubelab_yt.search_youtube(
                config["TUBELAB_API_KEY"],
                topic,
                from_date,
                to_date,
                depth=depth,
            )
        except http.HTTPError as e:
            raw_youtube = {"error": str(e)}
            youtube_error = f"API error: {e}"
        except Exception as e:
            raw_youtube = {"error": str(e)}
            youtube_error = f"{type(e).__name__}: {e}"

    # Parse response
    youtube_items = tubelab_yt.parse_youtube_response(raw_youtube or {})

    return youtube_items, raw_youtube, youtube_error


def run_research(
    topic: str,
    sources: str,
    config: dict,
    selected_models: dict,
    from_date: str,
    to_date: str,
    depth: str = "default",
    mock: bool = False,
    progress: ui.ProgressDisplay = None,
    run_dailydev: bool = False,
    run_youtube: bool = False,
) -> tuple:
    """Run the research pipeline.

    Returns:
        Tuple of (reddit_items, x_items, web_needed, raw_openai, raw_xai,
                  raw_reddit_enriched, reddit_error, x_error,
                  dailydev_items, raw_dailydev, dailydev_error,
                  youtube_items, raw_youtube, youtube_error)

    Note: web_needed is True when WebSearch should be performed by Claude.
    The script outputs a marker and Claude handles WebSearch in its session.
    """
    reddit_items = []
    x_items = []
    dailydev_items = []
    youtube_items = []
    raw_openai = None
    raw_xai = None
    raw_dailydev = None
    raw_youtube = None
    raw_reddit_enriched = []
    reddit_error = None
    x_error = None
    dailydev_error = None
    youtube_error = None

    # Check if WebSearch is needed (always needed in web-only mode)
    web_needed = sources in ("all", "web", "reddit-web", "x-web")

    # Web-only mode: no API calls needed, Claude handles everything
    if sources == "web":
        if progress:
            progress.start_web_only()
            progress.end_web_only()
        return (reddit_items, x_items, True, raw_openai, raw_xai, raw_reddit_enriched,
                reddit_error, x_error, dailydev_items, raw_dailydev, dailydev_error,
                youtube_items, raw_youtube, youtube_error)

    # Determine which searches to run
    run_reddit_src = sources in ("both", "reddit", "all", "reddit-web")
    run_x_src = sources in ("both", "x", "all", "x-web")

    # Count workers needed
    worker_count = sum([run_reddit_src, run_x_src, run_dailydev, run_youtube])
    worker_count = max(worker_count, 1)

    # Run searches in parallel
    reddit_future = None
    x_future = None
    dailydev_future = None
    youtube_future = None

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        # Submit searches
        if run_reddit_src:
            if progress:
                progress.start_reddit()
            reddit_future = executor.submit(
                _search_reddit, topic, config, selected_models,
                from_date, to_date, depth, mock
            )

        if run_x_src:
            if progress:
                progress.start_x()
            x_future = executor.submit(
                _search_x, topic, config, selected_models,
                from_date, to_date, depth, mock
            )

        if run_dailydev:
            if progress:
                progress.start_dailydev()
            dailydev_future = executor.submit(
                _search_dailydev, topic, config,
                from_date, to_date, depth, mock
            )

        if run_youtube:
            if progress:
                progress.start_youtube()
            youtube_future = executor.submit(
                _search_youtube, topic, config,
                from_date, to_date, depth, mock
            )

        # Collect results
        if reddit_future:
            try:
                reddit_items, raw_openai, reddit_error = reddit_future.result()
                if reddit_error and progress:
                    progress.show_error(f"Reddit error: {reddit_error}")
            except Exception as e:
                reddit_error = f"{type(e).__name__}: {e}"
                if progress:
                    progress.show_error(f"Reddit error: {e}")
            if progress:
                progress.end_reddit(len(reddit_items))

        if x_future:
            try:
                x_items, raw_xai, x_error = x_future.result()
                if x_error and progress:
                    progress.show_error(f"X error: {x_error}")
            except Exception as e:
                x_error = f"{type(e).__name__}: {e}"
                if progress:
                    progress.show_error(f"X error: {e}")
            if progress:
                progress.end_x(len(x_items))

        if dailydev_future:
            try:
                dailydev_items, raw_dailydev, dailydev_error = dailydev_future.result()
                if dailydev_error and progress:
                    progress.show_error(f"DailyDev error: {dailydev_error}")
            except Exception as e:
                dailydev_error = f"{type(e).__name__}: {e}"
                if progress:
                    progress.show_error(f"DailyDev error: {e}")
            if progress:
                progress.end_dailydev(len(dailydev_items))

        if youtube_future:
            try:
                youtube_items, raw_youtube, youtube_error = youtube_future.result()
                if youtube_error and progress:
                    progress.show_error(f"YouTube error: {youtube_error}")
            except Exception as e:
                youtube_error = f"{type(e).__name__}: {e}"
                if progress:
                    progress.show_error(f"YouTube error: {e}")
            if progress:
                progress.end_youtube(len(youtube_items))

    # Enrich Reddit items with real data (sequential, but with error handling per-item)
    if reddit_items:
        if progress:
            progress.start_reddit_enrich(1, len(reddit_items))

        for i, item in enumerate(reddit_items):
            if progress and i > 0:
                progress.update_reddit_enrich(i + 1, len(reddit_items))

            try:
                if mock:
                    mock_thread = load_fixture("reddit_thread_sample.json")
                    reddit_items[i] = reddit_enrich.enrich_reddit_item(item, mock_thread)
                else:
                    reddit_items[i] = reddit_enrich.enrich_reddit_item(item)
            except Exception as e:
                # Log but don't crash - keep the unenriched item
                if progress:
                    progress.show_error(f"Enrich failed for {item.get('url', 'unknown')}: {e}")

            raw_reddit_enriched.append(reddit_items[i])

        if progress:
            progress.end_reddit_enrich()

    return (reddit_items, x_items, web_needed, raw_openai, raw_xai, raw_reddit_enriched,
            reddit_error, x_error, dailydev_items, raw_dailydev, dailydev_error,
            youtube_items, raw_youtube, youtube_error)


def main():
    parser = argparse.ArgumentParser(
        description="Research a topic from the last 30 days on Reddit + X"
    )
    parser.add_argument("topic", nargs="?", help="Topic to research")
    parser.add_argument("--mock", action="store_true", help="Use fixtures")
    parser.add_argument(
        "--emit",
        choices=["compact", "json", "md", "context", "path"],
        default="compact",
        help="Output mode",
    )
    parser.add_argument(
        "--sources",
        choices=["auto", "reddit", "x", "both"],
        default="auto",
        help="Source selection",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Faster research with fewer sources (8-12 each)",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Comprehensive research with more sources (50-70 Reddit, 40-60 X)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging",
    )
    parser.add_argument(
        "--include-web",
        action="store_true",
        help="Include general web search alongside Reddit/X (lower weighted)",
    )
    parser.add_argument(
        "--dailydev",
        action="store_true",
        help="Include daily.dev developer articles",
    )
    parser.add_argument(
        "--youtube",
        action="store_true",
        help="Include YouTube videos via TubeLab (5 credits/search)",
    )

    args = parser.parse_args()

    # Enable debug logging if requested
    if args.debug:
        os.environ["LAST30DAYS_DEBUG"] = "1"
        # Re-import http to pick up debug flag
        from lib import http as http_module
        http_module.DEBUG = True

    # Determine depth
    if args.quick and args.deep:
        print("Error: Cannot use both --quick and --deep", file=sys.stderr)
        sys.exit(1)
    elif args.quick:
        depth = "quick"
    elif args.deep:
        depth = "deep"
    else:
        depth = "default"

    if not args.topic:
        print("Error: Please provide a topic to research.", file=sys.stderr)
        print("Usage: python3 last30days.py <topic> [options]", file=sys.stderr)
        sys.exit(1)

    # Load config
    config = env.get_config()

    # Check available sources
    available = env.get_available_sources(config)

    # Mock mode can work without keys
    if args.mock:
        if args.sources == "auto":
            sources = "both"
        else:
            sources = args.sources
    else:
        # Validate requested sources against available
        sources, error = env.validate_sources(args.sources, available, args.include_web)
        if error:
            # If it's a warning about WebSearch fallback, print but continue
            if "WebSearch fallback" in error:
                print(f"Note: {error}", file=sys.stderr)
            else:
                print(f"Error: {error}", file=sys.stderr)
                sys.exit(1)

    # Get date range
    from_date, to_date = dates.get_date_range(30)

    # Check what keys are missing for promo messaging
    missing_keys = env.get_missing_keys(config)

    # Initialize progress display
    progress = ui.ProgressDisplay(args.topic, show_banner=True)

    # Show promo for missing keys BEFORE research
    if missing_keys != 'none':
        progress.show_promo(missing_keys)

    # Show migration notice if user has old XAI_API_KEY
    if config.get('_HAS_OLD_XAI_KEY'):
        sys.stderr.write(
            "\n💡 Migration: Rename XAI_API_KEY to TWITTERAPI_IO_KEY in ~/.config/last30days/.env\n"
            "   (XAI_API_KEY still works but will be removed in a future version)\n\n"
        )

    # Select models
    if args.mock:
        # Use mock models
        mock_openai_models = load_fixture("models_openai_sample.json").get("data", [])
        selected_models = models.get_models(
            {
                "OPENAI_API_KEY": "mock",
                **config,
            },
            mock_openai_models,
        )
    else:
        selected_models = models.get_models(config)

    # Determine mode string
    if sources == "all":
        mode = "all"  # reddit + x + web
    elif sources == "both":
        mode = "both"  # reddit + x
    elif sources == "reddit":
        mode = "reddit-only"
    elif sources == "reddit-web":
        mode = "reddit-web"
    elif sources == "x":
        mode = "x-only"
    elif sources == "x-web":
        mode = "x-web"
    elif sources == "web":
        mode = "web-only"
    else:
        mode = sources

    # Determine if DailyDev should run
    # Auto-enable when key present + not web-only mode, or explicit --dailydev flag
    should_run_dailydev = (
        args.dailydev
        or (bool(config.get('DAILYDEV_API_KEY')) and sources != "web")
        or args.mock
    )

    # YouTube is explicit opt-in only (expensive: 5 credits/search)
    should_run_youtube = (
        args.youtube and (bool(config.get('TUBELAB_API_KEY')) or args.mock)
    )

    # Run research
    (reddit_items, x_items, web_needed, raw_openai, raw_xai, raw_reddit_enriched,
     reddit_error, x_error, dailydev_items, raw_dailydev, dailydev_error,
     youtube_items, raw_youtube, youtube_error) = run_research(
        args.topic,
        sources,
        config,
        selected_models,
        from_date,
        to_date,
        depth,
        args.mock,
        progress,
        run_dailydev=should_run_dailydev,
        run_youtube=should_run_youtube,
    )

    # Processing phase
    progress.start_processing()

    # Normalize items
    normalized_reddit = normalize.normalize_reddit_items(reddit_items, from_date, to_date)
    normalized_x = normalize.normalize_x_items(x_items, from_date, to_date)
    normalized_dailydev = normalize.normalize_dailydev_items(dailydev_items, from_date, to_date)
    normalized_youtube = normalize.normalize_youtube_items(youtube_items, from_date, to_date)

    # Hard date filter: exclude items with verified dates outside the range
    # This is the safety net - even if prompts let old content through, this filters it
    filtered_reddit = normalize.filter_by_date_range(normalized_reddit, from_date, to_date)
    filtered_x = normalize.filter_by_date_range(normalized_x, from_date, to_date)
    filtered_dailydev = normalize.filter_by_date_range(normalized_dailydev, from_date, to_date)
    filtered_youtube = normalize.filter_by_date_range(normalized_youtube, from_date, to_date)

    # Score items
    scored_reddit = score.score_reddit_items(filtered_reddit)
    scored_x = score.score_x_items(filtered_x)
    scored_dailydev = score.score_dailydev_items(filtered_dailydev)
    scored_youtube = score.score_youtube_items(filtered_youtube)

    # Sort items
    sorted_reddit = score.sort_items(scored_reddit)
    sorted_x = score.sort_items(scored_x)
    sorted_dailydev = score.sort_items(scored_dailydev)
    sorted_youtube = score.sort_items(scored_youtube)

    # Dedupe items
    deduped_reddit = dedupe.dedupe_reddit(sorted_reddit)
    deduped_x = dedupe.dedupe_x(sorted_x)
    deduped_dailydev = dedupe.dedupe_dailydev(sorted_dailydev)
    deduped_youtube = dedupe.dedupe_youtube(sorted_youtube)

    progress.end_processing()

    # Create report
    report = schema.create_report(
        args.topic,
        from_date,
        to_date,
        mode,
        selected_models.get("openai"),
        selected_models.get("xai"),
    )
    report.reddit = deduped_reddit
    report.x = deduped_x
    report.dailydev = deduped_dailydev
    report.youtube = deduped_youtube
    report.reddit_error = reddit_error
    report.x_error = x_error
    report.dailydev_error = dailydev_error
    report.youtube_error = youtube_error

    # Generate context snippet
    report.context_snippet_md = render.render_context_snippet(report)

    # Write outputs
    render.write_outputs(report, raw_openai, raw_xai, raw_reddit_enriched, raw_dailydev, raw_youtube)

    # Show completion
    if sources == "web":
        progress.show_web_only_complete()
    else:
        progress.show_complete(len(deduped_reddit), len(deduped_x), len(deduped_dailydev), len(deduped_youtube))

    # Output result
    output_result(report, args.emit, web_needed, args.topic, from_date, to_date, missing_keys)


def output_result(
    report: schema.Report,
    emit_mode: str,
    web_needed: bool = False,
    topic: str = "",
    from_date: str = "",
    to_date: str = "",
    missing_keys: str = "none",
):
    """Output the result based on emit mode."""
    if emit_mode == "compact":
        print(render.render_compact(report, missing_keys=missing_keys))
    elif emit_mode == "json":
        print(json.dumps(report.to_dict(), indent=2))
    elif emit_mode == "md":
        print(render.render_full_report(report))
    elif emit_mode == "context":
        print(report.context_snippet_md)
    elif emit_mode == "path":
        print(render.get_context_path())

    # Output WebSearch instructions if needed
    if web_needed:
        print("\n" + "="*60)
        print("### WEBSEARCH REQUIRED ###")
        print("="*60)
        print(f"Topic: {topic}")
        print(f"Date range: {from_date} to {to_date}")
        print("")
        print("Claude: Use your WebSearch tool to find 8-15 relevant web pages.")
        print("EXCLUDE: reddit.com, x.com, twitter.com (already covered above)")
        print("INCLUDE: blogs, docs, news, tutorials from the last 30 days")
        print("")
        print("After searching, synthesize WebSearch results WITH the Reddit/X")
        print("results above. WebSearch items should rank LOWER than comparable")
        print("Reddit/X items (they lack engagement metrics).")
        print("="*60)


if __name__ == "__main__":
    main()
