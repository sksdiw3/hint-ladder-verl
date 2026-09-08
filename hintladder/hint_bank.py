import json
from pathlib import Path

from .io import read_jsonl, write_jsonl
from .keys import Level, normalize_gamefile


def write_bank(path, rows):
    keys = set()
    normalized = []
    for source in rows:
        row = dict(source)
        row["gamefile"] = normalize_gamefile(row["gamefile"])
        row["level"] = Level(row["level"]).value
        key = (row["gamefile"], row["level"])
        if key in keys:
            raise ValueError(f"duplicate hint: {key}")
        keys.add(key)
        if not isinstance(row["hint"], str):
            raise ValueError("hint must be text")
        if row["word_count"] != len(row["hint"].split()):
            raise ValueError(f"word_count mismatch: {key}")
        normalized.append(row)
    write_jsonl(path, normalized)


class HintProvider:
    def __init__(self, bank_dir, *, level=None, level_map_path=None):
        if (level is None) == (level_map_path is None):
            raise ValueError("exactly one of level and level_map_path is required")
        self.level = Level(level).value if level is not None else None
        self.level_map = None
        if level_map_path is not None:
            raw = json.loads(Path(level_map_path).read_text(), object_pairs_hook=_unique_pairs)
            self.level_map = {}
            for game, selected in raw.items():
                game = normalize_gamefile(game)
                if game in self.level_map:
                    raise ValueError(f"duplicate normalized gamefile: {game}")
                self.level_map[game] = Level(selected).value
        levels = {self.level} if self.level else set(self.level_map.values())
        self.rows = {}
        for selected in sorted(levels - {"L0"}):
            path = Path(bank_dir) / f"{selected}.jsonl"
            for row in read_jsonl(path):
                game = normalize_gamefile(row["gamefile"])
                if row["level"] != selected:
                    raise ValueError(f"wrong level in {path}: {row['level']}")
                key = (game, selected)
                if key in self.rows:
                    raise ValueError(f"duplicate hint: {key}")
                self.rows[key] = row

    def level_for(self, gamefile):
        game = normalize_gamefile(gamefile)
        return self.level if self.level is not None else self.level_map[game]

    def get(self, gamefile):
        game = normalize_gamefile(gamefile)
        level = self.level_for(game)
        if level == "L0":
            return ""
        row = self.rows[(game, level)]
        if row["validation"]["ok"] is not True or row["validation"]["errors"]:
            raise ValueError(f"invalid hint for {game}, {level}: {row['validation']['errors']}")
        if not row["hint"].strip() or row["word_count"] != len(row["hint"].split()):
            raise ValueError(f"empty hint or incorrect word count for {game}, {level}")
        return row["hint"]

    def validate_coverage(self, games, *, training=False):
        for game in games:
            self.get(game)
            if training and self.level_map is not None and self.level_for(game) == "L0":
                raise ValueError("exclude mastered/L0 rows from the E3 training list")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
