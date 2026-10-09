# Trending Royale

A demo of [Cadence](https://github.com/muellerberndt/cadence). Six brains learn which live [Bluesky](https://bsky.app) trend is growing fastest.

Each brain picks one trend. The trend gaining posts fastest adds a point. The other trends take a point away. The brain does not read the trend's name. It only feels that score, and the next pick moves toward what paid.

The ranking is who found that trend and stayed on it. A copy of each brain stops learning after a first lesson on a quieter trend, so that copy falls behind. Picking at random is the floor. Nothing is posted.

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export OMP_NUM_THREADS=1
.venv/bin/python server.py
```

Open http://127.0.0.1:8765/. The page reads Bluesky's public trends, teaches each brain a quieter trend, then scores the one growing fastest. After about half a minute, the brains that are still learning should sit on that trend. The copies that stopped should not.

- **Space** pauses.
- **Clear scores** starts the ranking over. The brains keep what they already learned.

Click a brain to read its last lesson: whether that pick added points, and whether the brain was surprised or calm.

## Where the trends come from

Bluesky publishes a public trends list. No token is required. Growth is posts per hour since the trend started, and a cooling trend counts for less. The page only reads. It does not post, like, or follow.

The brains are [Cadence](https://github.com/muellerberndt/cadence) `0.80.0` (`Brain.compose` and `Brain.live` from `cadence-net`). One brain per name, and that brain keeps going.

## Checks

```sh
.venv/bin/python -m unittest tests.test_world tests.test_live_feed tests.test_repair
```

`tests.test_repair` teaches two brains a quiet trend, then scores a different one. The brains that keep learning move. The copies that stopped do not.
