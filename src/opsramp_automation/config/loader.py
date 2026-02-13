"""
Config loader — reads a client YAML file and returns a validated ClientConfig.

Supports environment variable interpolation in YAML values using ${VAR_NAME} syntax.
"""

import os
import re
import yaml

from .schema import ClientConfig


def _interpolate_env_vars(value: str) -> str:
    """
    Replace ${VAR_NAME} patterns in a string with environment variable values.
    Example: "${CLIENT_SECRET}" → actual env var value.
    Raises ValueError if the env var is not set.
    """
    pattern = re.compile(r"\$\{(\w+)\}")

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            raise ValueError(
                f"Environment variable '{var_name}' referenced in config "
                f"but not set."
            )
        return env_val

    return pattern.sub(replacer, value)


def _walk_and_interpolate(obj):
    """Recursively walk a dict/list and interpolate env vars in strings."""
    if isinstance(obj, dict):
        return {k: _walk_and_interpolate(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_walk_and_interpolate(item) for item in obj]
    elif isinstance(obj, str):
        return _interpolate_env_vars(obj)
    return obj


def load_config(config_path: str) -> ClientConfig:
    """
    Load and validate a client configuration from a YAML file.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        A validated ClientConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If env vars referenced in config are missing.
        pydantic.ValidationError: If the config fails schema validation.
    """
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain a YAML mapping, got {type(raw)}")

    # Interpolate environment variables
    interpolated = _walk_and_interpolate(raw)

    # Validate against Pydantic schema
    config = ClientConfig(**interpolated)
    return config
