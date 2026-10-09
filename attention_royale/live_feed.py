"""Read-only public posts from Bluesky's live trends.

Each trend is a feed Bluesky is already grouping. Two trends become the two
slices. Nothing here posts, likes, or follows.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .world import ACTIONS, BEST, TIMELINE, VIRAL

APPVIEW = "https://api.bsky.app/xrpc"
MIN_COUNT = 6
TREND_LIMIT = 8


def kind_of(post: dict[str, Any]) -> str:
    record = post.get("record") or {}
    if record.get("reply"):
        return "reply"
    embed = post.get("embed") or {}
    if "embed.record" in str(embed.get("$type") or ""):
        return "raid"
    return "post"


def engagement(post: dict[str, Any]) -> int:
    return (
        int(post.get("likeCount") or 0)
        + 2 * int(post.get("repostCount") or 0)
        + int(post.get("replyCount") or 0)
    )


def _trimmed_log_mean(values: list[int]) -> float:
    ordered = sorted(values)
    cut = max(0, len(ordered) // 10)
    core = ordered[cut : len(ordered) - cut or None]
    return sum(math.log1p(value) for value in core) / len(core)


def rank(posts: list[dict[str, Any]]) -> tuple[str, dict[str, dict[str, float]]]:
    """The verb with the higher typical engagement, ignoring classes with too few posts."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for post in posts:
        buckets[kind_of(post)].append(engagement(post))
    scores: dict[str, float] = {}
    stats: dict[str, dict[str, float]] = {}
    for name in ("post", "reply", "raid"):
        values = buckets.get(name) or []
        if not values:
            continue
        ordered = sorted(values)
        stats[name] = {
            "n": float(len(values)),
            "mean": round(sum(values) / len(values), 2),
            "median": float(ordered[len(ordered) // 2]),
        }
        if len(values) >= MIN_COUNT:
            scores[name] = _trimmed_log_mean(values)
    winner = max(scores, key=scores.get) if scores else BEST[TIMELINE]
    return winner, stats


def _public_post(post: dict[str, Any]) -> dict[str, Any]:
    record = post.get("record") or {}
    handle = str((post.get("author") or {}).get("handle") or "")
    uri = str(post.get("uri") or "")
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    text = " ".join(str(record.get("text") or "").split())
    if len(text) > 160:
        text = text[:157] + "..."
    url = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else ""
    return {
        "handle": f"@{handle}" if handle else "@",
        "text": text or "(no text)",
        "kind": kind_of(post),
        "likes": int(post.get("likeCount") or 0),
        "engagement": engagement(post),
        "url": url,
    }


def _get(method: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"{APPVIEW}/{method}?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "cadence-trending-royale"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def feed_uri(link: str) -> str | None:
    """Turn a trend link into the feed address `getFeed` accepts."""
    path = urllib.parse.urlparse(link).path if "://" in link else link
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 4 and parts[0] == "profile" and parts[2] == "feed":
        return f"at://{parts[1]}/app.bsky.feed.generator/{parts[3]}"
    return None


def growth_per_hour(trend: dict[str, Any], now: datetime | None = None) -> float:
    """Posts per hour since the trend started. Cooling trends count for less."""
    clock = now or datetime.now(timezone.utc)
    raw = str(trend.get("startedAt") or "")
    try:
        started = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        started = clock - timedelta(hours=6)
    hours = max((clock - started).total_seconds() / 3600.0, 0.25)
    rate = int(trend.get("postCount") or 0) / hours
    status = trend.get("status") or ""
    if status == "cooling":
        rate *= 0.7
    elif status == "trending":
        rate *= 1.15
    return round(rate, 1)


def assign_slots(scored: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fastest growth sits on post, the one the pit pays. Slowest sits on reply, the nursery habit."""
    ordered = sorted(scored, key=lambda item: float(item.get("growth") or 0.0), reverse=True)
    if not ordered:
        return {}
    while len(ordered) < 4:
        pad = dict(ordered[-1])
        pad["title"] = f"{pad.get('title') or 'trend'} · quiet"
        pad["growth"] = round(float(pad.get("growth") or 0.0) * 0.5, 1)
        ordered.append(pad)
    names = ("post", "lurk", "raid", "reply")
    return {name: trend for name, trend in zip(names, ordered[:4])}


def choose_pair(scored: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Two live trends. Prefer a pair whose paying verb differs, trending ones first."""
    if not scored:
        return None
    ordered = sorted(scored, key=lambda item: 0 if item.get("status") == "trending" else 1)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if left.get("winner") != right.get("winner"):
                return left, right
    if len(ordered) == 1:
        return ordered[0], ordered[0]
    return ordered[0], ordered[1]


def _trend_posts(uri: str) -> list[dict[str, Any]]:
    payload = _get("app.bsky.feed.getFeed", {"feed": uri, "limit": "50"})
    posts = []
    for item in payload.get("feed") or []:
        post = item.get("post") if isinstance(item, dict) else None
        if post:
            posts.append(post)
    return posts


class StaticFeed:
    """The measured stand-in used when there is no network: timeline pays reply, viral pays post."""

    source = "offline"

    def __init__(self, winners: dict[str, str] | None = None) -> None:
        self._winners = dict(winners or BEST)
        self.error: str | None = None
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def winners(self) -> dict[str, str]:
        return dict(self._winners)

    def example(self, regime: str, verb: str) -> dict[str, Any] | None:
        return None

    def public(self) -> dict[str, Any]:
        return {
            "name": "offline stand-in",
            "note": "No live trends loaded. The growing tag pays.",
            "error": self.error,
            "board": _stand_in_board(),
            "slices": {
                regime: {
                    "winner": verb,
                    "query": "",
                    "title": "the quiet tag" if regime == TIMELINE else "the growing tag",
                    "stats": {},
                }
                for regime, verb in self._winners.items()
            },
        }


def _stand_in_board() -> list[dict[str, Any]]:
    rows = (
        ("post", "the growing tag", 48.0, True),
        ("lurk", "a busy tag", 18.0, False),
        ("raid", "a cooling tag", 9.0, False),
        ("reply", "the quiet tag", 3.0, False),
    )
    return [
        {
            "slot": slot,
            "title": title,
            "growth": growth,
            "post_count": 0,
            "status": "trending" if paying else "",
            "category": "",
            "paying": paying,
            "sample": "",
        }
        for slot, title, growth, paying in rows
    ]


class LiveFeed:
    """Four live Bluesky trends. The fastest-growing one is what the pit pays."""

    source = "bsky"

    def __init__(self) -> None:
        self._winners = dict(BEST)
        self._examples: dict[str, dict[str, list[dict[str, Any]]]] = {
            TIMELINE: defaultdict(list),
            VIRAL: defaultdict(list),
        }
        self._stats: dict[str, dict[str, dict[str, float]]] = {TIMELINE: {}, VIRAL: {}}
        self._queries = {TIMELINE: "", VIRAL: ""}
        self._titles = {TIMELINE: "the quiet tag", VIRAL: "the growing tag"}
        self._meta: dict[str, dict[str, Any]] = {TIMELINE: {}, VIRAL: {}}
        self._board: list[dict[str, Any]] = _stand_in_board()
        self._samples: dict[str, list[dict[str, Any]]] = {name: [] for name in ACTIONS}
        self._cursor = {name: 0 for name in ACTIONS}
        self.error: str | None = None
        self.loaded = False

    def load(self) -> None:
        try:
            payload = _get("app.bsky.unspecced.getTrends", {"limit": str(TREND_LIMIT)})
            trends = list(payload.get("trends") or [])
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.loaded = True
            return
        now = datetime.now(timezone.utc)
        scored: list[dict[str, Any]] = []
        for trend in trends:
            uri = feed_uri(str(trend.get("link") or ""))
            if not uri:
                continue
            scored.append({
                "title": str(trend.get("displayName") or trend.get("topic") or "trend"),
                "category": str(trend.get("category") or ""),
                "status": trend.get("status") or "",
                "post_count": int(trend.get("postCount") or 0),
                "growth": growth_per_hour(trend, now),
                "uri": uri,
            })
        slots = assign_slots(scored)
        if not slots:
            self.error = "no trending feeds"
            self.loaded = True
            return
        self._winners = dict(BEST)
        board: list[dict[str, Any]] = []
        for slot, trend in slots.items():
            try:
                posts = _trend_posts(str(trend["uri"]))
            except Exception:
                posts = []
            samples = []
            for post in posts:
                item = _public_post(post)
                if item["text"] == "(no text)":
                    continue
                samples.append(item)
                if len(samples) >= 12:
                    break
            self._samples[slot] = samples
            if slot == "reply":
                self._titles[TIMELINE] = str(trend["title"])
            if slot == "post":
                self._titles[VIRAL] = str(trend["title"])
            board.append({
                "slot": slot,
                "title": str(trend["title"]),
                "growth": float(trend.get("growth") or 0.0),
                "post_count": int(trend.get("post_count") or 0),
                "status": trend.get("status") or "",
                "category": trend.get("category") or "",
                "paying": slot == "post",
                "sample": samples[0]["text"] if samples else "",
            })
        self._board = board
        self.loaded = True
        self.error = None

    def winners(self) -> dict[str, str]:
        return dict(self._winners)

    def example(self, regime: str, verb: str) -> dict[str, Any] | None:
        bucket = self._samples.get(verb) or []
        if not bucket:
            return None
        cursor = self._cursor.get(verb, 0)
        self._cursor[verb] = cursor + 1
        return bucket[cursor % len(bucket)]

    def public(self) -> dict[str, Any]:
        return {
            "name": "Bluesky",
            "note": "Four live trends. The fastest-growing one pays. Nothing is posted.",
            "error": self.error,
            "board": list(self._board),
            "slices": {
                regime: {
                    "winner": self._winners.get(regime),
                    "query": self._queries.get(regime, ""),
                    "title": self._titles.get(regime, ""),
                    "category": self._meta.get(regime, {}).get("category", ""),
                    "status": self._meta.get(regime, {}).get("status", ""),
                    "post_count": self._meta.get(regime, {}).get("post_count", 0),
                    "stats": self._stats.get(regime, {}),
                }
                for regime in (TIMELINE, VIRAL)
            },
        }
