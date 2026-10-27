"""Measure the presentation autocomplete preset on this computer."""
import argparse
import json
from pathlib import Path
from changelens.local_ai import LocalAI, presentation_check


def run(output):
    report=presentation_check(LocalAI())
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path("evaluation/local_ai_completion.json"))
    run(parser.parse_args().output)
