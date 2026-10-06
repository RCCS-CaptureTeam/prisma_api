import os
import sys
from pathlib import Path

import pandas as pd
import platformdirs
import yaml

### Helper functions for config management

# Internal function to get user config directory
def _user_config_dir() -> Path:
    """Return cross-platform user config directory Path."""
    if platformdirs is not None:
        return Path(platformdirs.user_config_dir("prisma_api", "prisma-api"))
    return Path.home() / ".prisma_api"

# Internal function to get path to config.yaml
def get_config_path() -> Path:
    """Get the path to the config.yaml file (ensuring parent exists)."""
    cfg_dir = _user_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "config.yaml"

# Public function to get config.yaml path as string
def locate_config() -> str:
    """Return the config.yaml path as a string (ensuring parent exists)."""
    return str(get_config_path())

# Internal function to load config from config.yaml
def load_config():
    """Load configuration from config.yaml if it exists; return dict or None."""
    cfg_file = get_config_path()
    if not cfg_file.exists():
        return None
    if yaml is None:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")
    with open(cfg_file, "r") as f:
        cfg = yaml.safe_load(f) or {}

    return cfg

# Internal function to create config.yaml
def create_config_file(api_key: str | None = None):
    """
    Create config.yaml. If api_key is None, prompt via CLI.

    Args:
        api_key: PrISMa API key.

    Returns:
        dict: The config that was written.
    """
    if yaml is None:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")

    if not api_key:
        if not sys.stdin or not sys.stdin.isatty():
            raise RuntimeError(
                f"No PrISMa config file at {get_config_path()} and no API key in the "
                f"environment. Set {', '.join(ENV_VARS)} (at least PRISMA_API_KEY), "
                "or run interactively once to create the config file."
            )
        val = input("Enter your PrISMa API key: ").strip()
        api_key = val

    cfg = {
        "api_key": api_key,
        "created": pd.Timestamp.now().isoformat(),
    }

    cfg_file = get_config_path()
    with open(cfg_file, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return cfg

# Environment variables read when no config file exists (or use_config_file=False)
ENV_VARS = ("PRISMA_API_KEY", "PRISMA_API_DEV_API_KEY", "PRISMA_API_DEV_HOST_PORT")


def config_from_env():
    """
    Build a config dict from PRISMA_API_* environment variables.

    Returns None if none of them is set.
    """
    if not any(os.getenv(name) for name in ENV_VARS):
        return None
    prod_key = os.getenv("PRISMA_API_KEY", "")
    return {
        "api_key": prod_key,
        "dev_api_key": os.getenv("PRISMA_API_DEV_API_KEY", prod_key),
        "dev_host_port": os.getenv("PRISMA_API_DEV_HOST_PORT", "8000"),
    }


# Get or create config - intended use by initialisation of main prisma_api class
def get_or_create_config():
    """
    Return the config, in order of preference:

    1. config.yaml, if it exists;
    2. PRISMA_API_* environment variables (nothing is written to disk);
    3. an interactive prompt, which creates config.yaml. Without a terminal
       (e.g. CI) this raises instead of blocking on input().
    """
    cfg = load_config()
    if cfg is not None:
        return cfg
    cfg = config_from_env()
    if cfg is not None:
        return cfg
    return create_config_file()


# Update dev flag in config.yaml - functional tool for user
def update_dev_mode(dev: bool):
    """
    Update the dev flag in config.yaml.

    Args:
        dev: Boolean flag to enable/disable dev mode.

    Returns:
        dict: Updated config.
    """
    if yaml is None:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")

    cfg = load_config()
    if cfg is None:
        cfg = {}
    cfg["dev"] = dev
    cfg["modified"] = pd.Timestamp.now().isoformat()

    cfg_file = get_config_path()
    with open(cfg_file, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return cfg

# Update dev host in config.yaml - functional tool for user
def update_dev_host_port(dev_host_port: str):
    """
    Update the dev host in config.yaml.

    Args:
        dev_host_port: Hostname or base URL for dev API.

    Returns:
        dict: Updated config.
    """
    if yaml is None:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")

    cfg = load_config()
    if cfg is None:
        cfg = {}

    cfg["dev_host_port"] = dev_host_port
    cfg["modified"] = pd.Timestamp.now().isoformat()

    cfg_file = get_config_path()
    with open(cfg_file, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return cfg

# Update API key in config.yaml - functional tool for user
def update_api_key(api_key: str):
    """
    Update the API key in config.yaml.

    Args:
        api_key: New PrISMa API key.

    Returns:
        dict: Updated config.
    """
    if yaml is None:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")

    cfg = load_config()
    if cfg is None:
        cfg = {}

    cfg["api_key"] = api_key
    cfg["modified"] = pd.Timestamp.now().isoformat()

    cfg_file = get_config_path()
    with open(cfg_file, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return cfg


# Update API key in config.yaml - functional tool for user
def update_dev_api_key(dev_api_key: str):
    """
    Update the API key in config.yaml.

    Args:
        dev_api_key: New PrISMa API key.

    Returns:
        dict: Updated config.
    """
    if yaml is None:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")

    cfg = load_config()
    if cfg is None:
        cfg = {}

    cfg["dev_api_key"] = dev_api_key
    cfg["modified"] = pd.Timestamp.now().isoformat()

    cfg_file = get_config_path()
    with open(cfg_file, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return cfg

