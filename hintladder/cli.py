"""The only user-facing launcher. All relative artifact paths are repo-relative."""
import argparse
import importlib
import os

from .config import load_config
from .io import ROOT

STAGES = ("build-privilege-bank", "build-hint-bank", "train-student", "eval-behavior",
          "e1-audit", "e3-probe", "train-hinter", "alternate")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--config", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--checkpoint")
    args = parser.parse_args(argv)
    if args.seed < 0:
        parser.error("--seed must be nonnegative")
    from pathlib import Path
    path = Path(args.config).resolve()
    config, inputs = load_config(path)
    config["stage.seed"] = args.seed
    os.chdir(ROOT)
    module = importlib.import_module("hintladder.stages." + args.stage.replace("-", "_"))
    module.run(config, path, args.seed, args.checkpoint, inputs)


if __name__ == "__main__":
    main()
