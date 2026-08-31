import React, { useState } from 'react';
import { DollarSign, Shield, Sparkles, Filter, CheckCircle2 } from 'lucide-react';
import { formatCurrency } from '../services/defiApi';

export default function YieldPools({ pools }) {
  const [filterStable, setFilterStable] = useState(false);

  const filtered = (pools || []).filter(p => {
    if (filterStable && !p.stablecoin) return false;
    return true;
  });

  return (
    <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 lg:p-6 mb-6">
      
      {/* Header & Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">Top DeFi Yields & Staking APY</h3>
            <p className="text-xs text-slate-400">Audited pools with over $10M+ TVL liquidity</p>
          </div>
        </div>

        {/* Stablecoin toggle */}
        <button
          onClick={() => setFilterStable(!filterStable)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all self-start sm:self-auto ${
            filterStable
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
              : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800'
          }`}
        >
          <Shield className="w-3.5 h-3.5" />
          <span>Stablecoins Only (USD)</span>
          {filterStable && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
        </button>
      </div>

      {/* Yield Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
        {filtered.map((pool, idx) => (
          <div 
            key={pool.pool || idx}
            className="bg-slate-950/70 border border-slate-800/90 hover:border-emerald-500/30 rounded-xl p-4 flex flex-col justify-between transition-all hover:translate-y-[-2px] group"
          >
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-slate-300 uppercase tracking-wider bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                  {pool.project}
                </span>
                <span className="text-[10px] font-mono text-slate-400 px-2 py-0.5 rounded-full bg-slate-900/60 border border-slate-800">
                  {pool.chain}
                </span>
              </div>

              <h4 className="text-sm font-extrabold text-white group-hover:text-emerald-300 transition-colors mb-3">
                {pool.symbol}
              </h4>
            </div>

            <div className="pt-3 border-t border-slate-800/60 flex items-end justify-between">
              <div>
                <span className="text-[10px] text-slate-400 block uppercase font-medium">Pool Liquidity</span>
                <span className="text-xs font-mono font-semibold text-slate-200">{pool.formattedTvl}</span>
              </div>

              <div className="text-right">
                <span className="text-[10px] text-slate-400 block uppercase font-medium">Net APY</span>
                <span className="text-xl font-mono font-extrabold text-emerald-400">
                  {pool.apy}%
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}
