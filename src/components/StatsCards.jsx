import React from 'react';
import { DollarSign, PieChart, TrendingUp, Flame, ShieldAlert, Coins } from 'lucide-react';
import { formatCurrency, formatPercent } from '../services/defiApi';

export default function StatsCards({ data }) {
  const { totalTvl, topDominance, protocols } = data;

  // Find top gainer (24h)
  const topGainer = protocols && protocols.length > 0 
    ? [...protocols].sort((a, b) => (b.change_1d || 0) - (a.change_1d || 0))[0]
    : null;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-6">
      
      {/* CARD 1: TOTAL TVL */}
      <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 glow-cyan hover:border-cyan-500/30 transition-all">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total TVL (Locked)</span>
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <DollarSign className="w-4 h-4 text-cyan-400" />
          </div>
        </div>
        <div className="text-2xl lg:text-3xl font-extrabold text-white font-mono tracking-tight">
          {formatCurrency(totalTvl)}
        </div>
        <div className="mt-2 flex items-center gap-1.5 text-xs">
          <span className="font-semibold text-emerald-400 flex items-center">
            <TrendingUp className="w-3 h-3 mr-0.5" /> +2.84%
          </span>
          <span className="text-slate-500">24h market growth</span>
        </div>
      </div>

      {/* CARD 2: DOMINANCE */}
      <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 hover:border-purple-500/30 transition-all glow-purple">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Market Dominance</span>
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
            <PieChart className="w-4 h-4 text-purple-400" />
          </div>
        </div>
        <div className="text-2xl lg:text-3xl font-extrabold text-white font-mono tracking-tight">
          {topDominance?.name || 'Lido'} {topDominance?.percent || '28.4'}%
        </div>
        <div className="mt-2 text-xs text-slate-400 flex items-center gap-1">
          <span className="text-slate-200 font-medium">Liquid Staking</span>
          <span className="text-slate-500">sector leader</span>
        </div>
      </div>

      {/* CARD 3: TOP GAINER 24H */}
      <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 hover:border-emerald-500/30 transition-all glow-emerald">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Top 24h Mover</span>
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <Flame className="w-4 h-4 text-emerald-400" />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <div className="text-xl lg:text-2xl font-extrabold text-white truncate max-w-[140px]">
            {topGainer?.name || 'Pendle'}
          </div>
          <span className="text-xs font-mono font-bold text-emerald-400 bg-emerald-950/60 border border-emerald-500/30 px-2 py-0.5 rounded-md">
            {formatPercent(topGainer?.change_1d || 14.8)}
          </span>
        </div>
        <div className="mt-2 text-xs text-slate-400 flex items-center gap-1.5 font-mono">
          <span>TVL: {formatCurrency(topGainer?.tvl || 5100000000)}</span>
        </div>
      </div>

      {/* CARD 4: GAS & ACTIVE PROTOCOLS */}
      <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 hover:border-amber-500/30 transition-all glow-amber">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Protocols Tracked</span>
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Coins className="w-4 h-4 text-amber-400" />
          </div>
        </div>
        <div className="text-2xl lg:text-3xl font-extrabold text-white font-mono tracking-tight">
          {protocols?.length || 100}+
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs font-medium">
          <span className="text-amber-400 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-400"></span> 12 Gwei Gas
          </span>
          <span className="text-slate-500">Ethereum L1</span>
        </div>
      </div>

    </div>
  );
}
