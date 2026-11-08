"""Telegram bot that answers /price and /alert with live Binance prices.

Run with:  python bot.py
Requires:  TELEGRAM_BOT_TOKEN in the environment (see README.md)
"""

import asyncio
import logging
import os

import requests
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
REQUEST_TIMEOUT = 10  # seconds

HELP_TEXT = (
    "Crypto price bot. Commands:\n"
    "/price <ticker>  - live USDT price, e.g. /price BTC\n"
    "/alert <ticker> <target_price>  - e.g. /alert BTC 75000"
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class PriceError(Exception):
    """Raised when a price could not be fetched."""


def normalise_ticker(raw: str) -> str:
    """'btc' -> 'BTC'; 'BTCUSDT' / 'BTC/USDT' / 'BTC-USDT' -> 'BTC'.

    Returns '' for anything unusable. A hyphen or slash is only accepted as
    the quote-currency separator, so a typo like 'BT-C' is rejected rather
    than silently turned into a real ticker.
    """
    ticker = raw.strip().upper().replace(" ", "")
    for sep in ("/", "-"):
        suffix = f"{sep}USDT"
        if ticker.endswith(suffix) and len(ticker) > len(suffix):
            ticker = ticker[: -len(suffix)]
            break
    else:
        if ticker.endswith("USDT") and len(ticker) > 4:
            ticker = ticker[:-4]
    if not ticker.isalnum():
        return ""
    return ticker


def fetch_price(ticker: str) -> float:
    """Return the live USDT price for `ticker` from Binance.

    Blocking on purpose: the caller runs it in a worker thread. Raises
    PriceError for anything that stops us returning a usable number.
    """
    symbol = f"{ticker}USDT"

    try:
        response = requests.get(
            BINANCE_PRICE_URL,
            params={"symbol": symbol},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.Timeout as exc:
        raise PriceError(f"Binance timed out for {symbol}") from exc
    except requests.exceptions.HTTPError as exc:
        # 400 here means Binance does not list that symbol.
        raise PriceError(f"Binance returned {exc.response.status_code} for {symbol}") from exc
    except requests.exceptions.RequestException as exc:
        raise PriceError(f"Binance request failed for {symbol}") from exc
    except ValueError as exc:  # non-JSON body
        raise PriceError(f"Binance sent an unreadable body for {symbol}") from exc

    try:
        return float(payload["price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PriceError(f"Unexpected Binance payload: {payload!r}") from exc


def format_price(value: float) -> str:
    """Format a price with sensible precision for both BTC and small alts."""
    if value >= 1:
        return f"{value:,.2f}"
    if value >= 0.01:
        return f"{value:,.4f}"
    return f"{value:.8f}".rstrip("0").rstrip(".")


def format_target(value: float) -> str:
    """Format an alert target: 75000 -> '75,000', 2450.5 -> '2,450.50',
    0.00001234 -> '0.00001234' (a fixed 2dp would show '$0.00')."""
    if value == int(value):
        return f"{int(value):,}"
    if value >= 1:
        return f"{value:,.2f}"
    if value >= 0.01:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:.8f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# Command handlers
# --------------------------------------------------------------------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/price <ticker> -> live USDT price."""
    message = update.effective_message

    if not context.args:
        await message.reply_text("Usage: /price <ticker>  e.g. /price BTC")
        return

    ticker = normalise_ticker(context.args[0])
    if not ticker:
        await message.reply_text("That ticker doesn't look right. Use letters/numbers, e.g. /price BTC")
        return

    # requests is blocking; keep the bot's event loop free.
    await message.chat.send_action(ChatAction.TYPING)

    try:
        price = await asyncio.to_thread(fetch_price, ticker)
    except PriceError as exc:
        logger.warning("price lookup failed for %s: %s", ticker, exc)
        await message.reply_text("Sorry, I couldn't fetch the price right now.")
        return
    except Exception:  # last-resort net so one bad lookup can't kill the handler
        logger.exception("unexpected error fetching %s", ticker)
        await message.reply_text("Sorry, I couldn't fetch the price right now.")
        return

    await message.reply_text(f"{ticker}/USDT: ${format_price(price)}")


async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/alert <ticker> <target_price> -> confirms the alert (MVP: no watcher)."""
    message = update.effective_message

    if len(context.args) < 2:
        await message.reply_text("Usage: /alert <ticker> <target_price>  e.g. /alert BTC 75000")
        return

    ticker = normalise_ticker(context.args[0])
    raw_target = context.args[1].strip().replace(",", "").lstrip("$")

    if not ticker:
        await message.reply_text("That ticker doesn't look right. Use letters/numbers, e.g. /alert BTC 75000")
        return

    try:
        target = float(raw_target)
    except ValueError:
        await message.reply_text("The target price must be a number, e.g. /alert BTC 75000")
        return

    if target <= 0:
        await message.reply_text("The target price must be greater than zero.")
        return

    await message.reply_text(f"Alert set for {ticker} at ${format_target(target)}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("update %r caused an error", update, exc_info=context.error)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Export it first:\n"
            "  export TELEGRAM_BOT_TOKEN='123456:ABC...'"
        )

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("alert", alert_command))
    application.add_error_handler(error_handler)

    logger.info("bot starting, polling for updates")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
