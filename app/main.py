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


def log(message):
    print(message, flush=True)


async def cycle(dry_run=False):
    wl = watchlist()
    log(f"WATCHLIST: {len(wl)} tickerlar")
    log(f"LOOKBACK: {NEWS_LOOKBACK_MINUTES} daqiqa")

    providers = [AlpacaNewsProvider(), SECProvider()]
    if MACRO_RSS_URLS:
        providers.append(RSSProvider(MACRO_RSS_URLS))

    all_items = []

    try:
        alpaca_items = await providers[0].fetch(
            None,
            since_minutes=NEWS_LOOKBACK_MINUTES,
        )
        log(f"ALPACA NEWS: {len(alpaca_items)}")
        if alpaca_items:
            log(f"ALPACA TOP: {alpaca_items[0].title[:160]}")
        all_items += alpaca_items
    except Exception as e:
        log(f"ALPACA ERROR: {type(e).__name__}: {e}")

    try:
        sec_items = await providers[1].fetch()
        log(f"SEC NEWS: {len(sec_items)}")
        all_items += sec_items
    except Exception as e:
        log(f"SEC ERROR: {type(e).__name__}: {e}")

    if len(providers) > 2:
        try:
            rss_items = await providers[2].fetch()
            log(f"RSS NEWS: {len(rss_items)}")
            all_items += rss_items
        except Exception as e:
            log(f"RSS ERROR: {type(e).__name__}: {e}")

    log(f"ALL NEWS: {len(all_items)}")
    all_items.sort(key=lambda x: x.published_at, reverse=True)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=NEWS_LOOKBACK_MINUTES + 5)

    state = load_state()
    published_ids = set(state["published_ids"])
    log(f"PUBLISHED IDS: {len(published_ids)}")

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

    log(f"CANDIDATES: {len(candidates)}")
    if candidates:
        for i, item in enumerate(candidates[:5], 1):
            log(f"CANDIDATE {i}: {item.title[:140]}")

    if not candidates:
        log("Yangi yangilik yo'q.")
        return

    try:
        results = await analyze_batch(candidates, wl)
        log(f"AI RESULTS: {len(results)}")
    except Exception as e:
        log(f"AI ERROR: {type(e).__name__}: {e}")
        return

    by_id = {str(x.get("source_id")): x for x in results}
    changed = False
    sent_count = 0
    publish_count = 0

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

        if publish:
            publish_count += 1
        else:
            log(
                f"SKIP: score={score} direction={direction} "
                f"publish={result.get('publish')} title={item.title[:100]}"
            )
            continue

        text = render(item, result)
        if dry_run:
            log("\n--- DRY RUN ---\n" + text)
        else:
            try:
                await send(text)
                sent_count += 1
                log("SENT: " + str(result.get("title_uz") or item.title))
            except Exception as e:
                log(f"TELEGRAM ERROR: {type(e).__name__}: {e}")
                continue

        published_ids.add(item.source_id)
        changed = True

    log(f"PUBLISHABLE: {publish_count}")
    log(f"SENT COUNT: {sent_count}")

    if changed and not dry_run:
        state["published_ids"] = list(published_ids)[-1000:]
        save_state(state)
        log("STATE: saved")
    else:
        log("STATE: no changes")


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
            log(f"CYCLE ERROR: {type(e).__name__}: {e}")
        await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
