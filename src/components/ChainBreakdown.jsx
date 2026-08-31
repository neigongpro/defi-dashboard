import React from 'react';
import { TrendingUp, Globe } from 'lucide-react';
import { formatCurrency } from '../services/defiApi';

export default function ChainBreakdown({ chains, totalTvl }) {
  return (
    <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 lg:p-6 mb-6">
      
      <div className="flex items-center gap-2.5 mb-5">
        <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
          <Globe className="w-4 h-4 text-blue-400" />
        </div>
        <div>
          <h3 className="text-base font-bold text-white">Blockchain Ecosystems TVL</h3>
          <p className="text-xs text-slate-400">Total capital deployed across Layer-1 & Layer-2 networks</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {(chains || []).map((chain, index) => {
          const percentOfTotal = totalTvl > 0 ? ((chain.tvl / totalTvl) * 100).toFixed(1) : '0.0';

          return (
            <div 
              key={chain.name}
              className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3.5 flex flex-col gap-2 hover:border-blue-500/30 transition-all"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono font-bold text-xs text-slate-500">#{index + 1}</span>
                  <span className="font-bold text-sm text-white">{chain.name}</span>
                </div>
                <div className="text-right font-mono font-bold text-sm text-cyan-300">
                  {chain.formattedTvl}
                </div>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden border border-slate-800/50">
                <div 
                  className="bg-gradient-to-r from-blue-500 to-cyan-400 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(Math.max(parseFloat(percentOfTotal), 2), 100)}%` }}
                />
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                <span>Dominance</span>
                <span className="font-semibold text-slate-200">{percentOfTotal}%</span>
              </div>
            </div>
          );
        })}
      </div>

    </div>
  );
}
