"""Read-only crypto news from public Bluesky posts.

Each story is a headline linking to a crypto news site. Nothing here posts,
likes, or follows.
"""

from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .world import ACTIONS, BEST, TIMELINE, VIRAL

APPVIEW = "https://api.bsky.app/xrpc"
MIN_COUNT = 6
TREND_LIMIT = 10
POOL_SIZE = 8
LIST_SIZE = 5
NEWS_DOMAINS = ("coindesk.com", "cointelegraph.com", "theblock.co", "decrypt.co")
NEWS_HOURS = 24
_STOP = {
    "the", "and", "for", "with", "after", "from", "that", "this", "crypto",
    "says", "into", "over", "have", "been", "will", "its", "are",
}


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


def quiet_list(pool_size: int, size: int = LIST_SIZE) -> list[int]:
    """The slower trends."""
    if pool_size <= 0:
        return []
    if pool_size <= size:
        return list(range(pool_size))
    return list(range(pool_size - size, pool_size))


def starting_list(pool_size: int, shift: int, size: int = LIST_SIZE) -> list[int]:
    """A different opening five for each brain, still toward the slower end."""
    if pool_size <= 0:
        return []
    count = min(size, pool_size)
    room = max(pool_size - count, 0)
    end = pool_size - (shift % (room + 1))
    start = max(0, end - count)
    held = list(range(start, end))
    for index in range(pool_size):
        if len(held) >= count:
            break
        if index not in held:
            held.append(index)
    return held[:count]


def list_points(pool: list[dict[str, Any]], held: list[int]) -> float:
    """Points from the list: posts per hour across the five, scaled down."""
    total = 0.0
    for index in held:
        if 0 <= index < len(pool):
            total += float(pool[index].get("growth") or 0.0)
    return round(total / 100.0, 2)


def revise_list(
    pool: list[dict[str, Any]],
    held: list[int],
    action: str,
    style: str = "hottest",
) -> tuple[list[int], tuple[int, int] | None]:
    """Swap one trend. The style decides which outside trend this brain wants."""
    kept: list[int] = []
    seen: set[int] = set()
    for index in held:
        if 0 <= index < len(pool) and index not in seen:
            seen.add(index)
            kept.append(index)
    outside = [index for index in range(len(pool)) if index not in seen]
    if action == "reply" or not outside or not kept:
        return kept, None

    def growth(index: int) -> float:
        return float(pool[index].get("growth") or 0.0)

    def posts(index: int) -> float:
        return float(pool[index].get("post_count") or 0.0)

    by_growth = sorted(outside, key=growth, reverse=True)
    by_posts = sorted(outside, key=posts, reverse=True)
    if action == "raid":
        incoming = by_growth[-1]
    elif style == "second":
        incoming = by_growth[min(1, len(by_growth) - 1)]
    elif style == "crowd":
        incoming = by_posts[-1]
    elif style == "size":
        incoming = by_posts[0]
    elif style == "wander":
        incoming = by_growth[len(by_growth) // 2]
    elif action == "lurk":
        incoming = by_growth[min(1, len(by_growth) - 1)]
    else:
        incoming = by_growth[0]
    weakest = min(kept, key=growth)
    if style == "patient" and action != "raid" and growth(incoming) < growth(weakest) * 1.75:
        return kept, None
    if style in ("hottest", "second") and action != "raid" and growth(incoming) <= growth(weakest):
        return kept, None
    if incoming == weakest:
        return kept, None
    nxt = list(kept)
    nxt[nxt.index(weakest)] = incoming
    return nxt, (weakest, incoming)


def _trend_posts(uri: str) -> list[dict[str, Any]]:
    payload = _get("app.bsky.feed.getFeed", {"feed": uri, "limit": "8"})
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
        ("post", "the growing tag", 80.0, True),
        ("lurk", "a fast tag", 60.0, False),
        ("raid", "a warm tag", 40.0, False),
        ("reply", "a steady tag", 28.0, False),
        ("post", "a fading tag", 18.0, False),
        ("lurk", "a quiet tag", 12.0, False),
        ("raid", "a cold tag", 7.0, False),
        ("reply", "the quietest tag", 3.0, False),
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


def _headline(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", " ", text)
    cleaned = re.sub(r"^[^\w]+", "", " ".join(cleaned.split()))
    parts = re.split(r"(?<=[a-z]) (?=[A-Z])", cleaned, maxsplit=1)
    cleaned = parts[0]
    for mark in (". ", "? ", "! "):
        cut = cleaned.find(mark)
        if cut >= 28:
            cleaned = cleaned[:cut]
            break
    if len(cleaned) > 72:
        cleaned = cleaned[:72].rsplit(" ", 1)[0]
    return cleaned


def _story_tokens(title: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9]{3,}", title.lower())
        if word not in _STOP
    }


def _when(post: dict[str, Any], now: datetime) -> datetime:
    raw = str(post.get("indexedAt") or (post.get("record") or {}).get("createdAt") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return now


def _crypto_news_posts() -> list[dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(hours=NEWS_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found: list[dict[str, Any]] = []
    errors: list[Exception] = []
    for domain in NEWS_DOMAINS:
        try:
            payload = _get("app.bsky.feed.searchPosts", {
                "q": "crypto",
                "domain": domain,
                "sort": "latest",
                "lang": "en",
                "since": since,
                "limit": "100",
            })
        except Exception as exc:
            errors.append(exc)
            continue
        for post in payload.get("posts") or []:
            if isinstance(post, dict):
                found.append(post)
    if not found and errors:
        raise errors[0]
    return found


def news_stories(posts: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Distinct headlines, fastest share-rate first."""
    clock = now or datetime.now(timezone.utc)
    clusters: list[dict[str, Any]] = []
    for post in posts:
        title = _headline(" ".join(str((post.get("record") or {}).get("text") or "").split()))
        if len(title) < 40:
            continue
        tokens = _story_tokens(title)
        if len(tokens) < 3:
            continue
        likes = int(post.get("likeCount") or 0)
        reposts = int(post.get("repostCount") or 0)
        when = _when(post, clock)
        placed = False
        for cluster in clusters:
            shared = tokens & cluster["tokens"]
            union = tokens | cluster["tokens"]
            if len(shared) >= 2 and len(shared) / len(union) >= 0.34:
                cluster["post_count"] += 1
                cluster["likes"] += likes
                cluster["reposts"] += reposts
                cluster["when"] = min(cluster["when"], when)
                placed = True
                break
        if not placed:
            clusters.append({
                "title": title,
                "tokens": tokens,
                "post_count": 1,
                "likes": likes,
                "reposts": reposts,
                "when": when,
            })
    scored: list[dict[str, Any]] = []
    for cluster in clusters:
        hours = max(0.25, (clock - cluster["when"]).total_seconds() / 3600)
        attention = cluster["post_count"] + cluster["likes"] + 2 * cluster["reposts"]
        scored.append({
            "title": cluster["title"],
            "growth": round(attention / hours, 1),
            "post_count": int(cluster["post_count"]),
            "status": "new" if hours < 3 else "live" if hours < 12 else "older",
            "category": "crypto",
            "sample": "",
        })
    scored.sort(key=lambda item: float(item["growth"]), reverse=True)
    return scored


class LiveFeed:
    """Crypto headlines from public Bluesky. Faster stories are worth more."""

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
            posts = _crypto_news_posts()
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.loaded = True
            return
        ordered = news_stories(posts)[:POOL_SIZE]
        if len(ordered) < 4:
            self.error = "not enough crypto news"
            self.loaded = True
            return
        self._winners = dict(BEST)
        self._titles[VIRAL] = str(ordered[0]["title"])
        self._titles[TIMELINE] = str(ordered[-1]["title"])
        self._board = [
            {
                "id": index,
                "title": str(story["title"]),
                "growth": float(story["growth"]),
                "post_count": int(story["post_count"]),
                "status": story["status"],
                "category": "crypto",
                "sample": "",
            }
            for index, story in enumerate(ordered)
        ]
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
            "note": "Crypto news only. Points are how fast each story is being shared.",
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
