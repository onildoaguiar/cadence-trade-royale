# Trade Royale

A [Cadence](https://github.com/muellerberndt/cadence) battle. Six traders each hold a simulated bag of five coins. They can buy any USDT pair on the public [Binance](https://www.binance.com) ticker.

Each trader starts with $1,000. Selling one coin and buying another is the only move, and the board is who made more. Nothing is sent to an exchange.

A copy of each trader sits the round out after the first lesson, so that bag never trades. A random bag trades with no style. The live traders keep learning.

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export OMP_NUM_THREADS=1
.venv/bin/python server.py
```

Open http://127.0.0.1:8765/. The page reads live prices. Each trader starts with $1,000 and plays a different style: scalper, sells winners, diamond hands, buys small, buys size, wanders. The board is who made more after the round opened.

- **Space** pauses.
- **New round** resets the bags. The traders keep what they already learned.

Pick a trader to see the style, the last trade, and each coin's gain.

## Where the coins come from

The book is Binance's public 24h ticker: every USDT pair except stables and leveraged tokens. No token is required. The page lists the coins that are moving. A bag is marked to the live price after the round opens. The page only reads. Buys and sells are simulated.

The traders are [Cadence](https://github.com/muellerberndt/cadence) `0.80.0` (`Brain.compose` and `Brain.live` from `cadence-net`). One life per name, and that life keeps going.

## Checks

```sh
.venv/bin/python -m unittest tests.test_world tests.test_live_feed tests.test_repair
```

`tests.test_repair` checks that traders who keep learning move onto the action that improves the bag. The copies that sat out do not.
