"""Read-only prices from Binance's public ticker.

The book is every priced USDT pair. Profit is the move after the round
opens. Nothing here is sent to an exchange.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .world import ACTIONS, BEST, TIMELINE, VIRAL

APPVIEW = "https://api.bsky.app/xrpc"
BINANCE = "https://api.binance.com/api/v3/ticker/24hr"
BINANCE_PRICE = "https://api.binance.com/api/v3/ticker/price"
STABLES = frozenset({
    "USDC", "FDUSD", "TUSD", "DAI", "USDP", "EUR", "AEUR", "USD1",
    "USDE", "BFUSD", "USDS", "RLUSD", "XUSD", "BUSD", "USDD",
})
MIN_COUNT = 6
TREND_LIMIT = 10
POOL_SIZE = 8
SHOWN = 12
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
        headers={"Accept": "application/json", "User-Agent": "cadence-trade-royale"},
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


def liquid_opening(pool: list[dict[str, Any]], shift: int, size: int = LIST_SIZE) -> list[int]:
    """Opening five among the busiest coins, shifted so each brain starts different.

    The quiet tail of a big book barely trades, so a bag that never sells
    stays exactly flat. The busiest names reprice, and that is the comparison.
    """
    if not pool:
        return []
    count = min(size, len(pool))
    ranked = sorted(
        range(len(pool)),
        key=lambda index: float(pool[index].get("post_count") or 0.0),
        reverse=True,
    )
    span = min(len(ranked), count + 8)
    head = ranked[:span]
    start = shift % max(span - count + 1, 1)
    return head[start : start + count]


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


STAKE = 1000.0


def open_bag(held: list[int], prices: list[float], stake: float = STAKE) -> dict[str, Any]:
    """Spend the stake evenly on the opening coins. Cash left over stays in the bag."""
    lots: dict[int, dict[str, float]] = {}
    cash = float(stake)
    picks = [index for index in held if 0 <= index < len(prices)]
    if picks:
        slice_cash = cash / len(picks)
        for index in picks:
            price = max(float(prices[index]), 1e-6)
            lots[index] = {"coins": slice_cash / price, "cost": slice_cash}
            cash -= slice_cash
    return {"cash": cash, "lots": lots, "stake": float(stake)}


def mark_bag(bag: dict[str, Any], prices: list[float]) -> float:
    value = float(bag.get("cash") or 0.0)
    for index, lot in (bag.get("lots") or {}).items():
        if 0 <= index < len(prices):
            value += float(lot["coins"]) * float(prices[index])
    return value


def trade_bag(bag: dict[str, Any], sold: int | None, bought: int | None, prices: list[float]) -> None:
    """Sell one coin at the current price and spend the proceeds on another."""
    lots = bag.setdefault("lots", {})
    if sold is None or bought is None or sold == bought:
        return
    if not (0 <= sold < len(prices) and 0 <= bought < len(prices)):
        return
    lot = lots.pop(sold, None)
    if lot is None or bought in lots:
        if lot is not None:
            lots[sold] = lot
        return
    proceeds = float(lot["coins"]) * max(float(prices[sold]), 1e-6)
    bag["cash"] = float(bag.get("cash") or 0.0) + proceeds
    price_in = max(float(prices[bought]), 1e-6)
    lots[bought] = {"coins": proceeds / price_in, "cost": proceeds}
    bag["cash"] -= proceeds


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
        sold = min(kept, key=growth)
    elif style == "second":
        incoming = by_growth[min(1, len(by_growth) - 1)]
        sold = max(kept, key=growth)
    elif style == "crowd":
        incoming = by_posts[-1]
        sold = max(kept, key=posts)
    elif style == "size":
        incoming = by_posts[0]
        sold = min(kept, key=posts)
    elif style == "wander":
        incoming = by_growth[len(by_growth) // 2]
        sold = sorted(kept, key=growth)[len(kept) // 2]
    elif action == "lurk":
        incoming = by_growth[min(1, len(by_growth) - 1)]
        sold = min(kept, key=growth)
    else:
        incoming = by_growth[0]
        sold = min(kept, key=growth)
    if style == "patient" and action != "raid" and growth(incoming) < growth(sold) * 1.75:
        return kept, None
    if style == "hottest" and action != "raid" and growth(incoming) <= growth(sold):
        return kept, None
    if incoming == sold:
        return kept, None
    nxt = list(kept)
    nxt[nxt.index(sold)] = incoming
    return nxt, (sold, incoming)


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


def _money(text: Any) -> float:
    digits = re.sub(r"[^0-9.]", "", str(text or ""))
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def _usd_change(data: dict[str, Any]) -> float:
    change = data.get("price_change_percentage_24h") or {}
    if isinstance(change, dict):
        try:
            return float(change.get("usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(change)
    except (TypeError, ValueError):
        return 0.0


def _get_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "cadence-trade-royale"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _price_quotes(symbols: list[str] | None = None) -> dict[str, float]:
    url = BINANCE_PRICE
    if symbols:
        encoded = urllib.parse.quote(json.dumps(symbols, separators=(",", ":")))
        url = f"{BINANCE_PRICE}?symbols={encoded}"
    payload = _get_json(url)
    quotes: dict[str, float] = {}
    if not isinstance(payload, list):
        return quotes
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            quotes[str(item.get("symbol") or "")] = float(item.get("price"))
        except (TypeError, ValueError):
            continue
    return quotes


def _levered(base: str) -> bool:
    for tag in ("DOWN", "BULL", "BEAR", "UP"):
        if base.endswith(tag) and len(base) > len(tag) + 2:
            return True
    return False


def price_movers(payload: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
    """Every priced USDT pair. Stables and leveraged tokens stay out.

    `growth` starts at zero and later tracks the price change after the round opens.
    """
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        return rows
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "")
        if not symbol.endswith("USDT"):
            continue
        base = symbol[:-4]
        if not base or base in STABLES or _levered(base):
            continue
        try:
            day = float(item.get("priceChangePercent"))
            last = float(item.get("lastPrice"))
            volume = float(item.get("quoteVolume") or 0)
        except (TypeError, ValueError):
            continue
        if last <= 0:
            continue
        rows.append({
            "symbol": symbol,
            "title": base,
            "growth": 0.0,
            "day": round(day, 1),
            "post_count": int(volume),
            "status": "",
            "open": last,
            "last": last,
            "category": "coin",
            "sample": "",
        })
    rows.sort(key=lambda row: float(row["day"]), reverse=True)
    return rows


def visible_moves(board: list[dict[str, Any]], limit: int = SHOWN) -> list[dict[str, Any]]:
    """The page lists the best live move first. The book the brains trade is larger."""
    if any(abs(float(item.get("growth") or 0.0)) > 0 for item in board):
        key = "growth"
    else:
        key = "day"
    ordered = sorted(board, key=lambda item: float(item.get(key) or 0.0), reverse=True)
    return ordered[:limit]


def trending_coins(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Coins people are searching for, biggest daily move first."""
    rows: list[dict[str, Any]] = []
    for entry in payload.get("coins") or []:
        item = entry.get("item") or {}
        data = item.get("data") or {}
        symbol = str(item.get("symbol") or "").upper()
        name = str(item.get("name") or "").strip()
        if not symbol:
            continue
        change = _usd_change(data)
        title = f"{symbol} {name}" if name and name.upper() != symbol else symbol
        rows.append({
            "title": title,
            "growth": round(change, 1),
            "post_count": int(_money(data.get("total_volume"))),
            "status": "24h",
            "category": "coin",
            "sample": "",
        })
    rows.sort(key=lambda row: float(row["growth"]), reverse=True)
    return rows


class LiveFeed:
    """Live USDT prices. The score is the move after the round opens."""

    source = "binance"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = False
        self._thread: threading.Thread | None = None
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
        self._quote_error: str | None = None
        self._quoted_at: float | None = None
        self.loaded = False

    def load(self) -> None:
        try:
            payload = _get_json(BINANCE)
            ordered = price_movers(payload)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.loaded = True
            return
        if len(ordered) < 4:
            self.error = "not enough coins on the book"
            self.loaded = True
            return
        self._winners = dict(BEST)
        self._titles[VIRAL] = str(ordered[0]["title"])
        self._titles[TIMELINE] = str(ordered[-1]["title"])
        board = []
        for index, story in enumerate(ordered):
            board.append({
                "id": index,
                "symbol": story["symbol"],
                "title": str(story["title"]),
                "growth": 0.0,
                "day": float(story["day"]),
                "post_count": int(story["post_count"]),
                "status": "",
                "open": float(story["open"]),
                "last": float(story["last"]),
                "category": "coin",
                "sample": "",
            })
        with self._lock:
            self._board = board
        self.loaded = True
        self.error = None
        self._quote_error = None
        self._quoted_at = time.time()
        self._ensure_poll()

    def mark_open(self) -> None:
        """Start profit from the price on the book right now."""
        with self._lock:
            for item in self._board:
                last = float(item.get("last") or 0.0)
                if last <= 0:
                    continue
                item["open"] = last
                item["growth"] = 0.0

    def book(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._board]

    def poll(self) -> None:
        with self._lock:
            if not any(item.get("symbol") for item in self._board):
                return
        try:
            quoted = _price_quotes()
        except Exception as exc:
            with self._lock:
                self._quote_error = type(exc).__name__
            return
        if not quoted:
            with self._lock:
                self._quote_error = "no prices"
            return
        with self._lock:
            self._quote_error = None
            self._quoted_at = time.time()
            for item in self._board:
                last = quoted.get(str(item.get("symbol") or ""))
                if not last:
                    continue
                item["last"] = last
                open_px = float(item.get("open") or last)
                item["growth"] = round((last / open_px - 1.0) * 100.0, 2)

    def _ensure_poll(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._poll_loop, name="prices", daemon=True)
        self._thread.start()

    def _poll_loop(self) -> None:
        while not self._stop:
            time.sleep(2.0)
            try:
                self.poll()
            except Exception:
                continue

    def winners(self) -> dict[str, str]:
        return dict(self._winners)

    def example(self, regime: str, verb: str) -> dict[str, Any] | None:
        bucket = self._samples.get(verb) or []
        if not bucket:
            return None
        cursor = self._cursor.get(verb, 0)
        self._cursor[verb] = cursor + 1
        return bucket[cursor % len(bucket)]

    def _feed_status(self) -> str:
        if self.error:
            return "down"
        if not self.loaded:
            return "reading"
        quoted_at = self._quoted_at
        if self._quote_error and quoted_at is None:
            return "down"
        if quoted_at is None or time.time() - quoted_at > 12:
            return "stale"
        return "live"

    def public(self) -> dict[str, Any]:
        with self._lock:
            board = [dict(item) for item in self._board]
        return {
            "name": "Binance",
            "url": "https://www.binance.com/en/markets",
            "status": self._feed_status(),
            "note": "Every USDT pair. Profit is the move after the round opens.",
            "error": self.error,
            "count": len(board),
            "board": visible_moves(board),
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
