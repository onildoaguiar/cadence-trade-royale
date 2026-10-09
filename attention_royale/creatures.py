"""The six accounts. Same verbs, a different way of trading for each one."""

from __future__ import annotations

CREATURES: tuple[dict, ...] = (
    {
        "id": "frog",
        "name": "frog",
        "handle": "@gm",
        "mark": "GM",
        "color": "#d6ff4a",
        "ink": "#17180f",
        "seed": 11,
        "style": "hottest",
        "taste": "scalper",
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
        "taste": "sells winners",
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
        "taste": "diamond hands",
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
        "taste": "buys small",
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
        "taste": "buys size",
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
        "taste": "wanders",
    },
)

# Color for an unused tape. The brain never reads these strings. It only settles a verb.
LINES: dict[str, dict[str, tuple[str, ...]]] = {
    "timeline": {
        "lurk": (
            "watches the tape",
            "leaves the bid",
            "refreshes the book",
        ),
        "post": (
            "lifts the offer",
            "buys the pop",
            "chases the print",
        ),
        "reply": (
            "sits on the bag",
            "holds the fill",
            "does not chase",
        ),
        "raid": (
            "hits the bid",
            "dumps the quiet coin",
            "sells into a dead tape",
        ),
    },
    "viral": {
        "lurk": (
            "freezes on the print",
            "watches the rip and passes",
            "steps off the tape",
        ),
        "post": (
            "buys the rip",
            "chases the leader",
            "adds into the move",
        ),
        "reply": (
            "holds through the rip",
            "keeps the bag",
            "does not sell the winner",
        ),
        "raid": (
            "fades the leader",
            "buys the cold coin",
            "sells the winner for size",
        ),
    },
}
