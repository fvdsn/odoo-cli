from pathlib import Path

import tomli_w
import tomllib

CONFIG_FILENAME = "odoo-workspace.toml"
WORKSPACE_CONFIG_KEYS = {"repositories", "postgres", "odoo"}

DEFAULT_CONFIG = {
    "version": "master",
    "odoo_employee": False,
    "user": {
        "name": "",
        "email": "",
    },
    "repositories": {
        "enterprise": False,
        "documentation": False,
        "themes": False,
        "extra_addons": [],
    },
    "remotes": {
        "dev_url": "git@github.com:odoo-dev/{repo}.git",
    },
    "postgres": {
        "host": False,
        "port": False,
        "user": False,
        "password": False,
        "db_name": "odoo-dev",
    },
    "odoo": {
        "admin_user": "admin",
        "admin_password": "admin",
        "http_port": 8069,
        "websocket_port": 8072,
        "data_dir": "~/.local/share/Odoo",
        "demo_data": True,
        "dev_mode": False,
        "install_modules": [],
    },
    "ai": {
        "harnesses": [],
    },
}


def config_path(directory: Path) -> Path:
    return directory / CONFIG_FILENAME


def is_workspace_config(config: dict) -> bool:
    """Return whether a parsed TOML dict looks like an odoo workspace config."""
    return WORKSPACE_CONFIG_KEYS.issubset(config)


def merge_defaults(config: dict, defaults: dict) -> dict:
    merged = defaults.copy()
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            merged[key] = merge_defaults(value, defaults[key])
        else:
            merged[key] = value
    return merged


def normalize_config(config: dict) -> dict:
    """Fill missing workspace config keys while preserving user-provided values."""
    return merge_defaults(config, DEFAULT_CONFIG)


def load_config(directory: Path, *, normalize: bool = True) -> dict | None:
    path = config_path(directory)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        config = tomllib.load(f)
    if normalize and is_workspace_config(config):
        return normalize_config(config)
    return config


def save_config(directory: Path, config: dict) -> None:
    path = config_path(directory)
    with open(path, "wb") as f:
        tomli_w.dump(config, f)
