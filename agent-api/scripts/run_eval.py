from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

CURRENT = Path(__file__).resolve()
AGENT_API_ROOT = CURRENT.parents[1]
if str(AGENT_API_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_API_ROOT))

from app.evaluation import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed offline evaluation cases for the finance ticket Agent.")
    parser.add_argument(
        "--cases",
        default=str(CURRENT.parents[2] / "eval_cases" / "finance_tickets.json"),
        help="Path to eval case JSON file.",
    )
    parser.add_argument("--output", help="Optional path to write JSON summary.")
    args = parser.parse_args()

    summary = run_evaluation(Path(args.cases))
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
