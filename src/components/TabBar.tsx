const tabs = ['ALL', 'OUTERWEAR', 'TOPS', 'PANTS'] as const;
export type Tab = (typeof tabs)[number];

export function TabBar({ current, onChange }: { current: Tab; onChange: (tab: Tab) => void }) {
  return (
    <nav className="tabs">
      {tabs.map((tab) => (
        <button type="button" key={tab} className={`tab ${tab === current ? 'active' : ''}`} onClick={() => onChange(tab)}>
          {tab}
        </button>
      ))}
    </nav>
  );
}
