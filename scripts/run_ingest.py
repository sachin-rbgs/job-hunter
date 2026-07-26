"""Daily pull. Point a scheduler at this, or run it by hand.

  python scripts/run_ingest.py            # pull, score, tailor
  python scripts/run_ingest.py --no-llm   # pull and score only, no spend
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import create_tables  # noqa: E402
from app.pipeline import ingest  # noqa: E402


def main() -> None:
    create_tables()
    tailor = "--no-llm" not in sys.argv

    result = ingest(tailor=tailor)
    if result.get("error"):
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    print(f"pulled     {result['pulled']}")
    print(f"qualified  {result['qualified']}")
    print(f"tailored   {result['generated']}")
    print(f"cost       ${result['llm_cost_usd'] + result['apify_cost_usd']:.4f} "
          f"(llm ${result['llm_cost_usd']:.4f}, apify ${result['apify_cost_usd']:.4f})")
    print("\nper source:")
    for name, info in result["sources"].items():
        if info.get("skipped"):
            print(f"  {name:12} skipped ({info['skipped']})")
        elif info.get("error"):
            print(f"  {name:12} ERROR {info['error']}")
        else:
            print(f"  {name:12} {info['new']:3} new of {info['pulled']}")


if __name__ == "__main__":
    main()
