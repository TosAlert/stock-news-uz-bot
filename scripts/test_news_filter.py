import asyncio
import json
import sys
from datetime import datetime, timezone

from app.ai import analyze_batch
from app.config import GEMINI_API_KEY
from app.models import NewsItem


CASES = [
    {
        "id": "test-market-recap",
        "expected_publish": False,
        "title": "Dow Jones slips 0.09% in quiet Wednesday trading",
        "body": (
            "U.S. stock indexes ended slightly lower in a quiet session. "
            "The Dow Jones Industrial Average fell 0.09%. The report identifies "
            "no new economic release, policy decision, company event, or other catalyst."
        ),
        "tickers": [],
    },
    {
        "id": "test-price-action",
        "expected_publish": False,
        "title": "Why Example Corp shares are moving today",
        "body": (
            "Shares moved 1.2% during the session. The article offers no new filing, "
            "company announcement, financial result, or independently verified catalyst."
        ),
        "tickers": ["EXM"],
    },
    {
        "id": "test-analyst-opinion",
        "expected_publish": False,
        "title": "Broker raises Example Corp price target",
        "body": (
            "A brokerage raised its price target from $100 to $105 while maintaining "
            "its rating. The article contains no new company facts, financial results, "
            "or other material event beyond the analyst's opinion."
        ),
        "tickers": ["EXM"],
    },
    {
        "id": "test-earnings",
        "expected_publish": True,
        "title": "Example Semiconductor reports quarterly results and cuts outlook",
        "body": (
            "Example Semiconductor reported quarterly revenue of $4.2 billion, below "
            "the $4.5 billion consensus estimate. The company also lowered its next-quarter "
            "revenue guidance to $3.6-$3.9 billion, compared with analysts' prior estimate "
            "of $4.4 billion. These figures and the updated guidance were in the company's "
            "earnings release published today."
        ),
        "tickers": ["EXS"],
    },
    {
        "id": "test-fda-event",
        "expected_publish": True,
        "title": "FDA approves Example Bio's new treatment",
        "body": (
            "The U.S. Food and Drug Administration approved Example Bio's treatment for "
            "the indication described in the company's official announcement today. "
            "The approval is a new regulatory decision. The article identifies the company "
            "and the approved treatment."
        ),
        "tickers": ["EXB"],
    },
]


async def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY is not configured.", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    items = [
        NewsItem(
            source="Professional News filter test fixture",
            source_id=case["id"],
            title=case["title"],
            url="https://example.invalid/test-fixture",
            published_at=now,
            body=case["body"],
            tickers=case["tickers"],
        )
        for case in CASES
    ]

    results = await analyze_batch(items, watchlist=[])
    by_id = {str(x.get("source_id")): x for x in results}
    failures = 0

    print("\n=== PROFESSIONAL NEWS FILTER TEST (no Telegram sending) ===")
    for case in CASES:
        result = by_id.get(case["id"])
        if not result:
            print(f"FAIL {case['id']}: AI returned no result")
            failures += 1
            continue

        actual = bool(result.get("publish")) and int(result.get("impact_score", 0) or 0) >= 7
        expected = case["expected_publish"]
        status = "PASS" if actual == expected else "REVIEW"
        if actual != expected:
            failures += 1

        print(json.dumps({
            "status": status,
            "case": case["id"],
            "expected_publish": expected,
            "ai_publish": bool(result.get("publish")),
            "impact_score": result.get("impact_score"),
            "actual_after_score_threshold": actual,
            "direction": result.get("direction"),
            "category": result.get("category"),
            "headline_uz": result.get("headline_uz"),
            "affected_tickers": result.get("affected_tickers"),
        }, ensure_ascii=False))

    print(f"\nRESULT: {len(CASES) - failures}/{len(CASES)} expected outcomes matched.")
    print("REVIEW means inspect the AI decision before merging; it does not send a Telegram post.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
