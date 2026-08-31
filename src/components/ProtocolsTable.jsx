import React, { useState } from 'react';
import { ExternalLink, Filter, TrendingUp, TrendingDown, Layers } from 'lucide-react';
import { formatCurrency, formatPercent } from '../services/defiApi';

const CATEGORIES = ['All', 'Liquid Staking', 'Lending', 'Dexes', 'Restaking', 'Yield', 'CDP', 'Bridge'];

export default function ProtocolsTable({ protocols, searchQuery }) {
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedChain, setSelectedChain] = useState('All');

  // Filter protocols
  const filtered = (protocols || []).filter(p => {
    // Search query filter
    const matchesSearch = !searchQuery || 
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.symbol?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.category.toLowerCase().includes(searchQuery.toLowerCase());

    // Category filter
    const matchesCat = selectedCategory === 'All' || 
      p.category.toLowerCase() === selectedCategory.toLowerCase();

    // Chain filter
    const matchesChain = selectedChain === 'All' || 
      (p.chains && p.chains.some(c => c.toLowerCase() === selectedChain.toLowerCase()));

    return matchesSearch && matchesCat && matchesChain;
  });

  return (
    <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 lg:p-6 mb-6">
      
      {/* Table Header & Category Filter Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <Layers className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">Top DeFi Protocols</h3>
            <p className="text-xs text-slate-400">Ranked by Total Value Locked (TVL)</p>
          </div>
        </div>

        {/* Category Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 scrollbar-none">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                selectedCategory === cat
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800/60'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* DESKTOP TABLE */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 text-xs uppercase font-semibold">
              <th className="py-3 px-3 w-12 text-center">#</th>
              <th className="py-3 px-4">Protocol</th>
              <th className="py-3 px-3">Category</th>
              <th className="py-3 px-3">Chains</th>
              <th className="py-3 px-4 text-right">TVL</th>
              <th className="py-3 px-3 text-right">24h</th>
              <th className="py-3 px-3 text-right">7d</th>
              <th className="py-3 px-3 text-right">Mcap / TVL</th>
              <th className="py-3 px-3 text-center">Link</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-sans text-xs">
            {filtered.slice(0, 50).map((p) => {
              const is1dPos = (p.change_1d || 0) >= 0;
              const is7dPos = (p.change_7d || 0) >= 0;

              return (
                <tr key={p.id} className="hover:bg-slate-800/30 transition-colors group">
                  <td className="py-3 px-3 text-center font-mono font-bold text-slate-500">
                    {p.rank}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-3">
                      {p.logo ? (
                        <img src={p.logo} alt={p.name} className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 object-cover" />
                      ) : (
                        <div className="w-7 h-7 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center font-bold text-cyan-400 text-xs">
                          {p.name.charAt(0)}
                        </div>
                      )}
                      <div>
                        <div className="font-bold text-white group-hover:text-cyan-400 transition-colors flex items-center gap-1.5">
                          <span>{p.name}</span>
                          {p.symbol && (
                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                              {p.symbol}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 px-3">
                    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-slate-800/80 text-slate-300 border border-slate-700/50">
                      {p.category}
                    </span>
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-1 flex-wrap max-w-[140px]">
                      {(p.chains || []).slice(0, 3).map((chain, i) => (
                        <span key={i} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-400">
                          {chain}
                        </span>
                      ))}
                      {(p.chains || []).length > 3 && (
                        <span className="text-[10px] text-slate-500">+{p.chains.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-4 text-right font-mono font-bold text-white text-sm">
                    {formatCurrency(p.tvl)}
                  </td>
                  <td className="py-3 px-3 text-right font-mono font-semibold">
                    <span className={is1dPos ? 'text-emerald-400' : 'text-rose-400'}>
                      {formatPercent(p.change_1d)}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right font-mono font-semibold">
                    <span className={is7dPos ? 'text-emerald-400' : 'text-rose-400'}>
                      {formatPercent(p.change_7d)}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right font-mono text-slate-400">
                    {p.mcapTvlRatio ? `${p.mcapTvlRatio}x` : '—'}
                  </td>
                  <td className="py-3 px-3 text-center">
                    {p.url && (
                      <a 
                        href={p.url} 
                        target="_blank" 
                        rel="noreferrer"
                        className="inline-flex p-1.5 rounded-lg bg-slate-800/60 hover:bg-cyan-500/20 text-slate-400 hover:text-cyan-300 transition-colors"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* MOBILE CARDS LIST */}
      <div className="md:hidden space-y-3">
        {filtered.slice(0, 30).map((p) => {
          const is1dPos = (p.change_1d || 0) >= 0;

          return (
            <div key={p.id} className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono font-bold text-xs text-slate-500 w-4">#{p.rank}</span>
                  {p.logo ? (
                    <img src={p.logo} alt={p.name} className="w-7 h-7 rounded-full bg-slate-800 object-cover" />
                  ) : (
                    <div className="w-7 h-7 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold text-xs">
                      {p.name.charAt(0)}
                    </div>
                  )}
                  <div>
                    <h4 className="font-bold text-white text-sm">{p.name}</h4>
                    <span className="text-[10px] text-slate-400">{p.category}</span>
                  </div>
                </div>

                <div className="text-right">
                  <div className="font-mono font-bold text-white text-sm">
                    {formatCurrency(p.tvl)}
                  </div>
                  <div className={`font-mono text-xs font-semibold ${is1dPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {formatPercent(p.change_1d)} (24h)
                  </div>
                </div>
              </div>

              {p.chains && p.chains.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-800/40 text-[10px]">
                  <span className="text-slate-500">Chains:</span>
                  {p.chains.slice(0, 4).map((c, idx) => (
                    <span key={idx} className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                      {c}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

    </div>
  );
}
