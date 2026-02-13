"""
Config schema definition using Pydantic.

Every client YAML is validated against this schema at startup.
If anything is missing or invalid, the app fails fast with a clear error.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class AuthConfig(BaseModel):
    """OAuth2 client-credentials configuration."""
    client_id: str = Field(..., description="OpsRamp OAuth client ID")
    client_secret: str = Field(..., description="OpsRamp OAuth client secret")
    token_refresh_margin_seconds: int = Field(
        7199,
        ge=0,
        description="Seconds before token expiry to trigger a refresh",
    )


class ReportConfig(BaseModel):
    """Report / analysis creation parameters."""
    app_id: str = Field(
        "PERFORMANCE-UTILIZATION",
        description="OpsRamp report application ID",
    )
    metrics: List[str] = Field(
        default=["system_cpu_utilization"],
        description="Metric names to include in the analysis",
    )
    methods: List[str] = Field(
        default=["max"],
        description="Aggregation methods (max, min, avg, etc.)",
    )
    filter_criteria: str = Field(
        default='state = "active" AND monitorable = "true"',
        description="OpsQL filter for resource selection",
    )
    report_format: List[str] = Field(
        default=["xlsx"],
        description="Output formats (xlsx, csv, pdf)",
    )
    report_name_prefix: str = Field(
        default="hourly-perf-report",
        description="Prefix for generated report names",
    )
    display_mode: str = Field(
        default="Consolidated List",
        description="Report display mode",
    )
    query_config: str = Field(
        default="summary",
        description="Query config type",
    )


class ScheduleConfig(BaseModel):
    """Scheduling parameters."""
    interval_hours: int = Field(
        1,
        ge=1,
        description="How often to create a report (in hours)",
    )
    total_reports_per_day: int = Field(
        24,
        ge=1,
        le=48,
        description="Number of reports to create per day",
    )
    cleanup_after_all: bool = Field(
        True,
        description="Delete all reports at the end of the daily cycle",
    )
    daily_start_hour_utc: int = Field(
        0,
        ge=0,
        le=23,
        description="UTC hour when the daily cycle begins",
    )


class ClientConfig(BaseModel):
    """
    Top-level configuration for a single client.
    Each client YAML maps to one instance of this model.
    """
    client_name: str = Field(
        ...,
        description="Human-readable client/tenant identifier",
    )
    base_url: str = Field(
        ...,
        description="OpsRamp API base URL (no trailing slash)",
    )
    tenant_id: str = Field(
        ...,
        description="OpsRamp tenant UUID",
    )
    auth: AuthConfig
    report: ReportConfig = Field(default_factory=ReportConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    ssl_verify: bool = Field(
        False,
        description="Verify SSL certificates (disable for self-signed certs)",
    )
    log_level: str = Field(
        "INFO",
        description="Logging level for this client run",
    )
