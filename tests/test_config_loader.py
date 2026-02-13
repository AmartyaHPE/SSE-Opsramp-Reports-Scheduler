"""Tests for config loader and schema validation."""

import os
import tempfile
import pytest
import yaml

from opsramp_automation.config.loader import load_config
from opsramp_automation.config.schema import ClientConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CONFIG = {
    "client_name": "test-client",
    "base_url": "https://test.api.try.opsramp.com",
    "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "auth": {
        "client_id": "test-id",
        "client_secret": "test-secret",
    },
}


def _write_yaml(data: dict, path: str) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f)


# ---------------------------------------------------------------------------
# Tests — Happy Path
# ---------------------------------------------------------------------------

class TestConfigLoaderHappyPath:
    """Valid configs should load without errors."""

    def test_minimal_config(self, tmp_path):
        cfg_file = tmp_path / "client.yaml"
        _write_yaml(VALID_CONFIG, str(cfg_file))

        config = load_config(str(cfg_file))

        assert isinstance(config, ClientConfig)
        assert config.client_name == "test-client"
        assert config.tenant_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert config.auth.client_id == "test-id"

    def test_defaults_applied(self, tmp_path):
        cfg_file = tmp_path / "client.yaml"
        _write_yaml(VALID_CONFIG, str(cfg_file))

        config = load_config(str(cfg_file))

        # Defaults from schema
        assert config.report.app_id == "PERFORMANCE-UTILIZATION"
        assert config.report.metrics == ["system_cpu_utilization"]
        assert config.schedule.interval_hours == 1
        assert config.schedule.total_reports_per_day == 24
        assert config.ssl_verify is False
        assert config.log_level == "INFO"

    def test_full_config(self, tmp_path):
        full = {
            **VALID_CONFIG,
            "report": {
                "app_id": "CUSTOM-APP",
                "metrics": ["memory_utilization"],
                "methods": ["avg"],
                "filter_criteria": 'state = "active"',
                "report_format": ["csv"],
                "report_name_prefix": "custom-report",
            },
            "schedule": {
                "interval_hours": 2,
                "total_reports_per_day": 12,
                "cleanup_after_all": False,
                "daily_start_hour_utc": 6,
            },
            "ssl_verify": True,
            "log_level": "DEBUG",
        }
        cfg_file = tmp_path / "client.yaml"
        _write_yaml(full, str(cfg_file))

        config = load_config(str(cfg_file))

        assert config.report.app_id == "CUSTOM-APP"
        assert config.report.metrics == ["memory_utilization"]
        assert config.schedule.interval_hours == 2
        assert config.schedule.total_reports_per_day == 12
        assert config.ssl_verify is True
        assert config.log_level == "DEBUG"


# ---------------------------------------------------------------------------
# Tests — Environment Variable Interpolation
# ---------------------------------------------------------------------------

class TestEnvVarInterpolation:
    """${VAR_NAME} in YAML values should resolve to env vars."""

    def test_env_var_substitution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_CLIENT_ID", "from-env-id")
        monkeypatch.setenv("TEST_CLIENT_SECRET", "from-env-secret")

        data = {
            **VALID_CONFIG,
            "auth": {
                "client_id": "${TEST_CLIENT_ID}",
                "client_secret": "${TEST_CLIENT_SECRET}",
            },
        }
        cfg_file = tmp_path / "client.yaml"
        _write_yaml(data, str(cfg_file))

        config = load_config(str(cfg_file))

        assert config.auth.client_id == "from-env-id"
        assert config.auth.client_secret == "from-env-secret"

    def test_missing_env_var_raises(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "auth": {
                "client_id": "${DOES_NOT_EXIST_XYZ}",
                "client_secret": "ok",
            },
        }
        cfg_file = tmp_path / "client.yaml"
        _write_yaml(data, str(cfg_file))

        with pytest.raises(ValueError, match="DOES_NOT_EXIST_XYZ"):
            load_config(str(cfg_file))


# ---------------------------------------------------------------------------
# Tests — Validation Errors
# ---------------------------------------------------------------------------

class TestConfigValidation:
    """Invalid configs should fail fast with clear errors."""

    def test_missing_required_field(self, tmp_path):
        incomplete = {
            "client_name": "test",
            # missing base_url, tenant_id, auth
        }
        cfg_file = tmp_path / "client.yaml"
        _write_yaml(incomplete, str(cfg_file))

        with pytest.raises(Exception):  # pydantic ValidationError
            load_config(str(cfg_file))

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_invalid_yaml_type(self, tmp_path):
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text("just a string")

        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(str(cfg_file))

    def test_invalid_schedule_values(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "schedule": {
                "interval_hours": 0,  # must be >= 1
            },
        }
        cfg_file = tmp_path / "client.yaml"
        _write_yaml(data, str(cfg_file))

        with pytest.raises(Exception):  # pydantic ValidationError
            load_config(str(cfg_file))
