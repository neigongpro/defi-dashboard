"""
DeFi Engine — data layer for DefiLlama API.
Handles fetching, caching, categorisation and smart filtering of yield pools.
"""

import requests
import time
import json

# ──────────────────────────────────────────────
#  PROTOCOL CATEGORY MAPS  (canonical lowercase)
# ──────────────────────────────────────────────

LENDING_PROTOCOLS = {
    "aave-v3", "aave-v2", "aave",
    "compound-v3", "compound-v2", "compound",
    "morpho", "morpho-blue", "morpho-aave",
    "spark", "spark-lending", "spark-savings",
    "fluid", "fluid-lending",
    # Solana
    "kamino", "kamino-lend",
    # Sui
    "navi-lending", "navi-protocol", "scallop-lend", "scallop", "suilend",
    # Aptos
    "aries-markets", "echelon-market",
    # Frax
    "fraxlend",
    # Others
    "venus", "venus-core-pool",
    "benqi-lending", "benqi",
    "silo-v2", "silo-finance", "silo",
    "euler", "euler-v2",
    "ionic", "ionic-protocol",
    "seamless-protocol",
    "moonwell", "moonwell-artemis",
    "zerolend", "layerbank", "init-capital",
    "justlend", "cream", "iron-bank",
    "aave-v3-lido"
}

DEX_PROTOCOLS = {
    "uniswap-v3", "uniswap-v2", "uniswap", "uniswap-v4",
    "curve-dex", "curve-finance", "curve",
    "aerodrome", "aerodrome-v2", "aerodrome-slipstream",
    "velodrome", "velodrome-v2",
    "camelot", "camelot-v3",
    "pancakeswap-amm-v3", "pancakeswap-amm-v2", "pancakeswap",
    "sushiswap", "sushi",
    "trader-joe", "trader-joe-v2",
    "balancer-v2", "balancer",
    "ambient", "maverick-v2", "maverick",
    # Solana
    "raydium", "raydium-clmm", "orca", "lifinity",
    # Sui
    "cetus-clmm", "cetus", "bluefin-spot",
    # Aptos
    "thalaswap", "thala",
    # Frax / Sonic
    "frax-swap", "beets-dex-v3", "shadow-exchange", "thena", "ramses"
}

YIELD_PROTOCOLS = {
    "lido", "rocket-pool", "convex-finance", "yearn-finance", "beefy",
    "stargate", "stargate-v1", "pendle", "eigenlayer",
    # Solana LST
    "jito", "marinade-finance", "marinade",
    # Aptos LST
    "amnis-finance",
    # Frax & LRT
    "frax", "ethena", "ether.fi-stake", "ether.fi"
}

# ──────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────

def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except Exception:
        return {
            "default_min_tvl": 1_000_000,
            "default_excluded_chains": ["Tron"],
            "max_results": 10,
            "cache_ttl_seconds": 300,
            "max_apy_cap": 500,
        }

# ──────────────────────────────────────────────
#  POOL CACHE
# ──────────────────────────────────────────────

_cache = {"data": [], "ts": 0}


def fetch_pools():
    """Fetch all pools from DefiLlama with in-memory caching."""
    cfg = load_config()
    now = time.time()
    if _cache["data"] and (now - _cache["ts"]) < cfg.get("cache_ttl_seconds", 300):
        return _cache["data"]

    try:
        resp = requests.get("https://yields.llama.fi/pools", timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        _cache["data"] = data
        _cache["ts"] = now
        print(f"[DefiLlama] Loaded {len(data)} pools")
        return data
    except Exception as e:
        print(f"[DefiLlama] Error: {e}")
        return _cache["data"]  # stale cache is better than nothing

# ──────────────────────────────────────────────
#  VERIFIED STABLECOINS & PROTOCOL URLS
# ──────────────────────────────────────────────

VERIFIED_STABLECOINS = {
    "USDC", "USDT", "DAI", "USDS", "USDE", "PYUSD", "GHO",
    "FRAX", "FDUSD", "CRVUSD", "LUSD", "USD+", "DOLA", "SUSD", "TUSD", "USDTB"
}

PROTOCOL_APP_URLS = {
    "aave": "https://app.aave.com",
    "aave-v3": "https://app.aave.com",
    "aave-v2": "https://app.aave.com",
    "morpho": "https://app.morpho.org",
    "morpho-blue": "https://app.morpho.org",
    "compound": "https://app.compound.finance",
    "compound-v3": "https://app.compound.finance",
    "spark": "https://app.spark.fi",
    "sparklend": "https://app.spark.fi",
    "spark-savings": "https://app.spark.fi",
    "fluid": "https://fluid.io",
    "fluid-lending": "https://fluid.io",
    "fluid-dex": "https://fluid.io",
    "uniswap": "https://app.uniswap.org",
    "uniswap-v3": "https://app.uniswap.org",
    "curve": "https://curve.fi",
    "curve-dex": "https://curve.fi",
    "pendle": "https://app.pendle.finance",
    "aerodrome": "https://aerodrome.finance",
    "aerodrome-slipstream": "https://aerodrome.finance",
    "lido": "https://stake.lido.fi",
    # Solana
    "kamino": "https://app.kamino.finance",
    "kamino-lend": "https://app.kamino.finance",
    "raydium": "https://raydium.io",
    "raydium-clmm": "https://raydium.io",
    "orca": "https://www.orca.so",
    "jito": "https://www.jito.network",
    "marinade": "https://marinade.finance",
    "marinade-finance": "https://marinade.finance",
    # Sui
    "navi": "https://app.naviprotocol.io",
    "navi-lending": "https://app.naviprotocol.io",
    "navi-protocol": "https://app.naviprotocol.io",
    "scallop": "https://app.scallop.io",
    "scallop-lend": "https://app.scallop.io",
    "cetus": "https://app.cetus.zone",
    "cetus-clmm": "https://app.cetus.zone",
    "suilend": "https://suilend.fi",
    # Aptos
    "thala": "https://app.thala.fi",
    "thalaswap": "https://app.thala.fi",
    "aries": "https://ariesmarkets.xyz",
    "aries-markets": "https://ariesmarkets.xyz",
    "amnis": "https://stake.amnis.finance",
    "amnis-finance": "https://stake.amnis.finance",
    # Frax Ecosystem
    "frax": "https://app.frax.finance",
    "fraxlend": "https://app.frax.finance/fraxlend",
    "frax-swap": "https://app.frax.finance/swap",
    # Others
    "venus": "https://app.venus.io",
    "benqi": "https://app.benqi.fi",
    "beets": "https://beets.fi",
    "beets-dex-v3": "https://beets.fi",
    "silo": "https://app.silo.finance",
    "silo-v2": "https://app.silo.finance",
    "ethena": "https://app.ethena.fi",
    "ether.fi": "https://app.ether.fi",
    "ether.fi-stake": "https://app.ether.fi"
}


def get_protocol_url(project: str, pool_id: str = "") -> str:
    """Get direct official web app URL for the protocol."""
    p = project.lower().strip()
    for k, url in PROTOCOL_APP_URLS.items():
        if p == k or p.startswith(k):
            return url
    return f"https://defillama.com/protocol/{p}"


def normalize_stable_symbol(symbol: str) -> str:
    """Extract and normalize canonical stablecoin symbol."""
    sym = symbol.upper().strip()
    for st in ["USDC", "USDT", "DAI", "USDS", "USDE", "PYUSD", "GHO", "FRAX", "FDUSD", "CRVUSD", "LUSD"]:
        if st in sym:
            return st
    return sym


def is_stablecoin(symbol: str) -> bool:
    """Check if the symbol represents a verified stablecoin."""
    sym = symbol.upper().strip()
    return any(st in sym for st in VERIFIED_STABLECOINS)


def get_category(project: str, symbol: str = "") -> str:
    """
    Classify pool category accurately:
    - If symbol has a pair delimiter (-, /) or project is a DEX -> 'dex'
    - If single-asset lending protocol -> 'lending'
    - If staking / yield aggregator -> 'yield'
    """
    p = project.lower().strip()
    s = symbol.upper().strip()

    # If it's explicitly a DEX project or contains pair hyphen (like USDC-ETH)
    is_pair = ("-" in s or "/" in s or " " in s)
    is_dex_project = (
        "-dex" in p or "dex" in p or
        any(dp in p for dp in ["uniswap", "curve", "aerodrome", "velodrome", "balancer", "pancakeswap", "sushi", "camelot", "trader-joe", "ambient", "maverick", "orca", "raydium"])
    )

    if is_pair or is_dex_project:
        return "dex"

    # Yield & Staking
    if any(yp in p for yp in ["lido", "pendle", "eigenlayer", "rocket-pool", "jito", "marinade", "convex", "yearn", "beefy", "stargate"]):
        return "yield"

    # Pure Single-Asset Lending
    if any(lp in p for lp in ["aave", "morpho", "compound", "spark", "fluid", "venus", "benqi", "silo", "euler", "moonwell", "zerolend"]):
        return "lending"

    return "other"


def fmt_tvl(tvl: float) -> str:
    if tvl >= 1_000_000_000:
        return f"${tvl / 1_000_000_000:.1f}B"
    if tvl >= 1_000_000:
        return f"${tvl / 1_000_000:.1f}M"
    if tvl >= 1_000:
        return f"${tvl / 1_000:.0f}K"
    return f"${tvl:.0f}"


def fmt_project(name: str) -> str:
    return name.replace("-", " ").title()

# ──────────────────────────────────────────────
#  MAIN SEARCH
# ──────────────────────────────────────────────

def search_pools(query: dict) -> list:
    """
    Search & filter pools by structured query.

    query keys:
        assets            : list[str]   — coin tickers (USDT, ETH …)
        chains            : list[str]   — include only these chains
        excluded_chains   : list[str]   — exclude these chains
        protocols         : list[str]   — specific protocol names
        category          : str|None    — "lending" / "dex" / "yield"
        min_tvl           : int         — minimum TVL in USD
        min_apy           : float       — minimum APY %
        limit             : int         — max results to return
    """
    cfg = load_config()
    pools = fetch_pools()
    if not pools:
        return []

    assets = {a.upper() for a in query.get("assets", [])}
    chains = {c.lower() for c in query.get("chains", [])}
    excluded = {c.lower() for c in query.get("excluded_chains", cfg.get("default_excluded_chains", []))}
    protocols = {p.lower() for p in query.get("protocols", [])}
    category = query.get("category")
    min_tvl = query.get("min_tvl", cfg.get("default_min_tvl", 1_000_000))
    min_apy = query.get("min_apy", 0.0)
    limit = query.get("limit", cfg.get("max_results", 10))
    max_apy = cfg.get("max_apy_cap", 500)

    results = []
    for p in pools:
        project = p.get("project", "")
        chain = p.get("chain", "")
        symbol = p.get("symbol", "").upper()
        tvl = p.get("tvlUsd", 0) or 0
        apy = p.get("apy", 0) or 0

        # --- category filter ---
        if category and get_category(project) != category:
            continue

        # --- protocol filter ---
        if protocols and not any(pr in project.lower() for pr in protocols):
            continue

        # --- chain include ---
        if chains and not any(c in chain.lower() for c in chains):
            continue

        # --- chain exclude ---
        if excluded and any(c in chain.lower() for c in excluded):
            continue

        # --- asset filter ---
        if assets:
            norm = symbol.replace("WETH", "ETH").replace("WBTC", "BTC")
            parts = set(norm.replace("-", " ").replace("/", " ").split())
            if not assets & parts:
                continue

        # --- tvl filter ---
        if tvl < min_tvl:
            continue

        # --- apy sanity ---
        if apy < min_apy or apy > max_apy:
            continue

        results.append({
            "project": project,
            "chain": chain,
            "symbol": symbol,
            "apy": round(apy, 2),
            "apyBase": round(p.get("apyBase", 0) or 0, 2),
            "apyReward": round(p.get("apyReward", 0) or 0, 2),
            "tvl": tvl,
            "category": get_category(project),
            "pool_id": p.get("pool", ""),
        })

    results.sort(key=lambda x: x["apy"], reverse=True)
    return results[:limit]
