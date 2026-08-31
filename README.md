# DeFi Tier-1 Yield & Rebalance Dashboard

🚀 **Live Production:** [https://defi.shtark.top](https://defi.shtark.top)  
🤖 **Telegram Bot:** Integrated DeFi Advisor with Smart Rebalancing & Instant Alerts  
📊 **Infrastructure:** AWS Singapore, Docker, FastAPI, Let's Encrypt HTTPS

---

## 💎 Features
- **100% Free On-Chain Data:** 15-minute background ingestion across Top-10 Tier-1 protocols (*Aave v3, Morpho Blue, Compound v3, Spark, Fluid, Lido, Uniswap v3, Curve, Pendle, Aerodrome*).
- **Zero-Maintenance SQLite Storage:** Rollup engine downsamples data older than 30 days, keeping DB footprint capped at ~50–70 MB.
- **Advanced Metrics:** Real Yield Ratio (Base APY vs Reward APY), 30d/7d Moving Averages, APY Stability Score, and Spike Detection.
- **AI Rebalance Advisor:** Calculates gas break-even timeframes and delivers personalized verdicts (*HOLD, STRONG_MOVE, CONSIDER*) powered by Gemini 2.5.
- **Interactive UI:** Dark mode responsive dashboard with Lucide icons, Chart.js time-series graphs, and real-time filtering.

---

## 🛠 Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run Web Dashboard
python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload

# Run Automated Test Suite
python3 -m pytest tests/ -v
```

---

## 🚀 Docker Deployment

```bash
docker build -t defi-dashboard .
docker run -d --name defi-dashboard --restart always -p 3000:80 \
  -e TELEGRAM_TOKEN=your_token \
  -e GEMINI_API_KEY=your_key \
  -e DASHBOARD_URL=https://defi.shtark.top \
  defi-dashboard
```
