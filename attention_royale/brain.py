"""One continuing Cadence life, and a frozen twin that stopped at the nursery door."""

from __future__ import annotations

import os
import tempfile
from typing import Any

import numpy as np
from cadence import Brain

# Measured on this feed: modules (24,), temperature 0.8, actor eta 0.15, youth 100.
# Nursery on gm reaches reply. After the payoff flips, repair shows up around moment 180–220.
# Do not retune arousal off at the door — surprise is what wakes the repair.
GENES: dict[str, Any] = {
    "modules": (24,),
    "working_memory_amplitude": 0.3,
    "consolidation": 0.25,
    "sensory_scale": 4.0,
    "temperature": 0.8,
    "actor_eta": 0.15,
    "actor_eta_bias": 0.015,
    "arousal": {
        "threshold": 0.2,
        "decay": 0.92,
        "youth": 100,
        "need": 0.0,
        "value_surprise": 1.0,
        "heat": 2.0,
        "floor": 0.05,
        "fast": 0.05,
        "slow": 0.005,
        "tolerance": 2.0,
    },
}


def compose(seed: int) -> Brain:
    genes = GENES
    return Brain.compose(
        8,
        4,
        modules=tuple(genes["modules"]),
        seed=int(seed),
        working_memory_amplitude=float(genes["working_memory_amplitude"]),
        consolidation=float(genes["consolidation"]),
        sensory_scale=float(genes["sensory_scale"]),
        temperature=float(genes["temperature"]),
        actor_eta=float(genes["actor_eta"]),
        actor_eta_bias=float(genes["actor_eta_bias"]),
        arousal=dict(genes["arousal"]),
    )


def clone_brain(brain: Brain) -> Brain:
    fd, name = tempfile.mkstemp(suffix=".npz")
    os.close(fd)
    try:
        brain.save(name)
        return Brain.load(name)
    finally:
        os.remove(name)


def _index(action: Any) -> int:
    value = int(np.atleast_1d(np.asarray(action)).reshape(-1)[0])
    return int(np.clip(value, 0, 3))


def read_activity(brain: Brain) -> dict[str, list[float]] | None:
    try:
        state = brain.basal_ganglia.state
        if state is None:
            return None
        act = np.asarray(state.activation)[0]

        def take(index: Any, limit: int) -> list[float]:
            return [round(float(act[int(i)]), 2) for i in list(index)[:limit]]

        return {
            "sensory": take(brain.sensory_index, 8),
            "association": take(brain.association_index, 24),
            "motor": take(brain.motor_index, 4),
        }
    except Exception:
        return None


class Life:
    """`Brain.live` for one account. The reward argument is the previous verb's payoff."""

    def __init__(self, seed: int, brain: Brain | None = None) -> None:
        self.brain = compose(seed) if brain is None else brain
        self.started = False
        self.last_action = 0
        self.hanging: float | None = None
        self.refusals = 0
        self.routine = 0
        self.aroused_moments = 0
        self.mode = "routine"
        self.want = 0.0
        self.level = 0.0
        self.learned = False
        self.sweeps = 0

    def act(self, observation: np.ndarray, reward: float | None, done: bool = False) -> int:
        kwargs: dict[str, Any] = {}
        if self.started:
            kwargs["reward"] = [0.0 if reward is None else float(reward)]
            kwargs["done"] = [bool(done)]
        try:
            out = self.brain.live(observation, **kwargs)
        except (RuntimeError, ValueError):
            self.refusals += 1
            pending = bool(getattr(self.brain, "pending_feedback", True))
            if kwargs and not pending:
                try:
                    out = self.brain.live(observation)
                except (RuntimeError, ValueError):
                    self._read()
                    return self.last_action
            else:
                self._read()
                return self.last_action
        self.started = True
        self.last_action = _index(out)
        self._read()
        return self.last_action

    def _read(self) -> None:
        reading = self.brain.last_arousal or {}
        arousal = self.brain.arousal
        mode = str(reading.get("mode") or (arousal.mode if arousal is not None else "routine"))
        self.mode = mode
        self.learned = bool(reading.get("learned", False))
        self.sweeps = int(reading.get("sweeps", 0))
        if arousal is not None:
            self.want = float(arousal.want)
            self.level = float(arousal.level)
        if mode == "aroused":
            self.aroused_moments += 1
        else:
            self.routine += 1

    def snapshot_twin(self) -> Twin:
        return Twin(clone_brain(self.brain))


class Twin:
    """Greedy `act` on a nursery copy. It watches the new feed and does not learn."""

    def __init__(self, brain: Brain) -> None:
        self.brain = brain
        self.last_action = 0
        self.refusals = 0

    def decide(self, observation: np.ndarray) -> int:
        try:
            out = self.brain.act(observation, greedy=True)
        except (RuntimeError, ValueError):
            self.refusals += 1
            return self.last_action
        self.last_action = _index(out)
        return self.last_action
