from pathlib import Path

import tomli_w
import tomllib

CONFIG_FILENAME = "config.toml"


def config_path(directory: Path) -> Path:
    return directory / CONFIG_FILENAME


def load_config(directory: Path) -> dict | None:
    path = config_path(directory)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return tomllib.load(f)


def save_config(directory: Path, config: dict) -> None:
    path = config_path(directory)
    with open(path, "wb") as f:
        tomli_w.dump(config, f)
