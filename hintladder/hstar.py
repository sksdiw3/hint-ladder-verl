import math
import random

LEVELS = ("L0", "L1", "L2", "L3")


def classify(rates, sufficient=0.5):
    """The contract's pass@k fields are k-trial empirical success fractions."""
    if set(rates) != set(LEVELS) or not 0 < sufficient <= 1:
        raise ValueError("all four levels and a threshold in (0, 1] are required")
    if any(not math.isfinite(float(x)) or not 0 <= x <= 1 for x in rates.values()):
        raise ValueError("probe rates must be finite fractions")
    level = next((key for key in LEVELS if rates[key] >= sufficient), None)
    if level == "L0":
        band = "mastered"
    elif level is None:
        band = "unreachable"
    elif level == "L3":
        band = "oracle_only"
    elif rates["L0"] > 0:
        band = "frontier"
    else:
        band = "scaffolded"
    return {"h_star": level, "band": band,
            "monotone": all(rates[a] <= rates[b] for a, b in zip(LEVELS, LEVELS[1:]))}


def random_level_map(games, seed):
    rng = random.Random(seed)
    return {game: rng.choice(LEVELS[1:]) for game in sorted(set(games))}
