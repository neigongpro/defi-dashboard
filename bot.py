"""
DeFi Yield Advisor — Telegram Bot
Interactive inline-keyboard UI, natural language search, scheduled alerts.
"""

import os
import json
import time
import threading
import telebot
from telebot import types
import schedule
from dotenv import load_dotenv

from defi_engine import search_pools, fetch_pools, fmt_tvl, fmt_project, load_config
from ai_handler import parse_query, format_results, answer_question, generate_rebalance_advice
from data.snapshot_worker import fetch_and_store_snapshots
from data.rollup_worker import run_rollup_job
from data.metrics_engine import get_enriched_pools, get_market_overview
from advisor.rebalance_advisor import evaluate_rebalance

load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))

DB_FILE = "database.json"
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8000")

# ──────────────────────────────────────────────
#  USER DATABASE
# ──────────────────────────────────────────────

def _load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def _save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def get_prefs(chat_id):
    db = _load_db()
    uid = str(chat_id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "fav_assets": ["USDC", "USDT"],
            "excluded_chains": ["Tron"],
            "min_tvl": 1_000_000,
            "alert_apy": 0.0,
            "position": {"asset": "USDT", "amount": 10000, "protocol": "aave-v3", "chain": "Ethereum", "apy": 4.2}
        }
        _save_db(db)
    return db["users"][uid]

def set_pref(chat_id, key, value):
    db = _load_db()
    uid = str(chat_id)
    if uid not in db["users"]:
        get_prefs(chat_id)
        db = _load_db()
    db["users"][uid][key] = value
    _save_db(db)

# ──────────────────────────────────────────────
#  INLINE KEYBOARDS
# ──────────────────────────────────────────────

def main_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📊 Открыть Web-Дашборд", url=DASHBOARD_URL),
        types.InlineKeyboardButton("🤖 AI Ребалансер", callback_data="rebalance:menu"),
    )
    kb.add(
        types.InlineKeyboardButton("🏆 Топ-5 Real Yield", callback_data="top:real_yield"),
        types.InlineKeyboardButton("💎 Стейкинг ETH", callback_data="q:yield:ETH"),
    )
    kb.add(
        types.InlineKeyboardButton("🏦 Лендинги USDC", callback_data="q:lending:USDC"),
        types.InlineKeyboardButton("🏦 Лендинги USDT", callback_data="q:lending:USDT"),
        types.InlineKeyboardButton("📊 DEX пулы USDC", callback_data="q:dex:USDC"),
        types.InlineKeyboardButton("📊 DEX пулы USDT", callback_data="q:dex:USDT"),
    )
    kb.add(
        types.InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
        types.InlineKeyboardButton("🗑 Очистить чат", callback_data="clear"),
    )
    return kb

def after_results_kb(category, asset):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("🔄 Обновить", callback_data=f"q:{category}:{asset}"),
        types.InlineKeyboardButton("🏠 Меню", callback_data="menu"),
        types.InlineKeyboardButton("📊 Дашборд", url=DASHBOARD_URL),
    )
    if category == "lending":
        kb.add(types.InlineKeyboardButton(f"📊 DEX пулы {asset}", callback_data=f"q:dex:{asset}"))
    elif category == "dex":
        kb.add(types.InlineKeyboardButton(f"🏦 Лендинги {asset}", callback_data=f"q:lending:{asset}"))
    return kb

# ──────────────────────────────────────────────
#  SEARCH HELPER
# ──────────────────────────────────────────────

def do_search(chat_id, query: dict, reply_to_msg=None):
    """Execute search, format and send results."""
    prefs = get_prefs(chat_id)

    if not query.get("excluded_chains"):
        query["excluded_chains"] = prefs.get("excluded_chains", [])
    if not query.get("min_tvl"):
        query["min_tvl"] = prefs.get("min_tvl", 1_000_000)

    results = search_pools(query)
    text = format_results(results, query)

    category = query.get("category", "lending") or "lending"
    asset = query.get("assets", ["USDC"])[0] if query.get("assets") else "USDC"
    kb = after_results_kb(category, asset)

    if reply_to_msg:
        bot.reply_to(reply_to_msg, text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    else:
        bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

# ──────────────────────────────────────────────
#  COMMAND HANDLERS
# ──────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    text = (
        "🚀 <b>DeFi Tier-1 Yield & Rebalance Advisor</b>\n\n"
        "Я отслеживаю доходность ведущих протоколов прямо из ончейн-данных и помогаю выгодно перекладывать активы.\n\n"
        "✨ <b>Возможности:</b>\n"
        "• 📊 <b>Web-Дашборд</b> — живые графики 7d/30d и сравнение\n"
        "• 🤖 <b>AI Ребалансер</b> — расчет окупаемости газа и совет ИИ\n"
        "• 🏆 <b>Real Yield</b> — только органический доход без мусорных токенов\n\n"
        "Используй кнопки ниже или напиши запрос (напр. <i>'где лучше хранить 10000 USDT'</i>):"
    )
    bot.send_message(msg.chat.id, text, reply_markup=main_menu_kb(), parse_mode="HTML")

@bot.message_handler(commands=["dashboard"])
def cmd_dashboard(msg):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📊 Открыть Web-Дашборд", url=DASHBOARD_URL))
    bot.send_message(
        msg.chat.id,
        "📊 <b>Интерактивный Web-Дашборд DeFi Tier-1:</b>\n\n"
        "• Графики доходности за 7 и 30 дней\n"
        "• Сравнение Real Yield vs Инфляционные токены\n"
        "• Индекс стабильности ставки и детектор спайков",
        reply_markup=kb,
        parse_mode="HTML"
    )

@bot.message_handler(commands=["top"])
def cmd_top(msg):
    bot.send_chat_action(msg.chat.id, "typing")
    top_stables = get_enriched_pools(assets=["USDC", "USDT", "DAI"], category="lending", limit=5)

    lines = ["🏆 <b>ТОП-5 Безопасных Лендингов (Real Yield):</b>\n"]
    for i, p in enumerate(top_stables, 1):
        lines.append(
            f"{i}. <b>{p['project'].capitalize()}</b> ({p['chain']}) — <code>{p['symbol']}</code>\n"
            f"   ⚡ APY: <b>{p['apy']}%</b> (Base: {p['apy_base']}%) | TVL: ${p['tvl_usd']:,.0f}\n"
            f"   🛡 Безопасность: <b>{p['safety_grade']}</b> | Стабильность: {p['stability_score']}\n"
        )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤖 Оценить ребаланс", callback_data="rebalance:menu"))
    kb.add(types.InlineKeyboardButton("📊 Открыть в Дашборде", url=DASHBOARD_URL))
    bot.send_message(msg.chat.id, "\n".join(lines), reply_markup=kb, parse_mode="HTML")

@bot.message_handler(commands=["rebalance"])
def cmd_rebalance(msg):
    prefs = get_prefs(msg.chat.id)
    pos = prefs.get("position", {"asset": "USDT", "amount": 10000, "protocol": "aave-v3", "chain": "Ethereum", "apy": 4.2})

    bot.send_chat_action(msg.chat.id, "typing")
    eval_res = evaluate_rebalance(
        asset=pos["asset"],
        amount_usd=pos["amount"],
        current_protocol=pos["protocol"],
        current_chain=pos["chain"],
        current_apy=pos["apy"]
    )
    advice = generate_rebalance_advice(eval_res)

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📊 Дашборд", url=f"{DASHBOARD_URL}/advisor"),
        types.InlineKeyboardButton("🏠 Меню", callback_data="menu"),
    )
    bot.send_message(msg.chat.id, advice, reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(commands=["help"])
def cmd_help(msg):
    text = (
        "💡 <b>Как пользоваться ботом:</b>\n\n"
        "1. <b>/dashboard</b> — ссылка на интерактивный веб-дашборд\n"
        "2. <b>/top</b> — топ безопасных доходностей прямо сейчас\n"
        "3. <b>/rebalance</b> — персональный расчет перекладки средств\n"
        "4. <b>/settings</b> — настройки фильтров и минимального TVL\n\n"
        "Или просто напиши текстом:\n"
        "• <i>'лендинги USDT на Base'</i>\n"
        "• <i>'у меня 15000 USDC в Aave, куда переложить?'</i>\n"
        "• <i>'мой APY 5.5%'</i>"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML")

@bot.message_handler(commands=["settings"])
def cmd_settings(msg):
    prefs = get_prefs(msg.chat.id)
    assets = ", ".join(prefs.get("fav_assets", []))
    excl = ", ".join(prefs.get("excluded_chains", []))
    tvl = fmt_tvl(prefs.get("min_tvl", 0))
    apy = prefs.get("alert_apy", 0)
    text = (
        "⚙️ <b>Твои настройки:</b>\n\n"
        f"Активы: {assets or 'Все'}\n"
        f"Исключенные сети: {excl or 'Нет'}\n"
        f"Мин. TVL: {tvl}\n"
        f"Порог алерта APY: {apy}%\n\n"
        "Чтобы изменить, напиши:\n"
        "  <code>мой APY 5%</code> — установить текущую доходность\n"
        "  <code>исключи Tron</code> — добавить сеть в исключения\n"
    )
    bot.send_message(msg.chat.id, text, reply_markup=main_menu_kb(), parse_mode="HTML")

# ──────────────────────────────────────────────
#  CALLBACK (BUTTON) HANDLER
# ──────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    chat_id = call.message.chat.id

    if data == "menu":
        bot.edit_message_text(
            "🚀 Главное меню — выбери действие:",
            chat_id,
            call.message.message_id,
            reply_markup=main_menu_kb(),
        )

    elif data == "top:real_yield":
        bot.answer_callback_query(call.id, "Загружаю топ...")
        cmd_top(call.message)

    elif data == "rebalance:menu":
        bot.answer_callback_query(call.id, "Анализирую позицию...")
        cmd_rebalance(call.message)

    elif data == "clear":
        bot.answer_callback_query(call.id, "Очищаю чат...")
        msg_id = call.message.message_id
        for i in range(msg_id, max(msg_id - 100, 0), -1):
            try:
                bot.delete_message(chat_id, i)
            except Exception:
                pass
        bot.send_message(chat_id, "🧹 Чат очищен!", reply_markup=main_menu_kb())

    elif data == "help":
        bot.answer_callback_query(call.id)
        cmd_help(call.message)

    elif data == "settings":
        bot.answer_callback_query(call.id)
        cmd_settings(call.message)

    elif data.startswith("q:"):
        parts = data.split(":")
        category = parts[1] if len(parts) > 1 else "lending"
        asset = parts[2] if len(parts) > 2 else "USDC"

        bot.answer_callback_query(call.id, f"Ищу {category} {asset}...")
        bot.send_chat_action(chat_id, "typing")

        query = {"category": category, "assets": [asset]}
        do_search(chat_id, query)

    else:
        bot.answer_callback_query(call.id, "Неизвестная команда")

# ──────────────────────────────────────────────
#  NATURAL LANGUAGE HANDLER
# ──────────────────────────────────────────────

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    text = msg.text.strip()
    bot.send_chat_action(msg.chat.id, "typing")

    # Rebalance query detection (e.g. "куда переложить 10000 usdt")
    import re
    rebal_match = re.search(r'(?:переложить|перенести|куда положить|оптимизировать|ребаланс)\D*(\d+)?\s*(usdt|usdc|dai|eth|btc)?', text.lower())
    if rebal_match and ("куда" in text.lower() or "пере" in text.lower()):
        amount = float(rebal_match.group(1)) if rebal_match.group(1) else 10000.0
        asset = (rebal_match.group(2) or "USDT").upper()
        eval_res = evaluate_rebalance(
            asset=asset,
            amount_usd=amount,
            current_protocol="aave-v3",
            current_chain="Ethereum",
            current_apy=4.0
        )
        advice = generate_rebalance_advice(eval_res)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📊 Открыть Дашборд", url=f"{DASHBOARD_URL}/advisor"))
        bot.reply_to(msg, advice, reply_markup=kb, parse_mode="Markdown")
        return

    # Quick APY update detection
    apy_match = re.search(r'(?:мой|текущ|сейчас|получаю|зарабатываю)\D*(\d+(?:[.,]\d+)?)\s*%', text.lower())
    if apy_match:
        apy_val = float(apy_match.group(1).replace(",", "."))
        set_pref(msg.chat.id, "alert_apy", apy_val)
        bot.reply_to(msg, f"Записал! Твой текущий APY: {apy_val}%\nБуду искать варианты выше этой ставки.")
        return

    # Parse the query
    query = parse_query(text)

    if query.get("type") == "question":
        answer = answer_question(text)
        bot.reply_to(msg, answer)
        return

    # It's a search query
    do_search(msg.chat.id, query, reply_to_msg=msg)

# ──────────────────────────────────────────────
#  SCHEDULED 15-MIN INGESTION & SMART ALERTS
# ──────────────────────────────────────────────

def job_periodic_sync():
    """Runs every 15 minutes: captures live snapshot."""
    try:
        print("[Scheduler] Running 15-min Tier-1 on-chain snapshot...")
        fetch_and_store_snapshots()
    except Exception as e:
        print(f"[Scheduler] Ingestion error: {e}")

def job_smart_alerts():
    """Checks for significant rebalance opportunities for registered users."""
    print("[Scheduler] Running smart alert scan...")
    db = _load_db()
    for uid, prefs in db.get("users", {}).items():
        alert_apy = prefs.get("alert_apy", 0)
        if alert_apy <= 0:
            continue
        assets = prefs.get("fav_assets", ["USDC", "USDT"])
        for asset in assets:
            eval_res = evaluate_rebalance(
                asset=asset,
                amount_usd=10000.0,
                current_protocol="aave-v3",
                current_chain="Ethereum",
                current_apy=alert_apy
            )
            if eval_res["verdict"] == "STRONG_MOVE" and eval_res.get("best_alternative"):
                best = eval_res["best_alternative"]
                text = (
                    f"🔔 <b>Найдена выгодная возможность перекладки {asset}!</b>\n\n"
                    f"Вместо ваших {alert_apy}%:\n"
                    f"👉 <b>{best['project'].capitalize()}</b> ({best['chain']}) даёт <b>{best['apy']}%</b> APY\n"
                    f"• Чистая выгода: <b>+{best['apy_diff']}% годовых</b>\n"
                    f"• Окупаемость газа: <b>{best['break_even_days']} дней</b>\n"
                    f"• Дополнительно: <b>+${best['yearly_extra_usd']:,.0f}/год</b>\n\n"
                    f"<i>Оценка надёжности: {best['safety_grade']} · TVL ${best['tvl_usd']:,.0f}</i>"
                )
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("📊 Подробнее в Дашборде", url=f"{DASHBOARD_URL}/advisor"))
                try:
                    bot.send_message(int(uid), text, reply_markup=kb, parse_mode="HTML")
                except Exception as e:
                    print(f"[Alert] Failed to notify {uid}: {e}")

def run_scheduler():
    # 1. 15-min on-chain snapshot
    schedule.every(15).minutes.do(job_periodic_sync)
    # 2. 6-hour alert check
    schedule.every(6).hours.do(job_smart_alerts)
    # 3. Daily 3 AM rollup cleanup
    schedule.every().day.at("03:00").do(run_rollup_job)

    while True:
        schedule.run_pending()
        time.sleep(30)

# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("DeFi Advisor Bot & Ingestion Engine starting...")
    # Initial data snapshot
    fetch_and_store_snapshots()

    # Start background scheduler thread
    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()

    # Start bot polling
    print("Bot is ready and listening for updates!")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
