"""The six accounts. Same verbs, different taste in which trend they swap in."""

from __future__ import annotations

CREATURES: tuple[dict, ...] = (
    {
        "id": "frog",
        "name": "gm frog",
        "handle": "@gm",
        "mark": "GM",
        "color": "#d6ff4a",
        "ink": "#17180f",
        "seed": 11,
        "style": "hottest",
        "taste": "grabs the fastest",
    },
    {
        "id": "jeet",
        "name": "jeet",
        "handle": "@jeet",
        "mark": "JT",
        "color": "#ff5a36",
        "ink": "#1c0d09",
        "seed": 23,
        "style": "second",
        "taste": "takes the one behind",
    },
    {
        "id": "diamond",
        "name": "diamond",
        "handle": "@diamond",
        "mark": "DM",
        "color": "#9fd4ff",
        "ink": "#0c141b",
        "seed": 37,
        "style": "patient",
        "taste": "waits for a big jump",
    },
    {
        "id": "pasta",
        "name": "copypasta",
        "handle": "@pasta",
        "mark": "CP",
        "color": "#ffcf70",
        "ink": "#1c150b",
        "seed": 41,
        "style": "crowd",
        "taste": "follows the small one",
    },
    {
        "id": "whale",
        "name": "whale",
        "handle": "@whale",
        "mark": "WH",
        "color": "#e0b0ff",
        "ink": "#160d1b",
        "seed": 53,
        "style": "size",
        "taste": "follows the biggest",
    },
    {
        "id": "npc",
        "name": "npc",
        "handle": "@npc",
        "mark": "NP",
        "color": "#f3efe7",
        "ink": "#161412",
        "seed": 67,
        "style": "wander",
        "taste": "wanders the middle",
    },
)

# What the feed shows. The brain never reads these strings. It only settles a verb.
LINES: dict[str, dict[str, tuple[str, ...]]] = {
    "timeline": {
        "lurk": (
            "sits in the replies",
            "types gm, deletes it",
            "refreshes and leaves",
        ),
        "post": (
            "gm. the chart is a feeling",
            "posted a candle with no thesis",
            "gm to everyone still here",
        ),
        "reply": (
            "gm ser. you dropped this",
            "reply guy, but correct",
            "under the post before the timeline moved",
        ),
        "raid": (
            "ratio attempt. the timeline shrugged",
            "quote-tweeted into silence",
            "raid on a feed that wanted gm",
        ),
    },
    "viral": {
        "lurk": (
            "logs off loudly",
            "watches the red and says nothing",
            "muted the chat",
        ),
        "post": (
            "it is so over, posted raw",
            "eulogy for the candle",
            "a thread nobody finishes",
        ),
        "reply": (
            "well actually, into the void",
            "replied gm while the pool drained",
            "ackshually, as a reply",
        ),
        "raid": (
            "quote-tweeted the timeline into dust",
            "raid landed. the replies scattered",
            "one quote and the feed flinched",
        ),
    },
}
