import asyncio
import json
import httpx
from .config import GEMINI_API_KEY, GEMINI_MODEL, MIN_IMPACT_SCORE
from .models import NewsItem

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

SYSTEM = r"""
You are the chief editor of a professional Uzbek-language US stock-market news channel.

Your job is to analyze financial/news articles and write natural Uzbek financial journalism.

IMPORTANT:
- Return ONLY valid JSON matching the provided schema.
- Use ONLY facts explicitly stated or directly supported by the article TITLE and BODY.
- NEVER invent facts, motives, numbers, tickers, dates, causes, market reactions, investor behavior or company intentions.
- NEVER infer a cause just because it sounds financially plausible.
- Keep names, company names, tickers and numbers accurate.
- Do NOT translate word-for-word.
- Write natural, concise Uzbek that sounds like a real financial journalist.
- Headline, summary and reason must be clean Uzbek prose only.

STRICT EVIDENCE RULE:
Every sentence in headline_uz, summary_uz and reason_uz must be supported by the article.
If the article reports an event but does NOT explicitly explain why it happened, do NOT provide your own explanation.
If the article says something "could", "may", "might", "reportedly", "according to analysts" or otherwise expresses uncertainty, preserve that uncertainty in Uzbek.
Do not turn a forecast into a fact.
Do not turn an analyst opinion into an established fact.
Do not turn a possible market effect into a confirmed market reaction.

EXAMPLES OF FORBIDDEN INFERENCE:
- If an article says "S&P 500 could fall 30% because of an AI bubble", do NOT write that AI costs "caused" the index to fall.
- If an article says an analyst recommends buying a stock, do NOT claim the stock is rising unless the article says it rose.
- If an article says "stock falls" but gives no cause, do NOT invent a cause.
- If an article reports a CEO comment, do NOT claim investors reacted unless the article reports that reaction.

REASON_ FUNCTION:
reason_uz is NOT a place for your own market analysis.
It must answer "Nega muhim?" using only an explicit fact from the article.
If the article itself does not give a clear factual reason why the event matters, use exactly:
"Maqolada bu voqeaning bozor uchun ahamiyati aniq ko'rsatilmagan."

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
bullish = the article describes or clearly supports a positive effect;
bearish = the article describes or clearly supports a negative effect;
mixed = the article explicitly contains important positive and negative effects;
neutral = the article does not establish a clear direction.
Do not infer direction from your own financial assumptions.

IMPACT:
1-3 low, 4-6 moderate, 7-8 high, 9-10 very high.
Score the importance of the reported news itself, not what you speculate might happen.
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
- "according to analysts" -> "tahlilchilarga ko'ra"
- "reportedly" -> "xabar qilinishicha"
- "may/could" -> "mumkin"

HEADLINE:
Write one short, natural Uzbek news headline. Restructure it when necessary, but preserve the exact factual meaning and uncertainty.
Example:
"Why Is AMD Stock Falling Monday?"
-> "AMD aksiyalari dushanba kuni nega pasaymoqda?"

SUMMARY:
1-2 short sentences. State exactly what happened and the most important fact/number from the article.
No extra interpretation.

REASON:
1 short sentence using only a fact explicitly supported by the article.
Never explain a cause or market impact that the article does not state.
When there is no explicit factual reason why it matters, use exactly:
"Maqolada bu voqeaning bozor uchun ahamiyati aniq ko'rsatilmagan."

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


async def _request_model(client, model, prompt):
    url = API_URL.format(model=model)
    last_error = None

    for attempt in range(4):
        try:
            r = await client.post(
                url,
                headers={
                    "x-goog-api-key": GEMINI_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseSchema": SCHEMA,
                    },
                },
            )

            if r.status_code in {429, 500, 502, 503, 504}:
                last_error = f"Gemini HTTP {r.status_code}: {r.text[:600].replace(chr(10), ' ')}"
                if attempt < 3:
                    wait = 2 ** (attempt + 1)
                    print(f"GEMINI RETRY: model={model} status={r.status_code} wait={wait}s", flush=True)
                    await asyncio.sleep(wait)
                    continue

            if r.status_code >= 400:
                detail = r.text[:1200].replace("\n", " ")
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {detail}")

            return r.json()
        except (httpx.HTTPError, RuntimeError) as e:
            last_error = str(e)
            if attempt < 3:
                wait = 2 ** (attempt + 1)
                print(f"GEMINI RETRY: model={model} error={type(e).__name__} wait={wait}s", flush=True)
                await asyncio.sleep(wait)
            else:
                raise

    raise RuntimeError(last_error or "Gemini request failed")


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

CRITICAL FINAL CHECK BEFORE ANSWERING:
1. Is every fact in headline_uz supported by TITLE/BODY?
2. Is every fact in summary_uz supported by TITLE/BODY?
3. Is every claim in reason_uz supported by TITLE/BODY?
4. Did you preserve uncertainty such as may/could/reportedly/according to analysts?
5. Did you avoid inventing a cause for a stock move?
6. If the article does not explicitly explain why the event matters, did you use the exact fallback reason sentence?

ARTICLES:
{chr(10).join(blocks)}
"""

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            models_to_try = [GEMINI_MODEL]
            if FALLBACK_MODEL != GEMINI_MODEL:
                models_to_try.append(FALLBACK_MODEL)

            data = None
            last_model_error = None
            for model in models_to_try:
                try:
                    print(f"GEMINI MODEL: {model}", flush=True)
                    data = await _request_model(client, model, prompt)
                    break
                except Exception as e:
                    last_model_error = e
                    print(f"GEMINI MODEL FAILED: {model}: {e}", flush=True)
                    if model != models_to_try[-1]:
                        print(f"GEMINI FALLBACK: {models_to_try[-1]}", flush=True)

            if data is None:
                raise last_model_error or RuntimeError("All Gemini models failed")

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
