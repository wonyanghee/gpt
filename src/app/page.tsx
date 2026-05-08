'use client';

import { useMemo, useState } from 'react';
import { ProductCard } from '../components/ProductCard';
import { TabBar, type Tab } from '../components/TabBar';
import { products } from '../data/products';

export default function Page() {
  const [tab, setTab] = useState<Tab>('ALL');
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<'A' | 'B'>('A');

  const visible = useMemo(() => {
    const byTab = tab === 'ALL' ? products : products.filter((p) => p.category === tab);
    const q = query.trim().toLowerCase();
    return q ? byTab.filter((p) => `${p.name} ${p.line}`.toLowerCase().includes(q)) : byTab;
  }, [tab, query]);

  return (
    <div className={`app-shell mode-${mode.toLowerCase()}`}>
      <aside className="sidebar">
        <p className="logo">SSENSE ARCHIVE</p>
        <div className="nav-item active">Catalog</div>
        <div className="nav-item">Saved</div>
        <div className="nav-item">Sale</div>
      </aside>

      <main className="content-wrap">
        <section className="content">
          <h1>Technical Minimal Catalog</h1>
          <TabBar current={tab} onChange={setTab} />

          <div className="toolbar">
            <input
              className="search-input"
              type="text"
              placeholder="Search artifacts"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className="toolbar-right">
              <button type="button" className={`mode-btn ${mode === 'A' ? 'active' : ''}`} onClick={() => setMode('A')}>A</button>
              <button type="button" className={`mode-btn ${mode === 'B' ? 'active' : ''}`} onClick={() => setMode('B')}>B</button>
              <span className="result-count">{visible.length} ITEMS</span>
            </div>
          </div>

          <section className="grid">
            {visible.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </section>
        </section>
      </main>
    </div>
  );
}
