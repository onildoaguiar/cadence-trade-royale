import unittest

from trade_royale.creatures import CREATURES
from trade_royale.match import League


def _mean(history: list[dict], key: str, start: int, end: int) -> float:
    rows = history[start:end]
    if not rows:
        return 0.0
    return sum(row[key] for row in rows) / len(rows)


class RepairTest(unittest.TestCase):
    def test_two_brains_find_the_growing_trend(self) -> None:
        league = League(creatures=CREATURES[:2], nursery_moments=360, seed=7)
        league.raise_all()
        for row in league.progress["raised"]:
            self.assertGreaterEqual(row["reply_rate"], 0.8, row)
        self.assertEqual(league.regime, "viral")
        self.assertEqual(league.winners["viral"], "post")
        for _ in range(430):
            league.step()
        # They walk in on the quiet trend. The growing one is what pays.
        self.assertLess(_mean(league.history, "live", 0, 40), 0.5)
        self.assertGreaterEqual(_mean(league.history, "live", 390, 430), 0.85)
        self.assertLess(_mean(league.history, "frozen", 390, 430), 0.15)
        self.assertGreater(max(league.scores.values()), 0.0)


if __name__ == "__main__":
    unittest.main()
