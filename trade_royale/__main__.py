"""Headless drill: nursery, a calm gm stretch, then the flip.

    python -m trade_royale
"""

from __future__ import annotations

import argparse

from .match import League


def _window(history: list[dict], key: str, start: int, end: int) -> float:
    rows = history[start:end]
    if not rows:
        return 0.0
    return sum(row[key] for row in rows) / len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Trade Royale drill and print the rates.")
    parser.add_argument("--moments", type=int, default=360, help="nursery moments per brain")
    parser.add_argument("--gm", type=int, default=40, help="pit moments on gm before the flip")
    parser.add_argument("--panic", type=int, default=400, help="pit moments after the flip")
    args = parser.parse_args()

    league = League(nursery_moments=args.moments)

    def show(progress: dict) -> None:
        if progress["moment"] % 120 == 0 or progress["moment"] == progress["moments"]:
            print(
                f"  raising {progress['name']:12} "
                f"{progress['moment']:3d}/{progress['moments']}  "
                f"reply {progress['reply_rate']:.0%}",
                flush=True,
            )

    print("nursery", flush=True)
    league.raise_all(show)
    for row in league.progress["raised"]:
        print(f"  {row['name']:12} arrived replying {row['reply_rate']:.0%}  refusals {row['refusals']}")

    for _ in range(args.gm):
        league.step()
    print(
        f"gm   last {args.gm:3d}   "
        f"live {_window(league.history, 'live', 0, args.gm):.0%}   "
        f"frozen {_window(league.history, 'frozen', 0, args.gm):.0%}"
    )
    league.flip()
    marks = {40, 120, 180, 220, args.panic}
    for step in range(1, args.panic + 1):
        league.step()
        if step in marks or step == args.panic:
            start = args.gm + max(0, step - 30)
            print(
                f"panic @{step:3d}   "
                f"live {_window(league.history, 'live', start, args.gm + step):.0%}   "
                f"frozen {_window(league.history, 'frozen', start, args.gm + step):.0%}   "
                f"random {_window(league.history, 'random', start, args.gm + step):.0%}"
            )
    print(
        "totals",
        {key: round(value, 1) for key, value in league.totals.items()},
    )


if __name__ == "__main__":
    main()
