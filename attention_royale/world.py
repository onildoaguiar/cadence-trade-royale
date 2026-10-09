"""The feed as a world: senses in, a verb out, a payoff back.

Off-meta pays −1 and the meta pays +1. Crowding only softens that.
The regime is a glow in the observation. Nothing in the vector says which verb pays.
"""

from __future__ import annotations

import numpy as np

ACTIONS: tuple[str, ...] = ("lurk", "post", "reply", "raid")
TIMELINE = "timeline"
VIRAL = "viral"
# Offline stand-in, measured on public Bluesky posts: recent posts pay reply,
# the posts that blow up pay an original post. A live fetch can replace this.
BEST: dict[str, str] = {TIMELINE: "reply", VIRAL: "post"}
SENSE_NAMES: tuple[str, ...] = (
    "timeline glow",
    "viral glow",
    "attention left",
    "own clout",
    "crowd lurking",
    "crowd posting",
    "crowd replying",
    "crowd raiding",
)
NURSERY_CROWD: tuple[float, ...] = (0.22, 0.18, 0.28, 0.16)
INPUTS = len(SENSE_NAMES)


def action_index(name: str) -> int:
    return ACTIONS.index(name)


def crowd_from_actions(actions: list[int]) -> np.ndarray:
    counts = np.zeros(len(ACTIONS), dtype=np.float64)
    if not actions:
        counts[:] = 1.0 / len(ACTIONS)
        return counts
    for action in actions:
        counts[int(action)] += 1.0
    counts /= len(actions)
    return counts


def payoff(
    action: int,
    regime: str,
    crowd_fraction: float,
    winners: dict[str, str] | None = None,
) -> float:
    """Sign follows whichever verb the live slice actually pays."""
    table = winners or BEST
    base = 1.0 if ACTIONS[int(action)] == table[regime] else -1.0
    scale = 1.0 - 0.25 * float(np.clip(crowd_fraction, 0.0, 1.0))
    return float(base * scale)


def observation(
    regime: str,
    attention: float,
    clout: float,
    crowd: np.ndarray | tuple[float, ...],
) -> np.ndarray:
    glow = 0.0 if regime == VIRAL else 1.0
    row = [
        glow,
        1.0 - glow,
        float(np.clip(attention, 0.0, 1.0)),
        float(np.clip(clout, 0.0, 1.0)),
        *[float(np.clip(value, 0.0, 1.0)) for value in crowd],
    ]
    if len(row) != INPUTS:
        raise ValueError(f"observation has {len(row)} senses, expected {INPUTS}")
    return np.asarray([row], dtype=np.float64)


def nursery_observation(moment: int) -> np.ndarray:
    """The timeline glow, with the same drift the pit will show."""
    attention = 0.45 + 0.40 * ((moment % 25) / 25.0)
    clout = 0.35 + 0.40 * ((moment % 13) / 13.0)
    return observation(TIMELINE, attention, clout, NURSERY_CROWD)


def pit_attention(moment: int) -> float:
    """Stays inside the range the nursery already showed the brain."""
    cycle = (moment % 25) / 25.0
    return 0.45 + 0.40 * cycle


def pit_clout_sense(score: float) -> float:
    """Squash the public score into the clout band the nursery used."""
    return float(0.55 + 0.20 * np.tanh(score / 12.0))


def void_close(moment: int, horizon: int = 420) -> float:
    """How far the void has eaten, from 0 (open feed) to 1 (tight)."""
    if horizon <= 0:
        return 1.0
    return float(np.clip(moment / horizon, 0.0, 1.0))
