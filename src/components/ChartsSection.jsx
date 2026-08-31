import React, { useState } from 'react';
import { 
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, 
  PieChart, Pie, Cell, Legend 
} from 'recharts';
import { TrendingUp, PieChart as PieIcon } from 'lucide-react';
import { formatCurrency } from '../services/defiApi';

const CHAIN_COLORS = ['#06b6d4', '#8b5cf6', '#10b981', '#f59e0b', '#ec4899', '#3b82f6', '#64748b'];

export default function ChartsSection({ historicalTvl, chains }) {
  const [timeframe, setTimeframe] = useState('30d');

  // Format data for Pie Chart
  const pieData = (chains || []).slice(0, 6).map(c => ({
    name: c.name,
    value: c.tvl
  }));

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-slate-950/90 backdrop-blur-md border border-cyan-500/30 px-3 py-2 rounded-xl shadow-xl font-mono text-xs">
          <p className="text-slate-400 font-sans mb-1">{label}</p>
          <p className="font-bold text-cyan-400">
            TVL: ${payload[0].value}B
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      
      {/* TVL HISTORY AREA CHART (2 Columns on Desktop) */}
      <div className="lg:col-span-2 bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 lg:p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-cyan-400" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">Global TVL Growth Trend</h3>
              <p className="text-xs text-slate-400">Historical capital locked across all chains</p>
            </div>
          </div>

          {/* Timeframe pills */}
          <div className="flex items-center gap-1 bg-slate-950/60 p-1 rounded-lg border border-slate-800 self-start sm:self-auto">
            {['7d', '30d', '90d', '1y'].map(t => (
              <button
                key={t}
                onClick={() => setTimeframe(t)}
                className={`px-2.5 py-0.5 rounded-md text-[11px] font-semibold transition-all ${
                  timeframe === t 
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' 
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {t.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="h-[220px] w-full font-mono text-xs">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={historicalTvl || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="tvlGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0}/>
                </linearGradient>
              </defs>
              <XAxis 
                dataKey="date" 
                stroke="#475569" 
                fontSize={10} 
                tickLine={false} 
                axisLine={false}
              />
              <YAxis 
                stroke="#475569" 
                fontSize={10} 
                tickLine={false} 
                axisLine={false}
                tickFormatter={(val) => `$${val}B`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area 
                type="monotone" 
                dataKey="tvl" 
                stroke="#06b6d4" 
                strokeWidth={2.5}
                fillOpacity={1} 
                fill="url(#tvlGradient)" 
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* CHAIN DOMINANCE DONUT CHART (1 Column on Desktop) */}
      <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-4 lg:p-5 flex flex-col justify-between">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
            <PieIcon className="w-4 h-4 text-purple-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">Chain Dominance</h3>
            <p className="text-xs text-slate-400">TVL distribution by Blockchain</p>
          </div>
        </div>

        <div className="h-[180px] w-full flex items-center justify-center">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                innerRadius={50}
                outerRadius={75}
                paddingAngle={3}
                dataKey="value"
              >
                {pieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={CHAIN_COLORS[index % CHAIN_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip 
                formatter={(val) => [formatCurrency(val), 'TVL']}
                contentStyle={{ 
                  backgroundColor: '#0a0b0e', 
                  borderColor: '#334155', 
                  borderRadius: '12px',
                  fontSize: '12px',
                  fontFamily: 'JetBrains Mono'
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Mini Legend */}
        <div className="grid grid-cols-2 gap-1.5 pt-2 border-t border-slate-800/60">
          {pieData.slice(0, 4).map((c, i) => (
            <div key={c.name} className="flex items-center gap-1.5 text-xs text-slate-300">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: CHAIN_COLORS[i] }}></span>
              <span className="truncate">{c.name}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
