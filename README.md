# Trending Royale

A demo of [Cadence](https://github.com/muellerberndt/cadence). Six brains each keep a list of five crypto news stories from public [Bluesky](https://bsky.app) posts.

Points are how fast those five are growing, in posts per hour. A brain does not read the names. It only feels the score, and it swaps a slower trend for a faster one when that raises the score.

The ranking is who built the list that earns more. A copy of each brain stops learning after the first lesson, so it keeps the quieter five and falls behind. Nothing is posted.

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export OMP_NUM_THREADS=1
.venv/bin/python server.py
```

Open http://127.0.0.1:8765/. The page reads crypto headlines that people posted from CoinDesk, Cointelegraph, The Block, and Decrypt. Each brain starts with five quieter stories. After about half a minute, the brains that are still learning should have swapped in the ones being shared faster. The copies that stopped should still hold the quieter five.

- **Space** pauses.
- **Clear scores** starts the ranking over. The brains keep what they already learned.

Click a brain to read its last lesson: whether that pick added points, and whether the brain was surprised or calm.

## Where the stories come from

The pool is crypto news: public Bluesky posts from the last day that link to CoinDesk, Cointelegraph, The Block, or Decrypt. No token is required. A story's score is how fast it is being shared. The page only reads. It does not post, like, follow, or trade.

The brains are [Cadence](https://github.com/muellerberndt/cadence) `0.80.0` (`Brain.compose` and `Brain.live` from `cadence-net`). One brain per name, and that brain keeps going.

## Checks

```sh
.venv/bin/python -m unittest tests.test_world tests.test_live_feed tests.test_repair
```

`tests.test_repair` checks that brains which keep learning move onto the action that improves the list. The copies that stopped do not.
