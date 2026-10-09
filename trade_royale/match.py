"""Raise six brains on gm, then run the pit. Same lives, nothing reset between rounds."""

from __future__ import annotations

from collections import Counter
from typing import Callable

import numpy as np

from .brain import GENES, Life
from .creatures import CREATURES, LINES
from .live_feed import (
    STAKE,
    StaticFeed,
    mark_bag,
    liquid_opening,
    open_bag,
    quiet_list,
    revise_list,
    starting_list,
    trade_bag,
)
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
        self.traces = {c["id"]: {"rate": [], "twin": [], "learn": []} for c in self.creatures}
        self.prices: list[float] = []
        self.bags: dict[str, dict] = {}
        self.twin_bags: dict[str, dict] = {}
        self.random_bags: dict[str, dict] = {}
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
        self._brain_reward = [0.0 for _ in self.creatures]
        self._random_actions = [0 for _ in self.creatures]
        self._seen: dict[str, list[float]] = {}
        self.pool: list[dict] = []
        self.lists: dict[str, list[int]] = {}
        self.twin_lists: dict[str, list[int]] = {}
        self.random_lists: dict[str, list[int]] = {}
        self._swap: dict[str, tuple[int, int] | None] = {}
        self._list_action: dict[str, str] = {}

    def raise_all(self, on_progress: Progress | None = None) -> None:
        self.phase = "reading"
        self.progress = {**self.progress, "phase": "reading", "name": "the pool"}
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
        self._bind_pool()
        self.events.append("Live. Each trader plays their own style.")
        self.progress = {**self.progress, "phase": "live"}

    def _bind_pool(self) -> None:
        mark_open = getattr(self.feed_source, "mark_open", None)
        if mark_open:
            mark_open()
        board = self._feed_coins()
        self.pool = sorted(
            board,
            key=lambda item: float(item.get("day") if item.get("day") is not None else item.get("growth") or 0.0),
            reverse=True,
        )
        quiet = quiet_list(len(self.pool))
        liquid = any(float(item.get("post_count") or 0) > 0 for item in self.pool)
        self.lists = {}
        self.twin_lists = {}
        for index, creature in enumerate(self.creatures):
            opening = (
                liquid_opening(self.pool, index)
                if liquid
                else starting_list(len(self.pool), index)
            )
            self.lists[creature["id"]] = list(opening)
            self.twin_lists[creature["id"]] = list(opening)
        self.random_lists = {c["id"]: list(quiet) for c in self.creatures}
        self.prices = [1.0 for _ in self.pool]
        self._price_steps = 0
        self.bags = {c["id"]: open_bag(self.lists[c["id"]], self.prices) for c in self.creatures}
        self.twin_bags = {c["id"]: open_bag(self.twin_lists[c["id"]], self.prices) for c in self.creatures}
        self.random_bags = {c["id"]: open_bag(self.random_lists[c["id"]], self.prices) for c in self.creatures}
        self._swap = {c["id"]: None for c in self.creatures}
        self._list_action = {c["id"]: "reply" for c in self.creatures}

    def _apply_prices(self) -> None:
        """Mark each coin from the live quote. The offline stand-in still walks its printed move."""
        if len(self.prices) != len(self.pool):
            self.prices = [1.0 for _ in self.pool]
        quote_fn = getattr(self.feed_source, "quotes", None)
        fresh = quote_fn() if quote_fn else None
        if fresh is None:
            fresh = {
                str(item.get("symbol") or item.get("title")): float(item.get("last") or 0.0)
                for item in self._feed_coins()
            }
        quoted = False
        for index, item in enumerate(self.pool):
            key = str(item.get("symbol") or item.get("title"))
            last = float(fresh.get(key) or item.get("last") or 0.0)
            open_px = float(item.get("open") or 0.0)
            if open_px > 0 and last > 0:
                item["last"] = last
                item["growth"] = round((last / open_px - 1.0) * 100.0, 2)
                self.prices[index] = last / open_px
                quoted = True
        if quoted:
            return
        self._price_steps = getattr(self, "_price_steps", 0) + 1
        if self._price_steps > 400:
            return
        for index, item in enumerate(self.pool):
            change = float(item.get("growth") or 0.0) / 100.0
            self.prices[index] *= 1.0 + change / 400.0

    def _feed_coins(self) -> list[dict]:
        book = getattr(self.feed_source, "book", None)
        if book:
            return list(book())
        return list(self.feed_source.public().get("board") or [])

    def _coin(self, index: int) -> str:
        title = str(self.pool[index].get("title") or "coin")
        return title.split(" ", 1)[0]

    def _bag_view(self, creature_id: str) -> list[dict]:
        bag = self.bags.get(creature_id) or {}
        rows = []
        for index, lot in (bag.get("lots") or {}).items():
            if not (0 <= index < len(self.pool) and index < len(self.prices)):
                continue
            value = float(lot["coins"]) * self.prices[index]
            rows.append({
                "title": self._coin(index),
                "value": round(value, 1),
                "gain": round(value - float(lot["cost"]), 1),
            })
        rows.sort(key=lambda row: row["gain"], reverse=True)
        return rows

    def _held_rate(self, held: list[int]) -> float:
        return round(
            sum(float(self.pool[i].get("growth") or 0) for i in held if 0 <= i < len(self.pool)),
            1,
        )

    def _note_trace(self, name: str, rate: float, twin: float, learning: bool) -> None:
        trace = self.traces.setdefault(name, {"rate": [], "twin": [], "learn": []})
        trace["rate"].append(rate)
        trace["twin"].append(twin)
        trace["learn"].append(1 if learning else 0)
        if len(trace["rate"]) > 2400:
            for key in trace:
                del trace[key][:-2400]

    def _list_view(self, held: list[int]) -> list[dict]:
        rows = []
        for index in held:
            if not (0 <= index < len(self.pool)):
                continue
            item = self.pool[index]
            rows.append({
                "title": item.get("title") or "trend",
                "growth": round(float(item.get("growth") or 0.0), 1),
                "hot": float(item.get("growth") or 0.0) > 0,
            })
        return rows

    def _change_text(self, creature_id: str) -> str:
        swap = self._swap.get(creature_id)
        if swap and self.pool:
            left, right = swap
            if 0 <= left < len(self.pool) and 0 <= right < len(self.pool):
                return f"Sold {self._coin(left)} · Bought {self._coin(right)}"
        if self._list_action.get(creature_id) in ("post", "lurk"):
            return "No coin worth a trade."
        return "Held the bag."

    def _title(self, regime: str) -> str:
        slices = self.feed_source.public().get("slices") or {}
        return str((slices.get(regime) or {}).get("title") or regime)

    def flip(self) -> str:
        self.regime = VIRAL if self.regime == TIMELINE else TIMELINE
        self.flipped_at = self.moment
        self.since = {c["id"]: Counter() for c in self.creatures}
        verb = self.winners[self.regime]
        self.events.append(
            f"New tape: {self._title(self.regime)}. The move is what pays."
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
        self.traces = {c["id"]: {"rate": [], "twin": [], "learn": []} for c in self.creatures}
        self.since = {c["id"]: Counter() for c in self.creatures}
        self._bind_pool()
        self.events.append(
            "New round. Bags reset. The traders keep what they learned."
        )
        self.events = self.events[-8:]

    def step(self) -> None:
        if self.phase != "live" or not self.lives:
            return
        if not any(item.get("symbol") for item in self.pool):
            fresh = self._feed_coins()
            if any(item.get("symbol") for item in fresh):
                self._bind_pool()
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
            reward = life.hanging if life.hanging is not None else self._brain_reward[index]
            life.hanging = None
            self._seen[creature["id"]] = [round(float(value), 2) for value in obs[0]]
            chosen.append(life.act(obs, reward))
            twin_chosen.append(twin.decide(obs))
            random_chosen.append(int(self.rng.integers(0, len(ACTIONS))))
        acted = crowd_from_actions(chosen)
        live_hits = 0
        frozen_hits = 0
        random_hits = 0
        self._apply_prices()
        self.totals = {"live": 0.0, "frozen": 0.0, "random": 0.0}
        for index, creature in enumerate(self.creatures):
            name = creature["id"]
            self._brain_reward[index] = payoff(
                chosen[index], regime, float(acted[chosen[index]]), self.winners
            )
            updated, swap = revise_list(
                self.pool,
                self.lists.get(name, []),
                ACTIONS[chosen[index]],
                str(creature.get("style") or "hottest"),
            )
            self.lists[name] = updated
            self._swap[name] = swap
            self._list_action[name] = ACTIONS[chosen[index]]
            wandered, _wander_swap = revise_list(
                self.pool,
                self.random_lists.get(name, []),
                ACTIONS[random_chosen[index]],
            )
            self.random_lists[name] = wandered
            trade_bag(self.bags[name], *(swap if swap else (None, None)), self.prices)
            trade_bag(self.random_bags[name], *(_wander_swap if _wander_swap else (None, None)), self.prices)
            pnl = mark_bag(self.bags[name], self.prices) - STAKE
            twin_pnl = mark_bag(self.twin_bags[name], self.prices) - STAKE
            random_pnl = mark_bag(self.random_bags[name], self.prices) - STAKE
            self._note_trace(name, pnl, twin_pnl, self.lives[index].mode == "aroused")
            self._prev_payoff[index] = pnl
            self.scores[name] = pnl
            self.totals["live"] += pnl
            self.totals["frozen"] += twin_pnl
            self.totals["random"] += random_pnl
            live_hits += int(chosen[index] == best)
            frozen_hits += int(twin_chosen[index] == best)
            random_hits += int(random_chosen[index] == best)
            self.since[creature["id"]][ACTIONS[chosen[index]]] += 1
            self._push_line(creature, index, chosen[index], pnl, regime)
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
        growing = self.winners.get(VIRAL, "")
        for index, creature in enumerate(self.creatures):
            ready = index < len(self.lives)
            life = self.lives[index] if ready else None
            twin = self.twins[index] if index < len(self.twins) else None
            mix = self.since[creature["id"]]
            total_mix = sum(mix.values()) or 1
            verb = ACTIONS[life.last_action] if life else "lurk"
            held = self.lists.get(creature["id"], [])
            creatures.append({
                "id": creature["id"],
                "name": creature["name"],
                "taste": creature.get("taste") or "",
                "style": creature.get("style") or "",
                "seed": creature.get("seed"),
                "handle": creature["handle"],
                "mark": creature["mark"],
                "color": creature["color"],
                "ink": creature["ink"],
                "ready": ready,
                "score": round(self.scores[creature["id"]], 2),
                "bag": self._bag_view(creature["id"]),
                "twin_pnl": round(mark_bag(self.twin_bags.get(creature["id"], {}), self.prices) - STAKE, 2) if self.prices else 0.0,
                "still": [
                    self._coin(index)
                    for index in self.twin_lists.get(creature["id"], [])
                    if 0 <= index < len(self.pool)
                ],
                "last_pay": round(self._prev_payoff[index], 2),
                "verb": verb,
                "list": self._list_view(held),
                "list_rate": self._held_rate(held),
                "twin_rate": self._held_rate(self.twin_lists.get(creature["id"], [])),
                "change": self._change_text(creature["id"]),
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
            "traces": {
                name: {
                    "rate": _spark(trace["rate"]),
                    "twin": _spark(trace["twin"]),
                }
                for name, trace in self.traces.items()
            },
            "totals": {k: round(v, 2) for k, v in self.totals.items()},
            "events": list(self.events),
            "senses": list(SENSE_NAMES),
            "actions": list(ACTIONS),
            "setup": {
                "modules": int(GENES["modules"][0]),
                "learn": GENES["actor_eta"],
                "memory": GENES["working_memory_amplitude"],
                "consolidation": GENES["consolidation"],
                "temperature": GENES["temperature"],
                "surprise": GENES["arousal"]["threshold"],
            },
        }


def _spark(values: list[float], buckets: int = 160) -> list[float]:
    """Keep the whole round visible, from the first swaps to now."""
    if len(values) <= buckets:
        return list(values)
    span = len(values) / buckets
    points = []
    for index in range(buckets):
        start = int(index * span)
        end = max(start + 1, int((index + 1) * span))
        chunk = values[start:end]
        points.append(round(sum(chunk) / len(chunk), 2))
    return points


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
