"""
AI Handler — Gemini integration for natural-language parsing and responses.
Two-layer parsing: AI first, keyword fallback if AI fails.
Uses the new google-genai SDK.
"""

import os
import json
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash"

# ──────────────────────────────────────────────
#  KEYWORD FALLBACK PARSER  (works without AI)
# ──────────────────────────────────────────────

_ASSET_LIST = ["USDT", "USDC", "ETH", "BTC", "DAI", "WETH", "WBTC",
               "SOL", "AVAX", "MATIC", "ARB", "OP", "SUI", "APT"]

_CHAIN_MAP = {
    "ethereum": "Ethereum", "эфириум": "Ethereum", "эфир": "Ethereum",
    "arbitrum": "Arbitrum", "optimism": "Optimism",
    "avalanche": "Avalanche", "avax": "Avalanche",
    "polygon": "Polygon", "matic": "Polygon",
    "bsc": "BSC", "binance": "BSC", "bnb": "BSC",
    "base": "Base", "solana": "Solana",
    "sui": "Sui", "aptos": "Aptos", "fantom": "Fantom",
    "gnosis": "Gnosis", "linea": "Linea", "scroll": "Scroll",
    "zksync": "zkSync Era", "mantle": "Mantle",
}

_PROTOCOL_MAP = {
    "aave": "aave", "compound": "compound", "morpho": "morpho",
    "spark": "spark", "venus": "venus", "benqi": "benqi",
    "radiant": "radiant", "silo": "silo", "euler": "euler",
    "moonwell": "moonwell", "fluid": "fluid", "zerolend": "zerolend",
    "curve": "curve", "uniswap": "uniswap", "sushi": "sushi",
    "balancer": "balancer", "camelot": "camelot", "aerodrome": "aerodrome",
    "velodrome": "velodrome", "pancakeswap": "pancakeswap",
    "pendle": "pendle", "lido": "lido", "eigenlayer": "eigenlayer",
    "stargate": "stargate", "beefy": "beefy", "convex": "convex",
}

_LENDING_WORDS = ["лендинг", "lending", "supply", "депозит", "вклад", "кредит"]
_DEX_WORDS = ["dex", "пул", "ликвидност", "lp ", "swap", "обмен"]
_YIELD_WORDS = ["стейкинг", "staking", "yield", "фарминг", "farming"]
_EXCLUDE_MARKERS = ["кроме", "без ", "исключ", "except", "exclude", "не включ"]

_QUESTION_WORDS = ["что такое", "как работает", "зачем", "почему",
                    "что значит", "объясни", "расскажи"]


def _keyword_parse(text: str) -> dict:
    """Robust keyword-based parser. No AI needed."""
    low = text.lower()
    q = {
        "type": "search",
        "assets": [],
        "chains": [],
        "excluded_chains": [],
        "protocols": [],
        "category": None,
        "min_tvl": 1_000_000,
        "min_apy": 0.0,
    }

    # --- detect general question ---
    if any(w in low for w in _QUESTION_WORDS):
        q["type"] = "question"
        return q

    # --- detect assets ---
    for asset in _ASSET_LIST:
        if re.search(rf'\b{asset}\b', text, re.IGNORECASE):
            q["assets"].append(asset)

    # --- detect category ---
    for w in _LENDING_WORDS:
        if w in low:
            q["category"] = "lending"
            break
    if not q["category"]:
        for w in _DEX_WORDS:
            if w in low:
                q["category"] = "dex"
                break
    if not q["category"]:
        for w in _YIELD_WORDS:
            if w in low:
                q["category"] = "yield"
                break

    # --- detect excluded vs included chains ---
    has_exclude = any(m in low for m in _EXCLUDE_MARKERS)
    for key, val in _CHAIN_MAP.items():
        # For Cyrillic keys, don't use trailing \b (Russian word forms: эфириума, эфире…)
        has_cyrillic = bool(re.search(r'[а-яё]', key))
        pattern = rf'\b{re.escape(key)}' if has_cyrillic else rf'\b{re.escape(key)}\b'
        if re.search(pattern, low):
            if has_exclude:
                if val not in q["excluded_chains"]:
                    q["excluded_chains"].append(val)
            else:
                if val not in q["chains"]:
                    q["chains"].append(val)

    # --- detect protocols ---
    for key, val in _PROTOCOL_MAP.items():
        if re.search(rf'\b{re.escape(key)}\b', low):
            q["protocols"].append(val)

    # --- detect min_tvl ---
    tvl_match = re.search(r'(?:tvl|от)\s*(\d+)\s*(млн|миллион|m|М)', low)
    if tvl_match:
        q["min_tvl"] = int(tvl_match.group(1)) * 1_000_000

    return q

# ──────────────────────────────────────────────
#  AI PARSER  (primary, with keyword fallback)
# ──────────────────────────────────────────────

def parse_query(user_text: str) -> dict:
    """Parse user message into a structured search query."""
    # Always run keyword parser first as baseline
    fallback = _keyword_parse(user_text)

    prompt = f"""Parse this DeFi bot message into JSON. Message: "{user_text}"

Return ONLY valid JSON (no markdown, no explanation):
{{"type":"search","assets":[],"chains":[],"excluded_chains":[],"protocols":[],"category":null,"min_tvl":1000000,"min_apy":0.0}}

Rules:
- type: "search" for finding yields. "question" for general knowledge questions (что такое DeFi? как работает APY?)
- assets: coin tickers UPPERCASE (USDT, USDC, ETH, BTC, DAI)
- chains: blockchain names (Arbitrum, Optimism, Avalanche, Base, BSC, Polygon, Ethereum)
- excluded_chains: chains after "кроме"/"без"/"except"
- protocols: protocol names lowercase (aave, compound, morpho, spark)
- category: "lending" for лендинг/lending/supply/депозит. "dex" for DEX/пулы/LP. null if unspecified
- min_tvl: integer USD. Default 1000000"""

    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
        raw = resp.text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        if "type" in parsed:
            return parsed
    except Exception as e:
        print(f"[AI] Parse error: {e}")

    return fallback

# ──────────────────────────────────────────────
#  RESPONSE FORMATTING  (pure Python, no AI)
# ──────────────────────────────────────────────

def _defillama_url(project: str) -> str:
    """Build DefiLlama protocol page URL."""
    slug = project.lower().strip()
    return f"https://defillama.com/protocol/{slug}"


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_results(results: list, query: dict) -> str:
    """Format search results into beautiful HTML for Telegram."""
    from defi_engine import fmt_tvl, fmt_project

    if not results:
        parts = []
        if query.get("category"):
            cat_names = {"lending": "лендинг-протоколам", "dex": "DEX пулам", "yield": "yield протоколам"}
            parts.append(cat_names.get(query["category"], query["category"]))
        if query.get("assets"):
            parts.append(", ".join(query["assets"]))
        if query.get("chains"):
            parts.append("на " + ", ".join(query["chains"]))

        hint = " по " + " ".join(parts) if parts else ""
        return f"Ничего не найдено{hint}.\n\nПопробуй расширить поиск или изменить фильтры."

    # --- header ---
    cat_emoji = {"lending": "🏦", "dex": "📊", "yield": "🌾"}.get(query.get("category", ""), "🔍")
    cat_name = {"lending": "Лендинг", "dex": "DEX", "yield": "Yield"}.get(query.get("category", ""), "Результаты")
    header_parts = [f"{cat_emoji} <b>{_html_escape(cat_name)}</b>"]
    if query.get("assets"):
        header_parts.append(" | ".join(query["assets"]))
    header = " — ".join(header_parts)

    lines = [header, ""]

    for i, r in enumerate(results, 1):
        name = _html_escape(fmt_project(r["project"]))
        url = _defillama_url(r["project"])
        chain = _html_escape(r["chain"])
        symbol = _html_escape(r["symbol"])
        apy = r["apy"]
        tvl = fmt_tvl(r["tvl"])

        lines.append(f'{i}. <a href="{url}">{name}</a> · {chain}  TVL {tvl}')
        lines.append(f"   💎 {symbol}  ⚡ <b>{apy}%</b>")
        lines.append("")

    lines.append(f"<i>Найдено: {len(results)} · DefiLlama</i>")
    return "\n".join(lines)

# ──────────────────────────────────────────────
#  GENERAL QUESTION ANSWERING
# ──────────────────────────────────────────────

def answer_question(question: str) -> str:
    """Answer a general DeFi knowledge question via Gemini."""
    prompt = f"""Ответь кратко на вопрос про DeFi/крипто (3-5 предложений, на русском).
НЕ используй markdown (звездочки, решетки). Только простой текст.

Вопрос: {question}"""

    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
        text = resp.text
        # Strip any markdown that slipped through
        text = re.sub(r'[*#_`]', '', text)
        return text.strip()
    except Exception as e:
        print(f"[AI] Question error: {e}")
        return "Извини, не удалось получить ответ. Попробуй позже."


# ──────────────────────────────────────────────
#  AI REBALANCE ADVICE SYNTHESIZER
# ──────────────────────────────────────────────

def generate_rebalance_advice(eval_data: dict) -> str:
    """
    Synthesizes a friendly, professional financial assessment from algorithmic rebalance evaluation.
    """
    pos = eval_data["current_position"]
    verdict = eval_data["verdict"]
    best = eval_data.get("best_alternative")

    # Fallback template message
    fallback_text = (
        f"📊 **Анализ позиции:** {pos['amount_usd']:,.0f} {pos['asset']} в {pos['protocol']} ({pos['chain']})\n"
        f"Текущая ставка: {pos['current_apy']}%\n\n"
        f"🎯 **Вердикт:** {eval_data['verdict_summary']}\n"
    )
    if best and verdict in ("STRONG_MOVE", "CONSIDER"):
        fallback_text += (
            f"\n💡 **Лучшая альтернатива:** {best['project']} ({best['chain']})\n"
            f"• Ставка: {best['apy']}% (чистая выгода: +{best['apy_diff']}%)\n"
            f"• Комиссия перехода: ~${best['gas_cost_usd']}\n"
            f"• Окупаемость газа: {best['break_even_days']} дней\n"
            f"• Дополнительный доход: +${best['yearly_extra_usd']:,.0f}/год\n"
            f"• Оценка надёжности: {best['safety_grade']}"
        )

    prompt = f"""Ты — объективный DeFi риск-аналитик и советник по оптимизации доходности.
Сформулируй краткий, понятный и убедительный совет для пользователя (на русском языке, 4-6 предложений).

Данные позиции:
- Актив: {pos['amount_usd']:,.0f} {pos['asset']}
- Текущий протокол: {pos['protocol']} на сети {pos['chain']}
- Текущий APY: {pos['current_apy']}%
- Вердикт алгоритма: {verdict}
- Резюме алгоритма: {eval_data['verdict_summary']}
- Лучшая альтернатива: {json.dumps(best, ensure_ascii=False) if best else 'Нет лучшей альтернативы'}

Требования к ответу:
1. Объясни, выгодно ли перемещать деньги или лучше оставить на месте.
2. Обязательно упомяни комиссии за газ, срок окупаемости и риск/безопасность (Real Yield vs инфляционные токены).
3. Используй четкое форматирование со структурой."""

    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
        if resp.text:
            return resp.text.strip()
    except Exception as e:
        print(f"[AI] Rebalance advice generation error: {e}")

    return fallback_text
