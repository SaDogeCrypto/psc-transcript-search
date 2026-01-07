'use client';

import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export function Header() {
  return (
    <header className="header">
      <div className="header-content">
        <div className="logo-title">
          <div>
            <h1>CanaryScope Admin</h1>
            <p className="subtitle">Pipeline Monitor Dashboard</p>
          </div>
        </div>
        <Link href="/dashboard" className="btn btn-secondary" style={{ color: 'white', borderColor: 'rgba(255,255,255,0.3)' }}>
          <ArrowLeft size={16} />
          Back to Dashboard
        </Link>
      </div>
    </header>
  );
}

export function Tabs({ active }: { active: string }) {
  const tabs = [
    { id: 'overview', label: 'Overview', href: '/admin' },
    { id: 'sources', label: 'Sources', href: '/admin/sources' },
    { id: 'hearings', label: 'Hearings', href: '/admin/hearings' },
    { id: 'pipeline', label: 'Pipeline', href: '/admin/pipeline' },
    { id: 'schedules', label: 'Schedules', href: '/admin/schedules' },
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
  title,
  subtitle,
}: {
  children: React.ReactNode;
  activeTab?: string;
  title?: string;
  subtitle?: string;
}) {
  // Determine active tab from title if not provided
  const active = activeTab || (title ? title.toLowerCase() : 'overview');

  return (
    <>
      <Header />
      <main className="main-content">
        <Tabs active={active} />
        {(title || subtitle) && (
          <div style={{ marginBottom: '1.5rem' }}>
            {title && <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.25rem' }}>{title}</h2>}
            {subtitle && <p style={{ color: 'var(--gray-500)' }}>{subtitle}</p>}
          </div>
        )}
        {children}
      </main>
    </>
  );
}
