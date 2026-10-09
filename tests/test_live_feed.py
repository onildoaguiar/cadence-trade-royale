import unittest

from datetime import datetime, timezone

from attention_royale.live_feed import (
    assign_slots,
    choose_pair,
    engagement,
    feed_uri,
    growth_per_hour,
    kind_of,
    liquid_opening,
    list_points,
    mark_bag,
    news_stories,
    open_bag,
    trade_bag,
    quiet_list,
    rank,
    revise_list,
    price_movers,
    starting_list,
    trending_coins,
)


def _post(kind: str, likes: int, reposts: int = 0) -> dict:
    record: dict = {"text": "hello"}
    embed = {}
    if kind == "reply":
        record["reply"] = {"parent": {"uri": "at://x"}}
    if kind == "raid":
        embed = {"$type": "app.bsky.embed.record"}
    return {
        "likeCount": likes,
        "repostCount": reposts,
        "replyCount": 0,
        "record": record,
        "embed": embed,
        "author": {"handle": "someone.bsky.social"},
        "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
    }


class RankTest(unittest.TestCase):
    def test_kind(self) -> None:
        self.assertEqual(kind_of(_post("post", 1)), "post")
        self.assertEqual(kind_of(_post("reply", 1)), "reply")
        self.assertEqual(kind_of(_post("raid", 1)), "raid")
        self.assertEqual(engagement(_post("post", 3, reposts=2)), 7)

    def test_replies_win_when_originals_are_quiet(self) -> None:
        posts = [_post("post", 0) for _ in range(30)]
        posts += [_post("reply", 2) for _ in range(12)]
        winner, stats = rank(posts)
        self.assertEqual(winner, "reply")
        self.assertGreater(stats["reply"]["median"], stats["post"]["median"])

    def test_a_handful_of_quotes_cannot_win(self) -> None:
        posts = [_post("post", 4) for _ in range(20)]
        posts += [_post("raid", 100) for _ in range(3)]
        winner, _stats = rank(posts)
        self.assertEqual(winner, "post")

    def test_originals_win_a_viral_slice(self) -> None:
        posts = [_post("post", 800) for _ in range(40)]
        posts += [_post("reply", 40) for _ in range(15)]
        posts += [_post("raid", 200) for _ in range(15)]
        winner, _stats = rank(posts)
        self.assertEqual(winner, "post")


class TrendPairTest(unittest.TestCase):
    def test_feed_uri_from_relative_and_absolute_links(self) -> None:
        relative = "/profile/did:plc:abc/feed/topic1"
        absolute = "https://bsky.app/profile/did:plc:abc/feed/topic1"
        expected = "at://did:plc:abc/app.bsky.feed.generator/topic1"
        self.assertEqual(feed_uri(relative), expected)
        self.assertEqual(feed_uri(absolute), expected)
        self.assertIsNone(feed_uri("/profile/did:plc:abc/post/xyz"))

    def test_pair_prefers_different_winners(self) -> None:
        scored = [
            {"title": "one", "winner": "post", "status": "trending"},
            {"title": "two", "winner": "post", "status": "trending"},
            {"title": "three", "winner": "raid", "status": "cooling"},
        ]
        left, right = choose_pair(scored)
        self.assertEqual(left["winner"], "post")
        self.assertEqual(right["winner"], "raid")
        self.assertEqual(left["title"], "one")

    def test_pair_falls_back_to_the_first_two(self) -> None:
        scored = [
            {"title": "one", "winner": "post", "status": "trending"},
            {"title": "two", "winner": "post", "status": ""},
        ]
        left, right = choose_pair(scored)
        self.assertEqual([left["title"], right["title"]], ["one", "two"])
        self.assertIsNone(choose_pair([]))

    def test_fastest_trend_takes_the_paying_slot(self) -> None:
        now = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
        hot = {
            "displayName": "hot",
            "postCount": 400,
            "startedAt": "2026-10-09T12:00:00.000Z",
            "status": "trending",
        }
        cold = {
            "displayName": "cold",
            "postCount": 40,
            "startedAt": "2026-10-09T04:00:00.000Z",
            "status": "cooling",
        }
        self.assertGreater(growth_per_hour(hot, now), growth_per_hour(cold, now))
        slots = assign_slots([
            {"title": "a", "growth": 10},
            {"title": "b", "growth": 80},
            {"title": "c", "growth": 3},
            {"title": "d", "growth": 20},
        ])
        self.assertEqual(slots["post"]["title"], "b")
        self.assertEqual(slots["reply"]["title"], "c")

    def test_a_brain_swaps_a_quiet_list_toward_hotter_trends(self) -> None:
        pool = [{"title": name, "growth": growth} for name, growth in (
            ("hot", 80), ("fast", 60), ("warm", 40), ("steady", 28),
            ("fading", 18), ("quiet", 12), ("cold", 7), ("quietest", 3),
        )]
        held = quiet_list(len(pool))
        self.assertEqual([pool[i]["title"] for i in held], ["steady", "fading", "quiet", "cold", "quietest"])
        before = list_points(pool, held)
        nxt, swap = revise_list(pool, held, "post")
        self.assertEqual(pool[swap[0]]["title"], "quietest")
        self.assertEqual(pool[swap[1]]["title"], "hot")
        self.assertGreater(list_points(pool, nxt), before)
        held_on, same = revise_list(pool, held, "reply")
        self.assertEqual(held_on, held)
        self.assertIsNone(same)
        for index, item in enumerate(pool):
            item["post_count"] = 1000 if item["title"] == "warm" else 10 + index
        _sized, size_swap = revise_list(pool, held, "post", "size")
        self.assertIsNotNone(size_swap)
        self.assertEqual(pool[size_swap[1]]["title"], "warm")
        _jeet, jeet_swap = revise_list(pool, held, "post", "second")
        self.assertEqual(pool[jeet_swap[0]]["title"], "steady")
        self.assertEqual(pool[jeet_swap[1]]["title"], "fast")
        self.assertNotEqual(starting_list(len(pool), 0), starting_list(len(pool), 1))

    def test_a_busy_book_opens_on_the_coins_that_reprice(self) -> None:
        pool = [
            {"post_count": 1, "title": "dust"},
            {"post_count": 900, "title": "btc"},
            {"post_count": 800, "title": "eth"},
            {"post_count": 50, "title": "mid"},
            {"post_count": 700, "title": "sol"},
            {"post_count": 2, "title": "flat"},
            {"post_count": 600, "title": "bnb"},
            {"post_count": 500, "title": "xrp"},
        ]
        first = liquid_opening(pool, 0)
        self.assertEqual([pool[index]["title"] for index in first], ["btc", "eth", "sol", "bnb", "xrp"])
        second = liquid_opening(pool, 1)
        self.assertNotEqual(first, second)
        self.assertNotIn("dust", [pool[index]["title"] for index in second])


def _news(text: str, when: str, likes: int = 0) -> dict:
    return {
        "likeCount": likes,
        "repostCount": 0,
        "indexedAt": when,
        "record": {"text": text, "createdAt": when},
    }


class BagTest(unittest.TestCase):
    def test_a_swap_sells_one_coin_and_buys_the_next(self) -> None:
        prices = [1.0, 1.0, 1.0]
        bag = open_bag([0, 1], prices, 100)
        prices[0] = 1.5
        trade_bag(bag, 0, 2, prices)
        self.assertNotIn(0, bag["lots"])
        self.assertAlmostEqual(bag["lots"][2]["coins"], 75.0)
        self.assertAlmostEqual(mark_bag(bag, prices), 125.0)


class PriceMoversTest(unittest.TestCase):
    def test_the_book_is_every_priced_pair(self) -> None:
        def row(base: str, change: float, volume: float) -> dict:
            return {
                "symbol": f"{base}USDT",
                "priceChangePercent": str(change),
                "lastPrice": "2",
                "quoteVolume": str(volume),
            }

        payload = [
            row("MAGIC", 80, 20_000_000),
            row("STRK", 27, 20_000_000),
            row("ATOM", 21, 20_000_000),
            row("DOT", 18, 20_000_000),
            row("KAIA", 12, 20_000_000),
            row("OGN", -19, 20_000_000),
            row("RLC", -6, 20_000_000),
            row("GTC", -5, 20_000_000),
            row("USDC", 0.1, 9_000_000_000),
            row("DUST", 400, 1_000),
            row("JUP", 30, 20_000_000),
            row("BTCUP", 90, 20_000_000),
        ]
        picked = price_movers(payload)
        titles = [item["title"] for item in picked]
        self.assertEqual(titles[0], "DUST")
        self.assertIn("MAGIC", titles)
        self.assertIn("OGN", titles)
        self.assertIn("JUP", titles)
        self.assertIn("DUST", titles)
        self.assertGreater(len(picked), 8)
        self.assertNotIn("USDC", titles)
        self.assertNotIn("BTCUP", titles)
        magic = next(item for item in picked if item["title"] == "MAGIC")
        self.assertEqual(magic["growth"], 0.0)
        self.assertEqual(magic["day"], 80.0)
        self.assertEqual(magic["open"], 2.0)


class TrendingCoinsTest(unittest.TestCase):
    def test_the_biggest_daily_move_ranks_first(self) -> None:
        payload = {
            "coins": [
                {"item": {"symbol": "down", "name": "Down", "data": {
                    "price_change_percentage_24h": {"usd": -10},
                    "total_volume": "$1,000",
                }}},
                {"item": {"symbol": "drv", "name": "Derive", "data": {
                    "price_change_percentage_24h": {"usd": 20.4},
                    "total_volume": "$2,500,000",
                }}},
            ]
        }
        rows = trending_coins(payload)
        self.assertEqual(rows[0]["title"], "DRV Derive")
        self.assertEqual(rows[0]["growth"], 20.4)
        self.assertEqual(rows[0]["post_count"], 2500000)
        self.assertEqual(rows[1]["title"], "DOWN")


class CryptoNewsTest(unittest.TestCase):
    def test_repeat_headlines_merge_and_newer_stories_rank_higher(self) -> None:
        now = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
        posts = [
            _news(
                "Ledger probes possible wallet tampering after reports of stolen crypto from reseller devices.",
                "2026-10-09T04:00:00Z",
            ),
            _news(
                "Ledger probes wallet tampering after stolen crypto was linked to reseller devices in Asia.",
                "2026-10-09T05:00:00Z",
                likes=2,
            ),
            _news(
                "Bitcoin nears a three-week low as oil heads higher on strike worries across the region.",
                "2026-10-09T15:30:00Z",
            ),
        ]
        stories = news_stories(posts, now)
        self.assertEqual(len(stories), 2)
        self.assertIn("Bitcoin", stories[0]["title"])
        self.assertGreater(stories[0]["growth"], stories[1]["growth"])
        self.assertEqual(stories[1]["post_count"], 2)


if __name__ == "__main__":
    unittest.main()
