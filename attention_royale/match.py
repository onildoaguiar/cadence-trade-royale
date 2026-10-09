"""Raise six brains on gm, then run the pit. Same lives, nothing reset between rounds."""

from __future__ import annotations

from collections import Counter
from typing import Callable

import numpy as np

from .brain import Life
from .creatures import CREATURES, LINES
from .live_feed import StaticFeed
from .world import (
    ACTIONS,
    BEST,
    NURSERY_CROWD,
    SENSE_NAMES,
    TIMELINE,
    VIRAL,
    action_index,
    crowd_from_actions,
    nursery_observation,
    observation,
    payoff,
    pit_attention,
    pit_clout_sense,
    void_close,
)

# The pit's raw crowd can be a one-hot the nursery never showed. Keep the sense
# near the nursery vector; the payoff still uses the real share.
_CROWD_ANCHOR = np.asarray(NURSERY_CROWD, dtype=np.float64)

Progress = Callable[[dict], None]


class League:
    def __init__(
        self,
        creatures: tuple[dict, ...] | list[dict] = CREATURES,
        nursery_moments: int = 360,
        seed: int = 7,
        feed: StaticFeed | None = None,
    ) -> None:
        self.creatures = list(creatures)
        self.nursery_moments = int(nursery_moments)
        self.rng = np.random.default_rng(seed)
        self.feed_source = feed or StaticFeed()
        self.winners = dict(BEST)
        self.phase = "nursery"
        self.regime = TIMELINE
        self.moment = 0
        self.lives: list[Life] = []
        self.twins: list = []
        self.scores = {c["id"]: 0.0 for c in self.creatures}
        self.totals = {"live": 0.0, "frozen": 0.0, "random": 0.0}
        self.feed: list[dict] = []
        self.history: list[dict] = []
        self.events: list[str] = []
        self.line_cursor = {c["id"]: 0 for c in self.creatures}
        self._last_line: dict[str, tuple[str, str]] = {}
        self.since: dict[str, Counter] = {c["id"]: Counter() for c in self.creatures}
        self.flipped_at: int | None = None
        self.progress: dict = {
            "phase": "nursery",
            "index": 0,
            "count": len(self.creatures),
            "moment": 0,
            "moments": self.nursery_moments,
            "name": self.creatures[0]["name"] if self.creatures else "",
            "reply_rate": 0.0,
            "raised": [],
        }
        self._prev_payoff = [0.0 for _ in self.creatures]
        self._random_actions = [0 for _ in self.creatures]
        self._seen: dict[str, list[float]] = {}

    def raise_all(self, on_progress: Progress | None = None) -> None:
        self.phase = "reading"
        self.progress = {**self.progress, "phase": "reading", "name": "the live feed"}
        if on_progress:
            on_progress(self.progress)
        self.feed_source.load()
        self.winners = dict(self.feed_source.winners())
        self.phase = "nursery"
        target = action_index(self.winners[TIMELINE])
        verb = self.winners[TIMELINE]
        raised: list[dict] = []
        for index, creature in enumerate(self.creatures):
            life = Life(int(creature["seed"]))
            reward: float | None = None
            hits: list[int] = []
            for moment in range(self.nursery_moments):
                action = life.act(nursery_observation(moment), reward)
                crowd = float(np.asarray([0.22, 0.18, 0.28, 0.16])[action])
                reward = payoff(action, TIMELINE, crowd, self.winners)
                hits.append(int(action == target))
                if on_progress and moment % 15 == 0:
                    rate = float(np.mean(hits[-40:])) if hits else 0.0
                    self.progress = {
                        "phase": "nursery",
                        "index": index,
                        "count": len(self.creatures),
                        "moment": moment,
                        "moments": self.nursery_moments,
                        "name": creature["name"],
                        "reply_rate": round(rate, 3),
                        "verb": verb,
                        "raised": list(raised),
                    }
                    on_progress(self.progress)
            life.hanging = float(reward if reward is not None else 0.0)
            rate = float(np.mean(hits[-40:])) if hits else 0.0
            twin = life.snapshot_twin()
            self.lives.append(life)
            self.twins.append(twin)
            raised.append({
                "id": creature["id"],
                "name": creature["name"],
                "reply_rate": round(rate, 3),
                "verb": verb,
                "refusals": life.refusals,
            })
            self.progress = {
                "phase": "nursery",
                "index": index,
                "count": len(self.creatures),
                "moment": self.nursery_moments,
                "moments": self.nursery_moments,
                "name": creature["name"],
                "reply_rate": round(rate, 3),
                "verb": verb,
                "raised": list(raised),
            }
            if on_progress:
                on_progress(self.progress)
        self.phase = "live"
        self.regime = VIRAL
        self.events.append(
            f"Ranking is open. The first lesson was {self._title(TIMELINE)}. "
            f"{self._title(VIRAL)} is gaining posts fastest, so only that trend adds points."
        )
        self.progress = {**self.progress, "phase": "live"}

    def _title(self, regime: str) -> str:
        slices = self.feed_source.public().get("slices") or {}
        return str((slices.get(regime) or {}).get("title") or regime)

    def flip(self) -> str:
        self.regime = VIRAL if self.regime == TIMELINE else TIMELINE
        self.flipped_at = self.moment
        self.since = {c["id"]: Counter() for c in self.creatures}
        verb = self.winners[self.regime]
        self.events.append(
            f"Now scoring {self._title(self.regime)}. Sitting there is what adds points."
        )
        self.events = self.events[-8:]
        return verb

    def new_round(self) -> None:
        self.regime = VIRAL
        self.moment = 0
        self.flipped_at = None
        self.scores = {c["id"]: 0.0 for c in self.creatures}
        self.totals = {"live": 0.0, "frozen": 0.0, "random": 0.0}
        self.feed.clear()
        self.history.clear()
        self.since = {c["id"]: Counter() for c in self.creatures}
        self.events.append(
            f"Scores cleared. The brains kept what they learned. {self._title(VIRAL)} still adds the points."
        )
        self.events = self.events[-8:]

    def step(self) -> None:
        if self.phase != "live" or not self.lives:
            return
        regime = self.regime
        best = action_index(self.winners[regime])
        raw_seen = crowd_from_actions([life.last_action for life in self.lives])
        seen = 0.35 * raw_seen + 0.65 * _CROWD_ANCHOR
        attention = pit_attention(self.moment)
        chosen: list[int] = []
        twin_chosen: list[int] = []
        random_chosen: list[int] = []
        for index, (life, twin, creature) in enumerate(zip(self.lives, self.twins, self.creatures)):
            obs = observation(
                regime,
                attention,
                pit_clout_sense(self.scores[creature["id"]]),
                seen,
            )
            reward = life.hanging if life.hanging is not None else self._prev_payoff[index]
            life.hanging = None
            self._seen[creature["id"]] = [round(float(value), 2) for value in obs[0]]
            chosen.append(life.act(obs, reward))
            twin_chosen.append(twin.decide(obs))
            random_chosen.append(int(self.rng.integers(0, len(ACTIONS))))
        acted = crowd_from_actions(chosen)
        live_hits = 0
        frozen_hits = 0
        random_hits = 0
        for index, creature in enumerate(self.creatures):
            live_pay = payoff(chosen[index], regime, float(acted[chosen[index]]), self.winners)
            frozen_pay = payoff(twin_chosen[index], regime, float(acted[twin_chosen[index]]), self.winners)
            random_pay = payoff(random_chosen[index], regime, float(acted[random_chosen[index]]), self.winners)
            self._prev_payoff[index] = live_pay
            self.scores[creature["id"]] += live_pay
            self.totals["live"] += live_pay
            self.totals["frozen"] += frozen_pay
            self.totals["random"] += random_pay
            live_hits += int(chosen[index] == best)
            frozen_hits += int(twin_chosen[index] == best)
            random_hits += int(random_chosen[index] == best)
            self.since[creature["id"]][ACTIONS[chosen[index]]] += 1
            self._push_line(creature, index, chosen[index], live_pay, regime)
        n = len(self.creatures)
        self.history.append({
            "regime": regime,
            "live": round(live_hits / n, 3),
            "frozen": round(frozen_hits / n, 3),
            "random": round(random_hits / n, 3),
        })
        if len(self.history) > 600:
            self.history = self.history[-600:]
        self._random_actions = random_chosen
        self.moment += 1

    def _push_line(self, creature: dict, index: int, action: int, pay: float, regime: str) -> None:
        verb = ACTIONS[action]
        signature = (regime, verb)
        if self._last_line.get(creature["id"]) == signature and self.moment % 6 != index % 6:
            return
        self._last_line[creature["id"]] = signature
        real = self.feed_source.example(regime, verb)
        if real is None:
            cursor = self.line_cursor[creature["id"]]
            bank = (LINES.get(regime) or LINES[TIMELINE])[verb]
            text = bank[cursor % len(bank)]
            self.line_cursor[creature["id"]] = cursor + 1
        else:
            text = real["text"]
        self.feed.append({
            "id": creature["id"],
            "handle": creature["handle"],
            "color": creature["color"],
            "verb": verb,
            "text": text,
            "pay": round(pay, 2),
            "moment": self.moment,
            "live_handle": None if real is None else real["handle"],
            "likes": None if real is None else real["likes"],
            "url": None if real is None else real["url"],
        })
        if len(self.feed) > 16:
            del self.feed[: len(self.feed) - 16]

    def snapshot(self) -> dict:
        close = void_close(self.moment)
        creatures = []
        raised = {row["id"]: row for row in self.progress.get("raised", [])}
        board = {
            str(item.get("slot")): item
            for item in (self.feed_source.public().get("board") or [])
        }
        growing = self.winners.get(VIRAL, "")
        for index, creature in enumerate(self.creatures):
            ready = index < len(self.lives)
            life = self.lives[index] if ready else None
            twin = self.twins[index] if index < len(self.twins) else None
            mix = self.since[creature["id"]]
            total_mix = sum(mix.values()) or 1
            verb = ACTIONS[life.last_action] if life else "lurk"
            trend = board.get(verb) or {}
            creatures.append({
                "id": creature["id"],
                "name": creature["name"],
                "handle": creature["handle"],
                "mark": creature["mark"],
                "color": creature["color"],
                "ink": creature["ink"],
                "ready": ready,
                "score": round(self.scores[creature["id"]], 2),
                "last_pay": round(self._prev_payoff[index], 2),
                "verb": verb,
                "trend": trend.get("title") or verb,
                "on_growing": verb == growing,
                "twin": ACTIONS[twin.last_action] if twin else "lurk",
                "mode": life.mode if life else "raising",
                "learned": bool(life.learned) if life else False,
                "want": round(life.want, 3) if life else 0.0,
                "level": round(life.level, 3) if life else 0.0,
                "sweeps": life.sweeps if life else 0,
                "refusals": life.refusals if life else 0,
                "calm": _calm(life),
                "nursery_reply": raised.get(creature["id"], {}).get("reply_rate"),
                "mix": {name: round(mix[name] / total_mix, 3) for name in ACTIONS},
                "senses": self._seen.get(creature["id"]),
                "activity": _activity(life),
            })
        ranking = sorted(creatures, key=lambda row: row["score"], reverse=True)
        for place, row in enumerate(ranking, start=1):
            row["rank"] = place
        return {
            "phase": self.phase,
            "regime": self.regime,
            "meta": self.winners[self.regime],
            "source": self.feed_source.public(),
            "moment": self.moment,
            "close": round(close, 4),
            "flipped_at": self.flipped_at,
            "progress": self.progress,
            "creatures": creatures,
            "ranking": ranking,
            "feed": list(self.feed),
            "history": list(self.history[-360:]),
            "totals": {k: round(v, 2) for k, v in self.totals.items()},
            "events": list(self.events),
            "senses": list(SENSE_NAMES),
            "actions": list(ACTIONS),
        }


def _calm(life: Life | None) -> float | None:
    if life is None:
        return None
    seen = life.routine + life.aroused_moments
    if seen == 0:
        return None
    return round(life.routine / seen, 3)


def _activity(life: Life | None) -> dict | None:
    if life is None:
        return None
    from .brain import read_activity

    return read_activity(life.brain)
