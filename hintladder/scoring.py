"""Three-view diagnostic on identical ordinary response token IDs."""
import math
from statistics import mean


def three_view_scores(client, prompts, target_ids, *, clip=5.0):
    if set(prompts) != {"clean", "hinted", "hint_only"} or not target_ids:
        raise ValueError("three aligned views and nonempty target tokens are required")
    if not math.isfinite(clip) or clip <= 0:
        raise ValueError("clip must be finite and positive")
    values = {name: client.score_tokens(prompt, target_ids) for name, prompt in prompts.items()}
    if any(len(row) != len(target_ids) or not all(math.isfinite(v) for v in row) for row in values.values()):
        raise ValueError("teacher-forced scores do not align with target IDs")
    lift = [max(-clip, min(clip, q - p)) for p, q in zip(values["clean"], values["hinted"])]
    copy = [max(0, min(clip, h - p)) for p, h in zip(values["clean"], values["hint_only"])]
    return {"target_ids": list(target_ids), "log_probs": values,
            "hint_ladder/lift": mean(lift), "hint_ladder/copy": mean(copy), "copy_is_diagnostic_only": True}
