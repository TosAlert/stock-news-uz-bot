# Stock News UZ Bot — GitHub Actions + Gemini Free

24/7 news bot for Telegram:
Alpaca News + SEC + optional macro RSS -> Gemini 2.5 Flash -> natural Uzbek -> Telegram.

## Required GitHub Secrets

Create these repository secrets:
- GEMINI_API_KEY
- ALPACA_API_KEY
- ALPACA_API_SECRET
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHANNEL_ID

Never commit `.env` or API keys.

## How it runs

GitHub Actions runs the bot every 5 minutes and also supports manual runs.
The public-repository standard runner is used.

The bot fetches recent Alpaca news, today's SEC filings, and optional RSS.
Gemini analyzes several news items in one request to reduce request count.
Only published-news IDs are persisted in `data/state.json`.

## Local test

```bash
pip install -r requirements.txt
python -m app.main --once --dry-run
```

## Notes

- `GEMINI_MODEL=gemini-2.5-flash`
- `MIN_IMPACT_SCORE=4`
- Neutral but relevant market/company/index news may be published.
- The bot does not claim a cause that the source does not support.
