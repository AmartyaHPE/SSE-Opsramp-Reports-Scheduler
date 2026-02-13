# SSE-Opsramp-Reports-Scheduler

Automated hourly performance-utilization report scheduler for OpsRamp. Creates 24 analyses per day (one per hour), each covering a 1-hour lookback window, and cleans them up at end-of-day.

## How It Works

```
Day starts (UTC 00:00)
  │
  ├─ Hour 0  → Create analysis (window: prev-day 23:00 – 00:00)
  ├─ Hour 1  → Create analysis (window: 00:00 – 01:00)
  ├─ ...     → (token auto-refreshes before 2-hour expiry)
  ├─ Hour 23 → Create analysis (window: 22:00 – 23:00)
  │
  └─ Cleanup → DELETE all 24 analyses
```

### Token Management

- OAuth tokens expire every **2 hours** (~7199 seconds).
- The script automatically fetches a new token **5 minutes** before expiry (configurable via `token_refresh_margin_seconds` in config).
- No manual token handling needed.

### Report Naming

Each report is named with the pattern:

```
{prefix}-{date}-{startHHMM}-{endHHMM}
```

Example: `hourly-perf-report-2026-02-12-0700-0800`

---

## Prerequisites

- **Python 3.10+** (uses only the standard library — no `pip install` needed)
- Network access to `https://hpe-dev.api.try.opsramp.com`
- Valid OpsRamp API credentials (client_id / client_secret)

---

## Configuration

Edit `config.json`:

| Key                            | Description                                   | Default                                     |
| ------------------------------ | --------------------------------------------- | ------------------------------------------- |
| `base_url`                     | OpsRamp API base URL                          | _(required)_                                |
| `tenant_id`                    | Tenant / client UUID                          | _(required)_                                |
| `client_id`                    | OAuth client ID                               | _(required)_                                |
| `client_secret`                | OAuth client secret                           | _(required)_                                |
| `app_id`                       | Report app type                               | `PERFORMANCE-UTILIZATION`                   |
| `metrics`                      | Metric names to analyze                       | `["system_cpu_utilization"]`                |
| `methods`                      | Aggregation methods                           | `["max"]`                                   |
| `filter_criteria`              | OpsQL filter                                  | `state = "active" AND monitorable = "true"` |
| `report_format`                | Output format(s)                              | `["xlsx"]`                                  |
| `report_name_prefix`           | Name prefix for reports                       | `hourly-perf-report`                        |
| `start_hour`                   | _(reserved for future use)_                   | `0`                                         |
| `token_refresh_margin_seconds` | Refresh token this many seconds before expiry | `300`                                       |

---

## Usage

### Normal 24-hour cycle (run on gateway)

Waits 1 hour between each analysis creation, deletes all at end of day:

```bash
python report_scheduler.py
```

### Dry run (preview without API calls)

```bash
python report_scheduler.py --dry-run
```

### Burst mode (create all 24 immediately)

Creates all 24 analyses back-to-back without waiting. Useful for testing or back-filling:

```bash
python report_scheduler.py --burst
```

### Cleanup specific analyses

```bash
python report_scheduler.py --cleanup <id1> <id2> <id3>
```

### Custom config path

```bash
python report_scheduler.py --config /opt/opsramp/config.json
```

### Verbose logging

```bash
python report_scheduler.py --log-level DEBUG
```

---

## Running as an OpsRamp Process Automation

1. Upload `report_scheduler.py` and `config.json` to the gateway server (e.g., `/opt/opsramp/reports/`).
2. Create a **Process Automation** in OpsRamp:
   - Add a **Script Task** with the command:
     ```
     python3 /opt/opsramp/reports/report_scheduler.py --config /opt/opsramp/reports/config.json
     ```
   - Set the **Resource** to the gateway server.
3. Schedule the automation to run **daily** at your desired start time (e.g., 00:00 UTC).

---

## Architecture

```
report_scheduler.py
├── TokenManager        # OAuth2 token lifecycle with auto-refresh
├── create_analysis()   # POST /analyses with dynamic time windows
├── delete_analysis()   # DELETE /analyses/{id}
├── run_daily_cycle()   # 24-iteration loop with hourly sleep
├── run_burst_mode()    # All 24 at once (no sleep)
└── run_cleanup_only()  # Manual deletion by ID
```

---

## Notes

- SSL verification is disabled (`-k` equivalent) since OpsRamp gateways often use self-signed certificates.
- The script uses **only Python standard library** — no external dependencies.
- All times are in **UTC**.
- If the script is interrupted mid-cycle, you can use `--cleanup` with the logged analysis IDs to delete partial runs.
