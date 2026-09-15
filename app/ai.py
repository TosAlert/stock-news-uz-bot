import json
import httpx
from .config import GEMINI_API_KEY, GEMINI_MODEL, MIN_IMPACT_SCORE
from .models import NewsItem

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM = r"""
You are the chief editor of a professional Uzbek-language US stock-market news channel.

Your job is to analyze financial/news articles and write natural Uzbek financial journalism.

IMPORTANT:
- Return ONLY valid JSON matching the provided schema.
- Do NOT invent facts, motives, numbers, tickers, dates, causes or market reactions.
- Keep names, company names, tickers and numbers accurate.
- Do NOT translate word-for-word.
- Write natural, concise Uzbek that sounds like a real financial journalist.
- Headline, summary and reason must be clean Uzbek prose only.

PUBLISH RULE:
Publish useful news about:
- individual stocks and companies;
- Nasdaq, S&P 500, Dow and the broad market;
- sectors;
- Fed/rates/CPI/PCE/jobs/GDP/Treasury yields;
- SEC/FTC/DOJ/FDA and other regulation;
- tariffs, sanctions, wars and geopolitics;
- important contracts, acquisitions, launches, recalls, supply disruptions;
- analyst actions or "why is stock falling/rising?" articles when they contain meaningful new information.

Reject only:
- spam;
- advertising;
- duplicate/recycled material;
- empty SEO content;
- content with essentially no factual news.

A neutral direction is allowed when the news itself is relevant.

DIRECTION:
bullish = likely positive pressure;
bearish = likely negative pressure;
mixed = important positive and negative effects;
neutral = no clear direction.

IMPACT:
1-3 low, 4-6 moderate, 7-8 high, 9-10 very high.
Do not give a high score merely because a headline sounds dramatic.

UZBEK STYLE:
- "shares fell" -> "aksiyalar pasaydi/tushdi"
- "shares rose" -> "aksiyalar ko'tarildi/o'sdi"
- "beat estimates" -> "kutilganidan yuqori natija qayd etdi"
- "missed estimates" -> "kutilganidan past natija qayd etdi"
- "guidance" -> "kompaniya prognozi"
- "revenue" -> "tushum"
- "stake" -> "ulush"
- "could weigh on the stock" -> "aksiya narxiga bosim qilishi mumkin"

HEADLINE:
Write one short, natural Uzbek news headline. Restructure it when necessary.
Example:
"Why Is AMD Stock Falling Monday?"
-> "AMD aksiyalari dushanba kuni nega pasaymoqda?"

SUMMARY:
1-2 short sentences. State what happened and the most important fact/number.
No extra interpretation.

REASON:
1 short sentence explaining why the event matters, but only from facts supported by the article.
If the article does not provide a clear reason:
"Maqolada aksiyalar harakatining aniq sababi ko'rsatilmagan."
Do not invent causal explanations.

CATEGORY must be one of:
stock, company, market, sector, macro, regulatory, geopolitical, analyst.

For each item, return source_id exactly as provided.
"""

SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "source_id": {"type": "string"},
            "publish": {"type": "boolean"},
            "direction": {
                "type": "string",
                "enum": ["bullish", "bearish", "mixed", "neutral"],
            },
            "impact_score": {"type": "integer"},
            "category": {
                "type": "string",
                "enum": [
                    "stock", "company", "market", "sector",
                    "macro", "regulatory", "geopolitical", "analyst"
                ],
            },
            "headline_uz": {"type": "string"},
            "summary_uz": {"type": "string"},
            "reason_uz": {"type": "string"},
        },
        "required": [
            "source_id", "publish", "direction", "impact_score",
            "category", "headline_uz", "summary_uz", "reason_uz"
        ],
    },
}

def _fallback(item: NewsItem, reason="AI tahlili bajarilmadi."):
    return {
        "source_id": item.source_id,
        "publish": False,
        "direction": "neutral",
        "impact_score": 0,
        "category": "company",
        "headline_uz": item.title,
        "summary_uz": "",
        "reason_uz": reason,
    }

async def analyze_batch(items: list[NewsItem], watchlist: list[str]) -> list[dict]:
    if not items:
        return []
    if not GEMINI_API_KEY:
        return [_fallback(x, "GEMINI_API_KEY sozlanmagan.") for x in items]

    blocks = []
    for i, item in enumerate(items, start=1):
        blocks.append(
            f"""ARTICLE {i}
SOURCE_ID: {item.source_id}
SOURCE: {item.source}
TITLE: {item.title}
PUBLISHED: {item.published_at.isoformat()}
TICKERS: {", ".join(item.tickers)}
WATCHLIST: {", ".join(watchlist)}

BODY:
{item.body[:7000]}
"""
        )

    prompt = f"""
Analyze all of the following articles independently.

Minimum publish impact score: {MIN_IMPACT_SCORE}

Return one JSON object for EACH ARTICLE.
Keep the exact SOURCE_ID.
Do not omit an article even if publish=false.

ARTICLES:
{chr(10).join(blocks)}
"""

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                API_URL.format(model=GEMINI_MODEL),
                headers={
                    "x-goog-api-key": GEMINI_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "responseMimeType": "application/json",
                        "responseSchema": SCHEMA,
                    },
                },
            )
            if r.status_code >= 400:
                detail = r.text[:1200].replace("\n", " ")
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {detail}")
            data = r.json()

        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
        result = json.loads(text)
        if not isinstance(result, list):
            raise ValueError("Gemini JSON array qaytarmadi.")

        by_id = {str(x.get("source_id")): x for x in result if isinstance(x, dict)}
        out = []
        for item in items:
            x = by_id.get(str(item.source_id))
            if not x:
                out.append(_fallback(item, "Gemini bu xabar uchun natija qaytarmadi."))
                continue
            score = max(0, min(10, int(x.get("impact_score", 0) or 0)))
            direction = str(x.get("direction", "neutral")).lower()
            if direction not in {"bullish", "bearish", "mixed", "neutral"}:
                direction = "neutral"
            category = str(x.get("category", "company")).lower()
            if category not in {
                "stock", "company", "market", "sector",
                "macro", "regulatory", "geopolitical", "analyst"
            }:
                category = "company"

            out.append({
                "source_id": item.source_id,
                "publish": bool(x.get("publish", False)),
                "direction": direction,
                "impact_score": score,
                "category": category,
                "headline_uz": str(x.get("headline_uz") or item.title).strip(),
                "summary_uz": str(x.get("summary_uz") or "").strip(),
                "reason_uz": str(x.get("reason_uz") or "").strip(),
            })
        return out
    except Exception as e:
        print(f"GEMINI ERROR: {e}", flush=True)
        return [_fallback(x, f"Gemini xatosi: {e}") for x in items]
