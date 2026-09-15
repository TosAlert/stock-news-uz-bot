import argparse
import asyncio
import json
from datetime import datetime, timezone, timedelta

from .config import (
    MIN_IMPACT_SCORE,
    MAX_AI_ITEMS_PER_RUN,
    NEWS_LOOKBACK_MINUTES,
    STATE_PATH,
    MACRO_RSS_URLS,
    watchlist,
)
from .ai import analyze_batch
from .telegram import render, send
from .providers.alpaca_news import AlpacaNewsProvider
from .providers.sec import SECProvider
from .providers.rss import RSSProvider


def load_state():
    if not STATE_PATH.exists():
        return {"published_ids": []}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        ids = data.get("published_ids", [])
        return {"published_ids": ids[-1000:]}
    except Exception:
        return {"published_ids": []}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["published_ids"] = state.get("published_ids", [])[-1000:]
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def cycle(dry_run=False):
    wl = watchlist()
    providers = [AlpacaNewsProvider(), SECProvider()]
    if MACRO_RSS_URLS:
        providers.append(RSSProvider(MACRO_RSS_URLS))

    all_items = []
    all_items += await providers[0].fetch(
        wl,
        since_minutes=NEWS_LOOKBACK_MINUTES,
    )
    all_items += await providers[1].fetch()
    if len(providers) > 2:
        all_items += await providers[2].fetch()

    all_items.sort(key=lambda x: x.published_at, reverse=True)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=NEWS_LOOKBACK_MINUTES + 5)

    state = load_state()
    published_ids = set(state["published_ids"])

    candidates = []
    local_seen = set()

    for item in all_items:
        if item.source_id in local_seen or item.source_id in published_ids:
            continue
        local_seen.add(item.source_id)

        published_at = item.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        if published_at < cutoff:
            continue

        candidates.append(item)
        if len(candidates) >= MAX_AI_ITEMS_PER_RUN:
            break

    if not candidates:
        print("Yangi yangilik yo'q.")
        return

    results = await analyze_batch(candidates, wl)
    by_id = {str(x.get("source_id")): x for x in results}

    changed = False

    for item in candidates:
        result = by_id.get(str(item.source_id))
        if not result:
            continue

        score = int(result.get("impact_score", 0) or 0)
        direction = str(result.get("direction", "neutral")).lower().strip()

        publish = (
            bool(result.get("publish"))
            and direction in {"bullish", "bearish", "mixed", "neutral"}
            and score >= MIN_IMPACT_SCORE
        )

        if not publish:
            continue

        text = render(item, result)
        if dry_run:
            print("\n--- DRY RUN ---\n" + text)
        else:
            try:
                await send(text)
                print("SENT:", result.get("headline_uz") or item.title)
            except Exception as e:
                print("TELEGRAM ERROR:", e)
                continue

        published_ids.add(item.source_id)
        changed = True

    if changed and not dry_run:
        state["published_ids"] = list(published_ids)[-1000:]
        save_state(state)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.once:
        await cycle(args.dry_run)
        return

    # Local fallback mode. GitHub Actions uses --once.
    while True:
        try:
            await cycle(args.dry_run)
        except Exception as e:
            print("CYCLE ERROR:", e)
        await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
