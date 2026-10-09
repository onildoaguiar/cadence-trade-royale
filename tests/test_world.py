import unittest

import numpy as np

from attention_royale.world import (
    ACTIONS,
    BEST,
    INPUTS,
    SENSE_NAMES,
    crowd_from_actions,
    nursery_observation,
    observation,
    payoff,
    pit_clout_sense,
)


class WorldTest(unittest.TestCase):
    def test_meta_sign(self) -> None:
        for regime, verb in BEST.items():
            good = ACTIONS.index(verb)
            self.assertGreater(payoff(good, regime, 0.0), 0.0)
            for other in range(len(ACTIONS)):
                if other == good:
                    continue
                self.assertLess(payoff(other, regime, 0.0), 0.0)

    def test_crowding_softens_and_keeps_the_sign(self) -> None:
        alone = payoff(ACTIONS.index("reply"), "timeline", 0.0)
        piled = payoff(ACTIONS.index("reply"), "timeline", 1.0)
        self.assertGreater(alone, piled)
        self.assertGreater(piled, 0.0)
        wrecked = payoff(ACTIONS.index("reply"), "viral", 1.0)
        self.assertLess(wrecked, 0.0)

    def test_observation_is_a_glow_not_a_label(self) -> None:
        timeline = observation("timeline", 0.5, 0.5, (0.1, 0.2, 0.3, 0.4))
        viral = observation("viral", 0.5, 0.5, (0.1, 0.2, 0.3, 0.4))
        self.assertEqual(timeline.shape, (1, INPUTS))
        self.assertEqual(len(SENSE_NAMES), INPUTS)
        self.assertEqual(float(timeline[0, 0]), 1.0)
        self.assertEqual(float(timeline[0, 1]), 0.0)
        self.assertEqual(float(viral[0, 0]), 0.0)
        self.assertEqual(float(viral[0, 1]), 1.0)
        # The verb that pays is not written into the vector.
        self.assertNotIn(float(ACTIONS.index("reply")), set(np.round(timeline[0], 5)))

    def test_nursery_stays_in_range(self) -> None:
        for moment in range(60):
            row = nursery_observation(moment)[0]
            self.assertEqual(float(row[0]), 1.0)
            self.assertGreaterEqual(float(row[2]), 0.45)
            self.assertLessEqual(float(row[2]), 0.85)
            self.assertGreaterEqual(float(row[3]), 0.35)
            self.assertLessEqual(float(row[3]), 0.75)

    def test_clout_sense_stays_in_the_nursery_band(self) -> None:
        for score in (-40, -8, 0, 8, 40):
            sense = pit_clout_sense(score)
            self.assertGreaterEqual(sense, 0.35)
            self.assertLessEqual(sense, 0.75)

    def test_crowd_is_a_share(self) -> None:
        crowd = crowd_from_actions([2, 2, 2, 3, 0, 1])
        self.assertAlmostEqual(float(crowd.sum()), 1.0)
        self.assertAlmostEqual(float(crowd[2]), 0.5)


if __name__ == "__main__":
    unittest.main()
