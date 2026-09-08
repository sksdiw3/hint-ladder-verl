from enum import Enum
import os
from pathlib import Path
import posixpath


class Level(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    FULLPATH = "FULLPATH"
    HINTER = "HINTER"


def data_root() -> Path:
    return Path(os.environ["ALFWORLD_DATA"]).expanduser().resolve()


def normalize_gamefile(value, root=None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("gamefile must be a nonempty path string")
    value = value.strip()
    if "\\" in value or "\n" in value or "\r" in value:
        raise ValueError("gamefile must use POSIX path separators")
    path = Path(posixpath.normpath(value))
    if path.is_absolute():
        path = path.resolve().relative_to(Path(root).resolve() if root else data_root())
    if path.as_posix() in (".", "") or ".." in path.parts:
        raise ValueError("gamefile must stay below ALFWORLD_DATA")
    return path.as_posix()


def read_game_list(path) -> list[str]:
    rows = [normalize_gamefile(row) for row in Path(path).read_text().splitlines() if row.strip()]
    if not rows:
        raise ValueError(f"empty game list: {path}")
    return rows


def experiment_name(config_path, seed: int) -> str:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    return f"{Path(config_path).stem}_seed{seed}"
