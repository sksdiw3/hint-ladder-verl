from types import SimpleNamespace

from verl.utils.tracking import Tracking


def test_complete_wandb_row_commits_without_changing_other_backends():
    calls = []
    tracker = Tracking.__new__(Tracking)
    tracker.logger = {
        "wandb": SimpleNamespace(log=lambda **kw: calls.append(("wandb", kw)), finish=lambda **kw: None),
        "console": SimpleNamespace(log=lambda data, step: calls.append(("console", {"data": data, "step": step}))),
    }
    tracker.log({"loss": .5}, step=1, commit=True)
    assert calls == [
        ("wandb", {"data": {"loss": .5}, "step": 1, "commit": True}),
        ("console", {"data": {"loss": .5}, "step": 1}),
    ]
    calls.clear()
    tracker.log({"loss": .4}, step=2)
    assert all("commit" not in kwargs for _, kwargs in calls)
    calls.clear()
    tracker.log({"loss": .3}, step=3, backend=["console"], commit=True)
    assert calls == [("console", {"data": {"loss": .3}, "step": 3})]
