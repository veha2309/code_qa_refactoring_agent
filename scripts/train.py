"""Run from workspace: python -m scripts.train"""
from pathlib import Path
import argparse
import json

from changelens.ranking import resources, train_model

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=resources() / "starter_model.json")
    args = parser.parse_args()
    print(json.dumps(train_model(args.output, progress=print), indent=2))

