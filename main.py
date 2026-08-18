#!/usr/bin/env python3
"""Demand Seeker command-line pipeline."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

import config
from analysis.classifier import classify_service
from analysis.demand_analyzer import analyze
from analysis.pain_point_extractor import extract_pain_points
from analysis.reporting import terminal_summary, write_reports
from analysis.technology_extractor import extract_technologies
from collectors.google_trends import GoogleTrendsCollector
from collectors.reddit import RedditRSSCollector
from collectors.upwork import UpworkCSVCollector
from crm.client import CRMClient
from storage.database import Database


def configure_logging() -> None:
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_PATH, encoding="utf-8")],
    )


def collectors():
    enabled = []
    if config.COLLECT_UPWORK:
        enabled.append(UpworkCSVCollector(config.UPWORK_CSV_PATH))
    if config.COLLECT_REDDIT:
        enabled.append(RedditRSSCollector(config.REDDIT_QUERIES, config.REDDIT_LIMIT_PER_QUERY,
                                          config.REDDIT_USER_AGENT))
    if config.COLLECT_GOOGLE_TRENDS:
        enabled.append(GoogleTrendsCollector(config.GOOGLE_TRENDS_KEYWORDS, config.GOOGLE_TRENDS_GEO))
    return enabled


def collect(db: Database) -> None:
    logger = logging.getLogger("collect")
    totals: dict[str, int] = {}
    for collector in collectors():
        logger.info("collector start: %s", collector.name)
        try:
            # DATA CAME FROM collector -> normalized Observation. Transformation below
            # adds business service, named technology, and customer pain-point labels.
            observations = collector.collect()
            for item in observations:
                item.service_category = classify_service(item.title, item.description)
                item.technologies = extract_technologies(item.title, item.description)
                item.pain_points = extract_pain_points(item.title, item.description)
                totals[item.service_category] = totals.get(item.service_category, 0) + 1
            inserted, duplicates = db.save_observations(observations)
            # DATA GOES NEXT to local SQLite; raw items do not go to the CRM.
            logger.info("collector end: %s collected=%d inserted=%d duplicates=%d",
                        collector.name, len(observations), inserted, duplicates)
        except Exception:
            logger.exception("collector failed: %s (continuing with remaining sources)", collector.name)
    logger.info("classification totals: %s", totals)


def build_report(db: Database) -> dict:
    # Two long periods are required for month-over-month comparison.
    observations = db.fetch_observations(datetime.now(timezone.utc) - timedelta(days=config.DAYS_LONG * 2 + 1))
    report = analyze(observations)
    paths = write_reports(report, config.PROCESSED_DIR)
    db.save_report(report)
    logging.getLogger("report").info("reports written: %s, %s", *paths)
    return report


def load_report(db: Database) -> dict:
    path = config.PROCESSED_DIR / "latest_market_report.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else build_report(db)


def sync_crm(report: dict) -> None:
    logger = logging.getLogger("crm")
    if not config.CRM_SYNC_ENABLED:
        logger.info("CRM sync disabled; set CRM_SYNC_ENABLED=true to enable")
        return
    client = CRMClient(config.CRM_BASE_URL, config.BOT_API_SECRET, config.CRM_MARKET_DEMAND_ENDPOINT)
    result = client.sync(report)
    logger.info("CRM sync complete: %s", result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research technical-service market demand")
    parser.add_argument("--collect", action="store_true", help="collect and store new observations only")
    parser.add_argument("--analyze", action="store_true", help="analyze local history and generate reports")
    parser.add_argument("--report", action="store_true", help="print the latest report (generate if absent)")
    parser.add_argument("--sync-crm", action="store_true", help="send the latest aggregates when CRM sync is enabled")
    parser.add_argument("--google-play", action="store_true", help="run the independent Google Play niche service")
    parser.add_argument("--trends", action="store_true", help="run the attention-velocity trends service")
    parser.add_argument("--trends-cadence", choices=("daily", "weekly", "monthly"), default="weekly",
                        help="select the trends calculation/fetch cadence")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    db = Database(config.DATABASE_PATH)
    db.initialize()
    selected = any((args.collect, args.analyze, args.report, args.sync_crm, args.google_play, args.trends))
    report = None
    if not selected:
        collect(db)
        report = build_report(db)
        print(terminal_summary(report))
        sync_crm(report)
        return 0
    if args.collect:
        collect(db)
    if args.analyze:
        report = build_report(db)
    if args.report:
        report = report or load_report(db)
        print(terminal_summary(report))
    if args.sync_crm:
        report = report or load_report(db)
        sync_crm(report)
    if args.google_play:
        from services.google_play import GooglePlayService
        from services.google_play.reporting import terminal_report
        run = GooglePlayService().run()
        print(terminal_report(run.report))
        logging.getLogger("google_play").info("report written: %s", run.report_path)
    if args.trends:
        from services.trends import TrendsService
        from services.trends.reporting import terminal_report as trends_terminal_report
        run = TrendsService().run(args.trends_cadence)
        print(trends_terminal_report(run.report))
        logging.getLogger("trends").info("report written: %s", run.report_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(130)
