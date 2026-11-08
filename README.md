# Crypto Price Alert Bot

A small Telegram bot that answers two commands: live crypto prices from Binance,
and a (stubbed) price alert.

Built with [`python-telegram-bot`](https://python-telegram-bot.org) v22 and `requests`.

## Commands

| Command | What it does |
| --- | --- |
| `/price <ticker>` | Replies with the live USDT price, e.g. `/price BTC` → `BTC/USDT: $75,853.78` |
| `/alert <ticker> <target>` | Confirms an alert, e.g. `/alert BTC 75000` → `Alert set for BTC at $75,000` |
| `/start`, `/help` | Prints the command list |

Tickers are case-insensitive, and `BTC`, `btc`, `BTCUSDT` and `BTC/USDT` all work.

## How it behaves

- **Prices** come from Binance's public ticker endpoint
  (`GET /api/v3/ticker/price?symbol=BTCUSDT`) — no API key or account needed.
- **Failures are handled.** If Binance times out, returns an HTTP error, sends
  unreadable JSON, or does not list the symbol, the bot replies
  `Sorry, I couldn't fetch the price right now.` rather than crashing.
- **Bad input is answered, not ignored.** A missing argument, a malformed ticker
  or a non-numeric target each get a short usage hint.
- **The event loop stays free.** `requests` is blocking, so the HTTP call is run
  in a worker thread via `asyncio.to_thread`.

## Requirements

- Python 3.10 or newer
- A bot token from [@BotFather](https://t.me/BotFather)

Tested on Python 3.13.5 with `python-telegram-bot==22.8` and `requests==2.34.2`.

## Setup

1. **Create the bot.** Message [@BotFather](https://t.me/BotFather) on Telegram,
   send `/newbot`, follow the prompts, and copy the token it gives you.

2. **Clone and install.**

   ```bash
   git clone https://github.com/<your-username>/telegram-price-bot.git
   cd telegram-price-bot
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
