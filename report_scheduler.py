#!/usr/bin/env python3
"""
OpsRamp Hourly Report Scheduler
================================
Automates creating 24 hourly performance-utilization analyses via OpsRamp API.
- Generates an OAuth token and auto-refreshes before expiry (tokens last ~2 hrs).
- Creates one analysis per hour with a 1-hour lookback window.
- At the end of the day (after all 24 iterations), deletes all created analyses.
- Designed to run on an OpsRamp Gateway server as a Process Automation task.

Usage:
    python report_scheduler.py                  # uses config.json in same dir
    python report_scheduler.py --config /path/to/config.json
    python report_scheduler.py --dry-run        # preview without making API calls
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import ssl
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("report_scheduler")

# Disable SSL verification (OpsRamp gateway often uses self-signed certs, '-k')
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    """Load JSON configuration file."""
    with open(path, "r") as f:
        cfg = json.load(f)
    required = ["base_url", "tenant_id", "client_id", "client_secret"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"Missing required config key: {key}")
    # Defaults
    cfg.setdefault("app_id", "PERFORMANCE-UTILIZATION")
    cfg.setdefault("metrics", ["system_cpu_utilization"])
    cfg.setdefault("methods", ["max"])
    cfg.setdefault("filter_criteria", 'state = "active" AND monitorable = "true"')
    cfg.setdefault("report_format", ["xlsx"])
    cfg.setdefault("report_name_prefix", "hourly-perf-report")
    cfg.setdefault("start_hour", 0)
    cfg.setdefault("token_refresh_margin_seconds", 300)  # refresh 5 min early
    return cfg


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

class TokenManager:
    """Handles OAuth2 client-credentials token lifecycle with auto-refresh."""

    def __init__(self, base_url: str, tenant_id: str, client_id: str,
                 client_secret: str, refresh_margin: int = 300):
        self.token_url = (
            f"{base_url}/tenancy/auth/oauth/token"
        )
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_margin = refresh_margin  # seconds before expiry to refresh
        self._access_token: str | None = None
        self._expires_at: float = 0.0  # epoch timestamp

    def _fetch_token(self) -> None:
        """POST to the token endpoint and cache the result."""
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.token_url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        logger.info("Requesting new OAuth token …")
        try:
            with urllib.request.urlopen(req, context=ssl_ctx) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            logger.error("Token request failed [%s]: %s", e.code, err_body)
            raise

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 7199)
        self._expires_at = time.time() + expires_in
        logger.info(
            "Token acquired (expires in %d s, at %s)",
            expires_in,
            datetime.fromtimestamp(self._expires_at, tz=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    @property
    def token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if (self._access_token is None
                or time.time() >= self._expires_at - self.refresh_margin):
            self._fetch_token()
        return self._access_token  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_post(url: str, token: str, payload: dict) -> dict:
    """Make an authenticated POST request returning JSON."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        logger.error("POST %s failed [%s]: %s", url, e.code, err_body)
        raise


def api_delete(url: str, token: str) -> int:
    """Make an authenticated DELETE request. Returns HTTP status code."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        logger.error("DELETE %s failed [%s]: %s", url, e.code, err_body)
        raise


# ---------------------------------------------------------------------------
# Core workflow
# ---------------------------------------------------------------------------

def build_analysis_payload(cfg: dict, report_name: str,
                           start_time: datetime, end_time: datetime) -> dict:
    """Build the JSON body for analysis creation."""
    return {
        "parameters": {
            "method": cfg["methods"],
            "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "metrics": cfg["metrics"],
            "options": ["resource.id", "resource.name"],
            "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "opsqlQuery": [
                {
                    "groupBy": [],
                    "filterCriteria": cfg["filter_criteria"],
                }
            ],
            "displayMode": "Consolidated List",
            "queryConfig": "summary",
            "analysisPeriod": "Specific Period",
            "client": cfg["tenant_id"],
        },
        "name": report_name,
        "tenantId": cfg["tenant_id"],
        "appId": cfg["app_id"],
        "format": cfg["report_format"],
    }


def create_analysis(cfg: dict, token_mgr: TokenManager,
                    report_name: str, start_time: datetime,
                    end_time: datetime, dry_run: bool = False) -> dict | None:
    """Create a single analysis and return the API response."""
    url = f"{cfg['base_url']}/reporting/api/v3/tenants/{cfg['tenant_id']}/analyses"
    payload = build_analysis_payload(cfg, report_name, start_time, end_time)

    if dry_run:
        logger.info("[DRY-RUN] Would POST to %s", url)
        logger.info("[DRY-RUN] Payload:\n%s", json.dumps(payload, indent=2))
        return {"id": f"dry-run-{report_name}", "name": report_name}

    token = token_mgr.token  # auto-refreshes if close to expiry
    result = api_post(url, token, payload)
    logger.info("Created analysis '%s' → id=%s", report_name, result.get("id"))
    return result


def delete_analysis(cfg: dict, token_mgr: TokenManager,
                    analysis_id: str, dry_run: bool = False) -> None:
    """Delete a single analysis by ID."""
    url = (f"{cfg['base_url']}/reporting/api/v3/tenants/"
           f"{cfg['tenant_id']}/analyses/{analysis_id}")

    if dry_run:
        logger.info("[DRY-RUN] Would DELETE %s", url)
        return

    token = token_mgr.token
    status = api_delete(url, token)
    logger.info("Deleted analysis %s (HTTP %s)", analysis_id, status)


def run_daily_cycle(cfg: dict, dry_run: bool = False) -> None:
    """
    Execute the full 24-hour cycle:
      1. For each hour 0–23, create an analysis covering that hour.
      2. Wait until the next hour boundary (unless --no-wait).
      3. After all 24 analyses, delete them all.
    """
    token_mgr = TokenManager(
        base_url=cfg["base_url"],
        tenant_id=cfg["tenant_id"],
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        refresh_margin=cfg["token_refresh_margin_seconds"],
    )

    today = datetime.now(timezone.utc).date()
    day_str = today.strftime("%Y-%m-%d")
    created_analyses: list[dict] = []

    logger.info("=" * 60)
    logger.info("Starting daily report cycle for %s (UTC)", day_str)
    logger.info("=" * 60)

    for hour in range(24):
        # ── Time window for this report ──────────────────────────
        end_time = datetime(today.year, today.month, today.day,
                            hour, 0, 0, tzinfo=timezone.utc)
        start_time = end_time - timedelta(hours=1)

        # For hour 0, the window is previous-day 23:00 → today 00:00
        window_label = (f"{start_time.strftime('%H%M')}-"
                        f"{end_time.strftime('%H%M')}")
        report_name = f"{cfg['report_name_prefix']}-{day_str}-{window_label}"

        logger.info(
            "── Hour %02d/23 ── window %s → %s  name='%s'",
            hour,
            start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            report_name,
        )

        # ── Create analysis ──────────────────────────────────────
        try:
            result = create_analysis(
                cfg, token_mgr, report_name, start_time, end_time, dry_run
            )
            if result:
                created_analyses.append(result)
        except Exception:
            logger.exception("Failed to create analysis for hour %d", hour)

        # ── Wait until next hour ─────────────────────────────────
        if hour < 23:
            now = datetime.now(timezone.utc)
            next_run = datetime(today.year, today.month, today.day,
                                hour + 1, 0, 0, tzinfo=timezone.utc)
            wait_seconds = (next_run - now).total_seconds()

            if wait_seconds > 0:
                logger.info("Sleeping %.0f s until next hour …", wait_seconds)
                if not dry_run:
                    time.sleep(wait_seconds)
                else:
                    logger.info("[DRY-RUN] Skipping sleep")
            else:
                logger.info("Already past next hour boundary, continuing …")

    # ── End-of-day cleanup: delete all analyses ──────────────────
    logger.info("=" * 60)
    logger.info("Day complete. Deleting %d analyses …", len(created_analyses))
    logger.info("=" * 60)

    for analysis in created_analyses:
        analysis_id = analysis.get("id")
        if not analysis_id:
            logger.warning("No ID found for analysis: %s", analysis)
            continue
        try:
            delete_analysis(cfg, token_mgr, analysis_id, dry_run)
        except Exception:
            logger.exception("Failed to delete analysis %s", analysis_id)

    logger.info("Daily cycle finished.")


# ---------------------------------------------------------------------------
# Immediate / burst mode  (creates all 24 at once, no waiting)
# ---------------------------------------------------------------------------

def run_burst_mode(cfg: dict, dry_run: bool = False) -> None:
    """
    Create all 24 hourly analyses immediately without waiting between them.
    Useful for back-filling or testing. Still deletes at the end.
    """
    token_mgr = TokenManager(
        base_url=cfg["base_url"],
        tenant_id=cfg["tenant_id"],
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        refresh_margin=cfg["token_refresh_margin_seconds"],
    )

    today = datetime.now(timezone.utc).date()
    day_str = today.strftime("%Y-%m-%d")
    created_analyses: list[dict] = []

    logger.info("=" * 60)
    logger.info("BURST MODE – creating all 24 analyses for %s now", day_str)
    logger.info("=" * 60)

    for hour in range(24):
        end_time = datetime(today.year, today.month, today.day,
                            hour, 0, 0, tzinfo=timezone.utc)
        start_time = end_time - timedelta(hours=1)
        window_label = (f"{start_time.strftime('%H%M')}-"
                        f"{end_time.strftime('%H%M')}")
        report_name = f"{cfg['report_name_prefix']}-{day_str}-{window_label}"

        try:
            result = create_analysis(
                cfg, token_mgr, report_name, start_time, end_time, dry_run
            )
            if result:
                created_analyses.append(result)
        except Exception:
            logger.exception("Failed to create analysis for hour %d", hour)
        time.sleep(2)  # small delay to avoid rate-limiting

    logger.info("All 24 analyses created. They will remain until deleted.")
    logger.info("Created analysis IDs:")
    for a in created_analyses:
        logger.info("  • %s  (name=%s)", a.get("id"), a.get("name"))

    # Ask-style: uncomment next block to auto-delete after a pause
    # logger.info("Waiting before end-of-day cleanup …")
    # time.sleep(60)
    # for a in created_analyses:
    #     delete_analysis(cfg, token_mgr, a.get("id", ""), dry_run)

    return created_analyses  # type: ignore[return-value]


def run_cleanup_only(cfg: dict, analysis_ids: list[str],
                     dry_run: bool = False) -> None:
    """Delete a list of analysis IDs (for manual cleanup)."""
    token_mgr = TokenManager(
        base_url=cfg["base_url"],
        tenant_id=cfg["tenant_id"],
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        refresh_margin=cfg["token_refresh_margin_seconds"],
    )
    for aid in analysis_ids:
        try:
            delete_analysis(cfg, token_mgr, aid, dry_run)
        except Exception:
            logger.exception("Failed to delete %s", aid)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="OpsRamp Hourly Report Scheduler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--config", "-c",
        default=os.path.join(os.path.dirname(__file__), "config.json"),
        help="Path to config.json (default: ./config.json)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Preview actions without making real API calls",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--hourly", action="store_true", default=True,
        help="Run the normal 24-hour cycle with 1-hour waits (default)",
    )
    mode.add_argument(
        "--burst", action="store_true",
        help="Create all 24 analyses immediately, no waiting",
    )
    mode.add_argument(
        "--cleanup", nargs="+", metavar="ID",
        help="Delete specific analysis IDs and exit",
    )
    p.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    cfg = load_config(args.config)

    if args.cleanup:
        run_cleanup_only(cfg, args.cleanup, args.dry_run)
    elif args.burst:
        run_burst_mode(cfg, args.dry_run)
    else:
        run_daily_cycle(cfg, args.dry_run)


if __name__ == "__main__":
    main()
