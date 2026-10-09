import unittest

from datetime import datetime, timezone

from attention_royale.live_feed import (
    assign_slots,
    choose_pair,
    engagement,
    feed_uri,
    growth_per_hour,
    kind_of,
    rank,
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


if __name__ == "__main__":
    unittest.main()
