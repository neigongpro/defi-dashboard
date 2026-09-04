"""
AI Handler — Gemini integration for natural-language parsing and responses.
Two-layer parsing: AI first, keyword fallback if AI fails.
Uses the new google-genai SDK.
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from google import genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY", "")
client = None

def get_client() -> Optional[genai.Client]:
    """Dynamically get or initialize the Gemini client from environment."""
    global client
    key = os.getenv("GEMINI_API_KEY", "") or API_KEY
    if not key:
        return None
    if client is None:
        try:
            client = genai.Client(api_key=key)
        except Exception as e:
            print(f"[AI] Gemini Client initialization warning: {e}")
            return None
    return client

# Try to initialize at startup if key exists
if API_KEY:
    get_client()

PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash"]

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

def _call_gemini(prompt: str) -> Optional[str]:
    """Invoke Gemini with automatic fallback between models."""
    cli = get_client()
    if not cli:
        return None
    models_to_try = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]
    for m in models_to_try:
        try:
            resp = cli.models.generate_content(model=m, contents=prompt)
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            print(f"[AI] Model {m} call error: {e}")
    return None


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
        raw_text = _call_gemini(prompt)
        if raw_text:
            cleaned = raw_text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned)
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
        raw_text = _call_gemini(prompt)
        if raw_text:
            # Strip any markdown that slipped through
            text = re.sub(r'[*#_`]', '', raw_text)
            return text.strip()
    except Exception as e:
        print(f"[AI] Question error: {e}")

    return "DeFi (децентрализованные финансы) — это финансовые сервисы на смарт-контрактах блокчейна без посредников. Доходность (APY) формируется за счет спроса на займы или комиссий с обменов ликвидности."


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
        advice = _call_gemini(prompt)
        if advice:
            return advice
    except Exception as e:
        print(f"[AI] Rebalance advice generation error: {e}")

    return fallback_text


# ──────────────────────────────────────────────
#  PORTFOLIO (Личный Кабинет) AI EVALUATION
# ──────────────────────────────────────────────

def generate_portfolio_advice(summary: dict, positions: list, market_overview: Optional[dict] = None) -> str:
    """
    Synthesizes a strategic allocation, yield-enhancement, and risk report for a user's entire capital portfolio.
    """
    if not positions:
        return "В вашем портфеле пока нет активных позиций. Добавьте ваши депозиты в панели выше, чтобы получить детальный аудит рисков и доходности от ИИ."

    total_cap = summary.get("total_capital", 0.0)
    w_apy = summary.get("weighted_apy", 0.0)
    m_inc = summary.get("monthly_income", 0.0)
    y_inc = summary.get("annual_income", 0.0)

    pos_summary_str = "\n".join([
        f"- {p['amount_usd']:,.0f} $ в {p['protocol']} ({p['chain']}), актив {p['asset']}, текущий APY: {p['current_apy']}%"
        for p in positions
    ])

    market_context_str = ""
    if market_overview:
        market_context_str = (
            f"Рыночный бенчмарк Tier-1:\n"
            f"- Средний APY стейблкоинов: {market_overview.get('avg_stable_apy', 'N/A')}%\n"
            f"- Средний APY ETH / LST: {market_overview.get('avg_eth_apy', 'N/A')}%\n"
            f"- Топ безопасный пул: {market_overview.get('top_safe_yield', {}).get('project', 'Aave')} "
            f"({market_overview.get('top_safe_yield', {}).get('apy', 'N/A')}%)\n"
        )

    prompt = f"""Ты — институциональный DeFi риск-менеджер и портфельный аналитик.
Проанализируй капитал пользователя и составь структурированный отчёт с практическими рекомендациями по увеличению пассивного дохода и снижению рисков.

Портфель пользователя:
- Общий капитал: ${total_cap:,.2f}
- Средневзвешенная ставка доходности: {w_apy}% APY
- Прогнозируемый пассивный доход: ${m_inc:,.2f} / мес (${y_inc:,.2f} / год)
- Количество позиций: {len(positions)}

Текущие распределения:
{pos_summary_str}

{market_context_str}

Требования к отчёту (на русском языке, профессионально, с Markdown):
1. 🎯 **Общая оценка портфеля**: качество диверсификации по протоколам, сетям и активам (есть ли перекосы или чрезмерная концентрация).
2. ⚡ **Анализ доходности**: насколько текущие {w_apy}% соответствуют рынку и есть ли спящий капитал (позиции с заниженным APY).
3. 🔄 **Конкретные рекомендации по ребалансировке**: какие именно позиции имеет смысл оптимизировать, куда переложить (Tier-1: Aave v3, Morpho, Compound, Spark, Fluid) и сколько это добавит к доходу с учетом окупаемости газа.
4. 🛡️ **Риск-профиль**: кредитное плечо / смарт-контрактный риск / риски депега или волатильности.
5. 📌 **План действий из 2-3 шагов**: что сделать прямо сейчас."""

    try:
        report = _call_gemini(prompt)
        if report:
            return report
    except Exception as e:
        print(f"[AI] Portfolio advice generation error: {e}")

    # Fallback algorithmic report
    underperforming = [p for p in positions if p.get("current_apy", 0) < 4.0]
    high_yield = [p for p in positions if p.get("current_apy", 0) >= 8.0]

    lines = [
        f"### 📊 Портфельный аудит (Алгоритмический расчёт)",
        f"",
        f"- **Общий капитал в работе:** ${total_cap:,.2f}",
        f"- **Средневзвешенная доходность:** **{w_apy:.2f}% APY**",
        f"- **Ожидаемый пассивный доход:** **+${m_inc:,.2f}/мес** (+${y_inc:,.2f}/год)",
        f"",
        f"#### 🎯 Статус диверсификации:",
        f"Портфель распределен по {len(positions)} позициям. "
    ]
    if len(positions) == 1:
        lines.append("⚠️ **Высокая концентрация:** 100% средств находится в одной позиции. Рекомендуется распределить риски минимум между 2-3 независимыми Tier-1 протоколами (Aave, Morpho, Spark).")
    else:
        lines.append(f"Хорошее базовое распределение по сетям и протоколам.")

    if underperforming:
        lines.append(f"\n#### ⚡ Позиции с низкой доходностью (< 4% APY):")
        for u in underperforming:
            lines.append(f"- **{u['protocol']} ({u['chain']})** — ${u['amount_usd']:,.0f} под {u['current_apy']}%. Рекомендуется рассмотреть перемещение в проверенные пулы Morpho или Spark для прироста +2-4% годовых.")

    if high_yield:
        lines.append(f"\n#### 🔥 Высокодоходные позиции (≥ 8% APY):")
        for h in high_yield:
            lines.append(f"- **{h['protocol']} ({h['chain']})** — {h['current_apy']}%. Обратите внимание на стабильность ставки и долю Reward APY (волатильные токены).")

    lines.append("\n#### 📌 Рекомендация:\nИспользуйте «AI Калькулятор Ребаланса» для каждой отдельной позиции, чтобы проверить окупаемость комиссии за газ перед транзакцией.")

    return "\n".join(lines)


def generate_curated_wallet_summary(
    address: str,
    label: str = "",
    strategy_type: str = "",
    chains: str = "",
    protocols: str = "",
    sample_positions: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Generate an informative, concise on-chain strategy analysis for a curated DeFi wallet
    using Google Gemini 3.8 / Flash with a specialized DeFi analyst prompt.
    """
    pos_desc = ""
    if sample_positions:
        pos_lines = [
            f"- {p.get('protocol', 'DeFi')} ({p.get('chain', 'EVM')}): {p.get('asset', 'Token')} "
            f"на ${p.get('amount_usd', 0):,.2f} под {p.get('current_apy', 0)}% APY"
            for p in sample_positions[:8]
        ]
        pos_desc = "Обнаруженные позиции:\n" + "\n".join(pos_lines)

    prompt = f"""Ты — институциональный DeFi-исследователь и ончейн-аналитик китов (Whale Tracker).
Составь лаконичный, информативный разбор стратегии интересного кошелька для базы знаний DeFi-инвесторов.

Параметры кошелька:
- Адрес: {address}
- Название / Метка: {label or 'DeFi Whale'}
- Заявленная стратегия: {strategy_type or 'On-Chain Yield Farming'}
- Основные сети: {chains or 'Multi-Chain'}
- Протоколы: {protocols or 'Uniswap v3, Revert, Aave, Curve'}
{pos_desc}

Требования к ответу (на русском языке, ёмко, структурированно, Markdown, без воды, не длиннее 4-5 предложений):
1. 🎯 **Суть стратегии**: как именно кошелек зарабатывает (узкие диапазоны концентрированной ликвидности LP v3, автокомпаундинг комиссий в Revert Finance, дельта-нейтральный хэдж, кредитование под залог).
2. ⚡ **Позиции и активы**: ключевые пары и концентрация капитала.
3. 🛡️ **Риск-профиль**: как управляет рисками (IL, ликвидация, смарт-контракты).
4. 💡 **Практический вывод**: чему обычный инвестор может научиться у этой позиции.
Пиши четко, профессионально и по делу."""

    try:
        summary = _call_gemini(prompt)
        if summary and len(summary.strip()) > 30:
            return summary.strip()
    except Exception as e:
        print(f"[AI] Curated wallet summary error: {e}")

    # High-signal algorithmic fallback
    strat_lower = (strategy_type + " " + label).lower()
    if "lp" in strat_lower or "concentrated" in strat_lower or "revert" in strat_lower:
        return (
            f"🎯 **Суть стратегии:** Активное управление концентрированной ликвидностью на Uniswap v3 и Revert Finance. "
            f"Фокусируется на сборе торговых комиссий в волатильных парах с частым ребалансом рабочего диапазона.\n"
            f"⚡ **Позиции:** Преобладают пары с нативными активами (ETH, WBTC) и ликвидными стейблкоинами (USDC, USDT).\n"
            f"🛡️ **Риск-профиль:** Умеренный — риск Impermanent Loss компенсируется высокой скоростью автокомпаунда комиссий (>25-40% APY).\n"
            f"💡 **Вывод:** Использование инструментов вроде Revert позволяет автоматизировать сбор комиссий и минимизировать простой капитала."
        )
    elif "supply" in strat_lower or "treasury" in strat_lower or "vitalik" in strat_lower:
        return (
            f"🎯 **Суть стратегии:** Консервативное удержание и лендинг в проверенных Tier-1 протоколах (Aave v3, Maker/Spark).\n"
            f"⚡ **Позиции:** Крупные депозиты нативного ETH и стейблкоинов без задействования рискованного плеча.\n"
            f"🛡️ **Риск-профиль:** Минимальный — нулевой риск ликвидации, фокус на смарт-контрактной надежности и защите капитала.\n"
            f"💡 **Вывод:** Образец институционального treasury management для сохранения и безинфляционного приумножения базового актива."
        )
    else:
        return (
            f"🎯 **Суть стратегии:** Мультичейн-арбитраж и поставка ликвидности в DEX пулы ({protocols or 'Uniswap, Curve'}).\n"
            f"⚡ **Позиции:** Диверсификация между основными L2 сетями ({chains or 'Arbitrum, Base, Optimism'}).\n"
            f"🛡️ **Риск-профиль:** Сбалансированный с контролем глубины стакана и стоимости газа.\n"
            f"💡 **Вывод:** Мониторинг подобных адресов дает сигналы о наиболее ликвидных пулах и трендах доходности."
        )

