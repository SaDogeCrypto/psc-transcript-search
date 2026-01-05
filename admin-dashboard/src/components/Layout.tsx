'use client';

import Link from 'next/link';

export function Header() {
  return (
    <header className="header">
      <div className="header-content">
        <div className="logo-title">
          <div>
            <h1>PSC Admin</h1>
            <p className="subtitle">Pipeline Monitor Dashboard</p>
          </div>
        </div>
      </div>
    </header>
  );
}

export function Tabs({ active }: { active: string }) {
  const tabs = [
    { id: 'overview', label: 'Overview', href: '/' },
    { id: 'sources', label: 'Sources', href: '/sources' },
    { id: 'hearings', label: 'Hearings', href: '/hearings' },
    { id: 'runs', label: 'Pipeline Runs', href: '/runs' },
  ];

  return (
    <div className="tabs-container">
      <div className="tabs">
        {tabs.map((tab) => (
          <Link
            key={tab.id}
            href={tab.href}
            className={`tab ${active === tab.id ? 'active' : ''}`}
          >
            {tab.label}
          </Link>
        ))}
      </div>
    </div>
  );
}

export function PageLayout({
  children,
  activeTab,
}: {
  children: React.ReactNode;
  activeTab: string;
}) {
  return (
    <>
      <Header />
      <main className="main-content">
        <Tabs active={activeTab} />
        {children}
      </main>
    </>
  );
}
