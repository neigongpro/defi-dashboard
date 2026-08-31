import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import StatsCards from './components/StatsCards';
import ChartsSection from './components/ChartsSection';
import ProtocolsTable from './components/ProtocolsTable';
import YieldPools from './components/YieldPools';
import ChainBreakdown from './components/ChainBreakdown';
import { fetchOverviewData, fetchYieldPools } from './services/defiApi';
import { RefreshCw, Zap, ShieldCheck } from 'lucide-react';

export default function App() {
  const [data, setData] = useState(null);
  const [pools, setPools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  const [lastUpdated, setLastUpdated] = useState(new Date());

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [overview, yieldPools] = await Promise.all([
        fetchOverviewData(),
        fetchYieldPools()
      ]);
      setData(overview);
      setPools(yieldPools);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Data load error:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
    // Auto-refresh every 60s
    const interval = setInterval(() => {
      loadData();
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  if (loading || !data) {
    return (
      <div className="min-h-screen bg-[#0a0b0e] flex flex-col items-center justify-center p-4">
        <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center glow-cyan mb-4 animate-pulse">
          <Zap className="w-7 h-7 text-cyan-400 fill-cyan-400/30 animate-bounce" />
        </div>
        <h2 className="text-lg font-bold text-white mb-1">Loading On-Chain Telemetry...</h2>
        <p className="text-xs text-slate-400">Connecting to DefiLlama protocol nodes</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0b0e] text-[#f1f5f9] flex flex-col selection:bg-cyan-500/30">
      
      {/* Top Sticky Header */}
      <Header 
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        refreshing={refreshing}
        onRefresh={() => loadData(true)}
        lastUpdated={lastUpdated}
      />

      {/* Main Dashboard Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6">
        
        {/* Top Hero Metrics Cards */}
        <StatsCards data={data} />

        {/* Tab 1: OVERVIEW */}
        {activeTab === 'overview' && (
          <>
            <ChartsSection 
              historicalTvl={data.historicalTvl} 
              chains={data.chains} 
            />
            <ProtocolsTable 
              protocols={data.protocols} 
              searchQuery={searchQuery} 
            />
            <YieldPools 
              pools={pools} 
            />
          </>
        )}

        {/* Tab 2: PROTOCOLS ONLY */}
        {activeTab === 'protocols' && (
          <ProtocolsTable 
            protocols={data.protocols} 
            searchQuery={searchQuery} 
          />
        )}

        {/* Tab 3: YIELDS ONLY */}
        {activeTab === 'yields' && (
          <YieldPools 
            pools={pools} 
          />
        )}

        {/* Tab 4: CHAINS ONLY */}
        {activeTab === 'chains' && (
          <ChainBreakdown 
            chains={data.chains} 
            totalTvl={data.totalTvl} 
          />
        )}

      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/50 py-6 px-4 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span>Live Node: <strong>defi.shtark.top</strong></span>
          </div>
          <div>
            Powered by <strong>DefiLlama API</strong> • Auto-updated at {lastUpdated.toLocaleTimeString()}
          </div>
        </div>
      </footer>

    </div>
  );
}
