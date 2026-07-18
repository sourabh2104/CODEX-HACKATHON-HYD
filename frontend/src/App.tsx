import { useEffect, useMemo, useState } from 'react';
import { Icon } from './components/Icon';
import { api, apiConfig, getDashboard } from './lib/api';
import { demoData } from './lib/demo';
import type { ActionDefinition, Activity, ActivityEvent, Area, ConnectionCheck, DashboardData, Policy, PolicyArtifact, PolicyTestRun, RepositorySummary, Severity, Vendor } from './types';

const navItems: { id: Area; label: string; icon: 'grid' | 'link' | 'bot' | 'shield' | 'bolt'; hint?: string }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: 'grid' },
  { id: 'vendors', label: 'Vendors', icon: 'link' },
  { id: 'agent', label: 'Policy Agent', icon: 'bot', hint: 'AI' },
  { id: 'policies', label: 'Deployed Policies', icon: 'shield' },
  { id: 'actions', label: 'Actions', icon: 'bolt' },
];

const pageCopy: Record<Area, { eyebrow: string; title: string; description: string }> = {
  dashboard: { eyebrow: 'Operations overview', title: 'Security overview', description: 'Security posture across the current workspace.' },
  vendors: { eyebrow: 'Data sources', title: 'Vendor connections', description: 'Connect and monitor the systems that feed your policy engine.' },
  agent: { eyebrow: 'Guided creation', title: 'Policy Agent', description: 'Turn a risk scenario into a tested, deployable policy.' },
  policies: { eyebrow: 'Runtime controls', title: 'Deployed policies', description: 'Monitor active policy versions and the events they evaluate.' },
  actions: { eyebrow: 'Response orchestration', title: 'Actions', description: 'Configure safe, auditable responses when a policy triggers.' },
};

function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'purple' | 'blue' }) {
  return <span className={`badge badge-${tone}`}><span className="badge-dot" />{children}</span>;
}

function Button({ children, variant = 'secondary', icon, onClick, disabled, type = 'button', className = '' }: { children: React.ReactNode; variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; icon?: Parameters<typeof Icon>[0]['name']; onClick?: () => void; disabled?: boolean; type?: 'button' | 'submit'; className?: string }) {
  return <button className={`button button-${variant} ${className}`} onClick={onClick} disabled={disabled} type={type}>{icon && <Icon name={icon} size={16} />}{children}</button>;
}

function MetricCard({ label, value, delta, sub, icon, tone = 'purple' }: { label: string; value: string; delta: string; sub: string; icon: Parameters<typeof Icon>[0]['name']; tone?: string }) {
  return <div className="metric-card">
    <div className="metric-top"><span className={`metric-icon metric-${tone}`}><Icon name={icon} size={18} /></span><span className="metric-label">{label}</span><Icon name="more" size={18} className="muted" /></div>
    <div className="metric-value">{value}</div>
    <div className="metric-foot"><span className={delta.startsWith('-') ? 'delta good' : 'delta'}>{delta}</span><span>{sub}</span></div>
  </div>;
}

function SectionHeader({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  return <div className="section-header"><h2>{title}</h2>{action && <button className="text-button" onClick={onAction}>{action}<Icon name="arrow" size={15} /></button>}</div>;
}

function ActivityFeed({ activity }: { activity: Activity[] }) {
  return <div className="activity-feed">{activity.map((item) => <div className="activity-row" key={item.id}>
    <span className={`activity-icon activity-${item.tone}`}><Icon name={item.icon as Parameters<typeof Icon>[0]['name']} size={15} /></span>
    <div className="activity-copy"><strong>{item.title}</strong><span>{item.detail}</span></div><time>{item.time}</time>
  </div>)}</div>;
}

function StatusBadge({ status }: { status: Vendor['status'] | Policy['status'] }) {
  const tone = status === 'connected' || status === 'enabled' ? 'success' : status === 'degraded' || status === 'warning' ? 'warning' : status === 'testing' || status === 'deploying' ? 'purple' : 'neutral';
  const label = status === 'enabled' ? 'Enabled' : status === 'connected' ? 'Connected' : status === 'degraded' ? 'Degraded' : status === 'disabled' ? 'Disabled' : status === 'deploying' ? 'Deploying' : status === 'testing' ? 'Testing' : 'Needs review';
  return <Badge tone={tone}>{label}</Badge>;
}

function LegacyDashboard({ data, onNavigate }: { data: DashboardData; onNavigate: (area: Area) => void }) {
  const connected = data.vendors.filter((vendor) => vendor.status === 'connected').length;
  const enabled = data.policies.filter((policy) => policy.status === 'enabled').length;
  const triggerCount = Number(data.metrics.triggers.replace(/[^0-9]/g, '')) || 0;
  const highTriggers = data.policies.filter((policy) => policy.severity === 'high').reduce((sum, policy) => sum + policy.triggers, 0);
  const criticalTriggers = data.policies.filter((policy) => policy.severity === 'critical').reduce((sum, policy) => sum + policy.triggers, 0);
  const mediumTriggers = Math.max(0, triggerCount - highTriggers - criticalTriggers);
  return <>
    <div className="health-banner"><div className="health-pulse"><span /></div><div><strong>All systems operational</strong><span>Ingestion and evaluation are within normal operating parameters.</span></div><span className="health-time">Updated just now <Icon name="refresh" size={14} /></span></div>
    <div className="metric-grid">
      <MetricCard label="Events processed" value={data.metrics.events} delta={data.metrics.eventsDelta} sub="vs. last 24 hours" icon="activity" tone="blue" />
      <MetricCard label="Active policies" value={`${enabled} / ${data.policies.length}`} delta="+1" sub="deployed this week" icon="shield" tone="purple" />
      <MetricCard label="Policy triggers" value={data.metrics.triggers} delta={data.metrics.triggerDelta} sub="vs. last 24 hours" icon="alert" tone="orange" />
      <MetricCard label="Avg. evaluation" value={data.metrics.latency} delta={data.metrics.latencyDelta} sub="faster than last week" icon="bolt" tone="green" />
    </div>
    <div className="dashboard-grid">
      <section className="panel panel-wide"><SectionHeader title="Policy activity" action="View policies" onAction={() => onNavigate('policies')} /><div className="chart-wrap"><div className="chart-legend"><span><i className="legend-line purple-line" />Evaluations</span><span><i className="legend-line orange-line" />Triggers</span><span className="chart-period">Last 24 hours <Icon name="chevron" size={13} /></span></div><div className="chart"><div className="chart-y"><span>3k</span><span>2k</span><span>1k</span><span>0</span></div><svg viewBox="0 0 700 220" preserveAspectRatio="none" role="img" aria-label="Policy evaluations and triggers over the last 24 hours"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8b5cf6" stopOpacity=".24" /><stop offset="1" stopColor="#8b5cf6" stopOpacity="0" /></linearGradient></defs><path d="M0 174 C35 158 43 167 72 138 S111 151 141 127 S183 149 213 112 S248 132 276 95 S312 111 345 87 S379 104 407 75 S441 100 472 63 S515 91 543 49 S578 82 610 37 S662 68 700 22 L700 220 L0 220Z" fill="url(#area)" /><path d="M0 174 C35 158 43 167 72 138 S111 151 141 127 S183 149 213 112 S248 132 276 95 S312 111 345 87 S379 104 407 75 S441 100 472 63 S515 91 543 49 S578 82 610 37 S662 68 700 22" fill="none" stroke="#a78bfa" strokeWidth="2.5" /><path d="M0 196 C38 190 46 201 75 183 S112 190 141 177 S183 193 212 168 S250 181 280 153 S318 177 347 148 S384 171 411 134 S447 162 476 123 S511 153 544 105 S579 132 612 101 S657 124 700 75" fill="none" stroke="#f5a524" strokeWidth="2" strokeDasharray="5 5" /></svg><div className="chart-x"><span>00:00</span><span>04:00</span><span>08:00</span><span>12:00</span><span>16:00</span><span>20:00</span><span>Now</span></div></div></div></section>
      <section className="panel"><SectionHeader title="Vendor health" action="Manage" onAction={() => onNavigate('vendors')} /><div className="health-list">{data.vendors.slice(0, 4).map((vendor) => <div className="health-item" key={vendor.id}><span className="vendor-mark" style={{ color: vendor.color }}>{vendor.icon}</span><div><strong>{vendor.name}</strong><span>{vendor.events} events</span></div><span className={`health-dot health-${vendor.status}`} title={vendor.status} /></div>)}</div><div className="panel-footer"><span>{connected} of {data.vendors.length} connections healthy</span><button onClick={() => onNavigate('vendors')} aria-label="View vendor health"><Icon name="arrow" size={16} /></button></div></section>
    </div>
    <div className="dashboard-grid lower-grid"><section className="panel panel-wide"><SectionHeader title="Recent activity" action="View audit log" /><ActivityFeed activity={data.activity} /></section><section className="panel"><SectionHeader title="Trigger distribution" /><div className="donut-wrap"><div className="donut"><div><strong>{triggerCount}</strong><span>triggers</span></div></div><div className="donut-legend"><span><i className="dot dot-red" />Critical <b>{criticalTriggers}</b></span><span><i className="dot dot-orange" />High <b>{highTriggers}</b></span><span><i className="dot dot-blue" />Medium <b>{mediumTriggers}</b></span></div></div></section></div>
  </>;
}

function Dashboard({ data, onNavigate }: { data: DashboardData; onNavigate: (area: Area) => void }) {
  const connected = data.vendors.filter((vendor) => vendor.status === 'connected').length;
  const enabled = data.policies.filter((policy) => policy.status === 'enabled').length;
  const triggerCount = Number(data.metrics.triggers.replace(/[^0-9]/g, '')) || 0;
  const severityCounts = (['critical', 'high', 'medium'] as Severity[]).map((severity) => ({ severity, count: data.policies.filter((policy) => policy.severity === severity).reduce((sum, policy) => sum + policy.triggers, 0) }));
  return <><div className="health-banner"><div className="health-pulse"><span /></div><div><strong>{data.vendors.some((vendor) => vendor.status === 'degraded') ? 'Attention required' : 'All systems operational'}</strong><span>Live status from the configured activity sources and policy engine.</span></div><span className="health-time">Current API data <Icon name="refresh" size={14} /></span></div><div className="metric-grid"><MetricCard label="Events processed" value={data.metrics.events} delta={data.metrics.eventsDelta} sub="reported by the API" icon="activity" tone="blue" /><MetricCard label="Active policies" value={`${enabled} / ${data.policies.length}`} delta="—" sub="from policy inventory" icon="shield" tone="purple" /><MetricCard label="Policy triggers" value={data.metrics.triggers} delta={data.metrics.triggerDelta} sub="reported by evaluations" icon="alert" tone="orange" /><MetricCard label="Avg. evaluation" value={data.metrics.latency} delta={data.metrics.latencyDelta} sub="from evaluation records" icon="bolt" tone="green" /></div><div className="dashboard-grid"><section className="panel panel-wide"><SectionHeader title="Policy activity" action="View policies" onAction={() => onNavigate('policies')} /><div className="empty-state"><Icon name="activity" size={22} /><strong>Event timeline is API-driven</strong><span>Use a connected vendor’s activity log to inspect received events. No fabricated chart data is displayed.</span></div></section><section className="panel"><SectionHeader title="Vendor health" action="Manage" onAction={() => onNavigate('vendors')} /><div className="health-list">{data.vendors.slice(0, 4).map((vendor) => <div className="health-item" key={vendor.id}><span className="vendor-mark" style={{ color: vendor.color }}>{vendor.icon}</span><div><strong>{vendor.name}</strong><span>{vendor.events} events</span></div><span className={`health-dot health-${vendor.status}`} title={vendor.status} /></div>)}</div><div className="panel-footer"><span>{connected} of {data.vendors.length} connections healthy</span><button onClick={() => onNavigate('vendors')} aria-label="View vendor health"><Icon name="arrow" size={16} /></button></div></section></div><div className="dashboard-grid lower-grid"><section className="panel panel-wide"><SectionHeader title="Recent activity" action="View audit log" /><ActivityFeed activity={data.activity} /></section><section className="panel"><SectionHeader title="Trigger distribution" /><div className="donut-wrap"><div className="donut"><div><strong>{triggerCount}</strong><span>triggers</span></div></div><div className="donut-legend">{severityCounts.map(({ severity, count }) => <span key={severity}><i className={`dot dot-${severity === 'critical' ? 'red' : severity === 'high' ? 'orange' : 'blue'}`} />{severity[0].toUpperCase() + severity.slice(1)} <b>{count}</b></span>)}</div></div></section></div></>;
}

function VendorCard({ vendor, onTest, onSelect }: { vendor: Vendor; onTest: () => void; onSelect: () => void }) {
  return <div className="vendor-card"><div className="vendor-card-top"><span className="vendor-mark vendor-mark-large" style={{ color: vendor.color }}>{vendor.icon}</span><button className="icon-button" aria-label={`More options for ${vendor.name}`}><Icon name="more" /></button></div><div className="vendor-card-name"><div><h3>{vendor.name}</h3><span>{vendor.category}</span></div><StatusBadge status={vendor.status} /></div><p>{vendor.description}</p><div className="vendor-card-stats"><div><span>Events ingested</span><strong>{vendor.events}</strong></div><div><span>Last event</span><strong>{vendor.lastEvent}</strong></div></div><div className="vendor-card-actions"><Button variant="secondary" icon="flask" onClick={onTest} disabled={vendor.status === 'testing'}>{vendor.status === 'testing' ? 'Testing…' : 'Test connection'}</Button><Button variant="ghost" icon="external" onClick={onSelect}>Details</Button></div></div>;
}

function Vendors({ vendors, onUpdate, onToast }: { vendors: Vendor[]; onUpdate: (vendors: Vendor[]) => void; onToast: (message: string) => void }) {
  const [showModal, setShowModal] = useState(false);
  const [selected, setSelected] = useState<Vendor | null>(null);
  useEffect(() => {
    if (!selected || apiConfig.isDemo || selected.id.startsWith('new-')) return;
    let active = true;
    const refresh = async () => {
      try {
        const events = await api.connectionEvents(selected.id, true);
        if (!active) return;
        const next = vendors.map((item) => item.id === selected.id ? { ...item, lastEvent: events.length ? 'just now' : 'No events yet', events: String(events.length), eventLog: events } : item);
        onUpdate(next);
        setSelected((current) => current && current.id === selected.id ? { ...current, lastEvent: events.length ? 'just now' : 'No events yet', events: String(events.length), eventLog: events } : current);
      } catch { /* The diagnostics shown from the last test remain visible. */ }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [selected?.id, apiConfig.isDemo]);
  const testVendor = async (vendor: Vendor) => {
    if (!apiConfig.isDemo && vendor.id === vendor.key) { setShowModal(true); onToast(`Configure ${vendor.name} before testing the connection`); return; }
    onUpdate(vendors.map((item) => item.id === vendor.id ? { ...item, status: 'testing' } : item));
    try { const result = apiConfig.isDemo ? { status: 'passed', checks: vendor.checks || [], remediation: vendor.remediation || null } : await api.testConnection(vendor.id); const events = apiConfig.isDemo ? (vendor.eventLog || []) : await api.connectionEvents(vendor.id); await new Promise((resolve) => setTimeout(resolve, 300)); onUpdate(vendors.map((item) => item.id === vendor.id ? { ...item, status: result.status === 'passed' ? 'connected' : 'degraded', lastEvent: events.length ? 'just now' : 'No events yet', events: String(events.length), checks: result.checks, remediation: result.remediation as Vendor['remediation'], eventLog: events } : item)); onToast(result.status === 'passed' ? `${vendor.name} connection verified` : `${vendor.name} needs attention`); }
    catch { onUpdate(vendors.map((item) => item.id === vendor.id ? { ...item, status: 'degraded' } : item)); onToast(`${vendor.name} needs attention`); }
  };
  return <>
    <div className="page-toolbar"><div className="filter-tabs"><button className="active">All <span>{vendors.length}</span></button><button>Connected <span>{vendors.filter((v) => v.status === 'connected').length}</span></button><button>Needs attention <span>{vendors.filter((v) => v.status === 'degraded').length}</span></button></div><Button variant="primary" icon="plus" onClick={() => setShowModal(true)}>Connect vendor</Button></div>
    {vendors.filter((vendor) => vendor.status === 'degraded').map((vendor) => <div className="callout callout-warning" key={`attention-${vendor.id}`}><span className="callout-icon"><Icon name="alert" size={17} /></span><div><strong>{vendor.name} needs attention</strong><span>{vendor.remediation?.summary || 'Review the connection diagnostics and required permissions.'}</span></div><button className="text-button" onClick={() => setSelected(vendor)}>Review issue <Icon name="arrow" size={14} /></button></div>)}
    <div className="vendor-grid">{vendors.map((vendor) => <VendorCard vendor={vendor} key={vendor.id} onTest={() => void testVendor(vendor)} onSelect={() => setSelected(vendor)} />)}<button className="add-card" onClick={() => setShowModal(true)}><span><Icon name="plus" size={22} /></span><strong>Connect GitHub</strong><small>Configure a real GitHub organization connection</small></button></div>
    {showModal && <ConnectModal onClose={() => setShowModal(false)} onConnect={async (vendor, payload) => { if (!apiConfig.isDemo) { try { const created = await api.createConnection<{ id: string }>(payload); const result = await api.testConnection(created.id); const blocking = (result.checks || []).some((check) => ['credentials', 'api_reachability', 'required_scopes'].includes(check.name) && check.status === 'failed'); if (!blocking) await api.enableConnection(created.id); const events = await api.connectionEvents(created.id); const saved: Vendor = { ...vendor, id: created.id, status: result.status === 'passed' ? 'connected' : 'degraded', lastEvent: events.length ? 'just now' : 'No events yet', events: String(events.length), checks: result.checks, remediation: result.remediation as Vendor['remediation'], eventLog: events }; onUpdate([...vendors, saved]); setSelected(saved); onToast(result.status === 'passed' ? `${vendor.name} connected successfully` : `${vendor.name} connected with limited event access — open diagnostics`); } catch (error) { onToast(error instanceof Error ? error.message : `${vendor.name} could not be connected`); } } else { onUpdate([...vendors, vendor]); setSelected(vendor); onToast(`${vendor.name} added in testing mode`); } setShowModal(false); }} />}
    {selected && <VendorDetail vendor={selected} onClose={() => setSelected(null)} onTest={() => { void testVendor(selected); setSelected(null); }} />}
  </>;
}

function ConnectModal({ onClose, onConnect }: { onClose: () => void; onConnect: (vendor: Vendor, payload: Record<string, unknown>) => Promise<void> | void }) {
  const [name, setName] = useState('');
  const [organization, setOrganization] = useState('');
  const [organizationUrl, setOrganizationUrl] = useState('https://github.com/');
  const [apiUrl, setApiUrl] = useState('https://api.github.com');
  const [token, setToken] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const key = 'github';
    void onConnect({ id: `new-${Date.now()}`, name: name || 'GitHub organization', key, category: 'Version control', description: 'GitHub organization and repository activity', status: 'testing', events: '—', lastEvent: 'Testing now', icon: 'GH', color: '#a78bfa', capabilities: ['Audit log', 'Webhooks', 'Repository events'] }, { vendor: key, name: name || `GitHub · ${organization}`, secret_ref: `openbao://workspace/${key}/${Date.now()}`, config: { organization, organization_url: organizationUrl, api_url: apiUrl, personal_access_token: token, token_last_four: token.slice(-4), webhook_secret: webhookSecret } });
  };
  return <Modal title="Connect GitHub" subtitle="Credentials are tested against the GitHub API" onClose={onClose}><form onSubmit={submit}><label>Connection name<input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Acme GitHub" autoFocus /></label><label>Organization name<input required value={organization} onChange={(e) => setOrganization(e.target.value)} placeholder="e.g. acme-inc" /></label><label>Organization URL<input required type="url" value={organizationUrl} onChange={(e) => setOrganizationUrl(e.target.value)} placeholder="https://github.com/acme-inc" /></label><label>GitHub API URL<input required type="url" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} placeholder="https://api.github.com" /></label><label>Personal access token<input required type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="ghp_…" /></label><label>Webhook secret <span className="muted">(optional)</span><input type="password" value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} placeholder="Only needed for signed webhooks" /></label><div className="form-note"><Icon name="shield" size={15} />The token is sent only to the backend secret store reference and is never returned to the browser.</div><div className="modal-actions"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" type="submit" icon="link">Test GitHub connection</Button></div></form></Modal>;
}

function LegacyVendorDetail({ vendor, onClose, onTest }: { vendor: Vendor; onClose: () => void; onTest: () => void }) {
  const checks: ConnectionCheck[] = vendor.checks || [];
  return <Modal title={vendor.name} subtitle="Connection diagnostics and activity" onClose={onClose}><div className="detail-head"><span className="vendor-mark vendor-mark-large" style={{ color: vendor.color }}>{vendor.icon}</span><div><StatusBadge status={vendor.status} /><p>Last checked {vendor.lastEvent}</p></div></div><div className="diagnostic-list">{checks.length ? checks.map((check) => <div key={check.name}><span>{check.name.replaceAll('_', ' ')}</span><span className={`diagnostic-${check.status}`}><Icon name={check.status === 'passed' ? 'check' : check.status === 'failed' ? 'alert' : 'clock'} size={14} />{check.status}{check.message ? ` · ${check.message}` : ''}</span></div>) : <div className="empty-state"><span>No connection test has been run.</span></div>}</div>{vendor.remediation && <div className="remediation"><strong>Remediation</strong><p>{vendor.remediation.summary}</p><ul>{vendor.remediation.steps.map((step) => <li key={step}>{step}</li>)}</ul><small>Suggested test: {vendor.remediation.test_actions.join(' ')}</small></div>}<div className="event-log"><div className="section-header"><h3>Recent GitHub activity</h3><span>{vendor.eventLog?.length || 0} events</span></div>{vendor.eventLog?.length ? vendor.eventLog.map((event) => <div className="event-log-row" key={event.event_id}><span className="live-dot" /><div><strong>{event.event_type}</strong><span>{event.actor?.name || event.actor?.id || 'Unknown actor'} · {event.resource?.name || 'Unknown repository'}</span></div><time>{new Date(event.occurred_at).toLocaleString()}</time></div>) : <div className="empty-state"><span>No events have been received yet. Perform the suggested GitHub activity and re-test.</span></div>}</div><div className="modal-actions"><Button variant="primary" icon="refresh" onClick={onTest}>Re-test connection</Button></div></Modal>;
}

function VendorDetail({ vendor, onClose, onTest }: { vendor: Vendor; onClose: () => void; onTest: () => void }) {
  const [repositories, setRepositories] = useState<RepositorySummary[]>(vendor.repositories || []);
  useEffect(() => {
    if (apiConfig.isDemo || vendor.id.startsWith('new-')) return;
    let active = true;
    void api.connectionRepositories(vendor.id).then((items) => { if (active) setRepositories(items); }).catch(() => undefined);
    return () => { active = false; };
  }, [vendor.id]);
  const checks: ConnectionCheck[] = vendor.checks || [];
  return <Modal title={vendor.name} subtitle="API-backed connection diagnostics, repositories, and activity" onClose={onClose}><div className="detail-head"><span className="vendor-mark vendor-mark-large" style={{ color: vendor.color }}>{vendor.icon}</span><div><StatusBadge status={vendor.status} /><p>Last checked {vendor.lastEvent}</p></div></div><div className="diagnostic-list">{checks.length ? checks.map((check) => <div key={check.name}><span>{check.name.replaceAll('_', ' ')}</span><span className={`diagnostic-${check.status}`}><Icon name={check.status === 'passed' ? 'check' : check.status === 'failed' ? 'alert' : 'clock'} size={14} />{check.status}{check.message ? ` · ${check.message}` : ''}</span></div>) : <div className="empty-state"><span>No connection test has been run.</span></div>}</div>{vendor.remediation && <div className="remediation"><strong>Remediation</strong><p>{vendor.remediation.summary}</p><ul>{vendor.remediation.steps.map((step) => <li key={step}>{step}</li>)}</ul><small>Suggested test: {vendor.remediation.test_actions.join(' ')}</small></div>}<div className="repository-list"><div className="section-header"><h3>Accessible repositories</h3><span>{repositories.length}</span></div>{repositories.length ? repositories.map((repository) => <div className="repository-row" key={repository.id || repository.full_name}><Icon name="link" size={14} /><div><strong>{repository.full_name || repository.name}</strong><span>{repository.source || 'GitHub'} · {repository.private ? 'Private' : 'Public'}</span></div>{repository.html_url && <a href={repository.html_url} target="_blank" rel="noreferrer"><Icon name="external" size={14} /></a>}</div>) : <div className="empty-state"><span>No accessible repositories were returned by GitHub.</span></div>}</div><div className="event-log"><div className="section-header"><h3>Recent GitHub activity</h3><span>{vendor.eventLog?.length || 0} events</span></div>{vendor.eventLog?.length ? vendor.eventLog.map((event) => <div className="event-log-row" key={event.event_id}><span className="live-dot" /><div><strong>{event.event_type}</strong><span>{event.actor?.name || event.actor?.id || 'Unknown actor'} · {event.resource?.name || 'Unknown repository'}</span></div><time>{new Date(event.occurred_at).toLocaleString()}</time></div>) : <div className="empty-state"><span>No events have been received yet. Push a commit or fork a repository, then re-test.</span></div>}</div><div className="modal-actions"><Button variant="primary" icon="refresh" onClick={onTest}>Re-test connection</Button></div></Modal>;
}

function Modal({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: React.ReactNode }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-head"><div><h2 id="modal-title">{title}</h2>{subtitle && <span>{subtitle}</span>}</div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="x" /></button></div>{children}</div></div>;
}

function AgentLive({ onToast, onDeploy }: { onToast: (message: string) => void; onDeploy: (policy: Policy) => void }) {
  const [prompt, setPrompt] = useState('');
  const [stage, setStage] = useState<'prompt' | 'generated' | 'tested'>('prompt');
  const [severity, setSeverity] = useState<Severity>('high');
  const [draftId, setDraftId] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<PolicyArtifact | null>(null);
  const [testRun, setTestRun] = useState<PolicyTestRun | null>(null);
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    if (!prompt.trim() || apiConfig.isDemo) { onToast('Configure the API URL to generate a real policy artifact'); return; }
    setBusy(true);
    try {
      const draft = await api.generatePolicy<{ id: string }>({ prompt, vendor: 'github', severity });
      const generated = await api.generateDraft<{ artifact: PolicyArtifact }>(draft.id);
      setDraftId(draft.id); setArtifact(generated.artifact); setTestRun(null); setStage('generated'); onToast('Policy artifact generated by the API');
    } catch (error) { onToast(error instanceof Error ? error.message : 'Policy generation failed'); }
    finally { setBusy(false); }
  };

  const runTests = async () => {
    if (!draftId) return;
    setBusy(true);
    try {
      const result = await api.testDraft<PolicyTestRun>(draftId);
      setTestRun(result);
      if (result.status === 'passed') { setStage('tested'); onToast('All mandatory scenarios passed'); }
      else onToast('Policy test failed; review the scenario results');
    } catch (error) { onToast(error instanceof Error ? error.message : 'Policy test failed'); }
    finally { setBusy(false); }
  };

  const deploy = async () => {
    if (!draftId || !testRun || testRun.status !== 'passed' || !artifact) return;
    setBusy(true);
    try {
      const response = await api.deployDraft<{ policy: { id: string; name: string; vendor: string; severity: Severity; version: number } }>(draftId);
      onDeploy({ id: response.policy.id, name: response.policy.name, description: artifact.summary, version: `v${response.policy.version}`, status: 'enabled', severity: response.policy.severity, source: response.policy.vendor, evaluations: '0', triggers: 0, lastTrigger: 'Never', latency: '—' });
    } catch (error) { onToast(error instanceof Error ? error.message : 'Policy deployment failed'); }
    finally { setBusy(false); }
  };

  return <div className="agent-layout"><section className="agent-main"><div className="agent-stepper"><span className="step-active"><b>1</b> Describe</span><i /><span className={stage !== 'prompt' ? 'step-active' : ''}><b>2</b> Review</span><i /><span className={stage === 'tested' ? 'step-active' : ''}><b>3</b> Test & deploy</span></div><div className="agent-card"><div className="agent-card-head"><div className="agent-orb"><Icon name="spark" size={21} /></div><div><h2>What should this policy detect?</h2><p>Describe the risk in plain language. The backend will generate a deterministic, testable policy artifact.</p></div></div><label className="prompt-label">Risk scenario<textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={5} placeholder="Describe the GitHub activity or risk you want to detect…" /></label><div className="prompt-footer"><span>{prompt.length} / 2,000 characters</span><span><Icon name="shield" size={14} /> Submitted to the configured policy API</span></div><div className="agent-options"><label>Event source<select><option>GitHub · repository and audit events</option></select></label><label>Severity<select value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label></div><div className="agent-actions"><Button variant="primary" icon="spark" onClick={() => void generate()} disabled={busy || !prompt.trim()}>{busy ? 'Working…' : stage === 'prompt' ? 'Generate policy' : 'Regenerate policy'}</Button></div></div>{stage !== 'prompt' && artifact && <LivePolicyDraft artifact={artifact} testRun={testRun} stage={stage} onTest={() => void runTests()} onDeploy={() => void deploy()} busy={busy} />}</section><aside className="agent-aside"><div className="aside-card"><div className="aside-title"><Icon name="spark" size={16} />How it works</div><div className="how-step"><span>01</span><div><strong>Describe</strong><p>Explain the activity and any exceptions.</p></div></div><div className="how-step"><span>02</span><div><strong>Review</strong><p>Inspect the returned artifact, assumptions, and hash.</p></div></div><div className="how-step"><span>03</span><div><strong>Test</strong><p>Every mandatory API scenario must pass before deploy.</p></div></div></div></aside></div>;
}

function LivePolicyDraft({ artifact, testRun, stage, onTest, onDeploy, busy }: { artifact: PolicyArtifact; testRun: PolicyTestRun | null; stage: 'generated' | 'tested'; onTest: () => void; onDeploy: () => void; busy: boolean }) {
  return <div className="draft-card"><div className="draft-head"><div><div className="draft-label"><Badge tone="purple">API artifact</Badge><span>SHA-256 {artifact.source_sha256.slice(0, 12)}…</span></div><h2>{artifact.policy_name}</h2><p>{artifact.summary}</p></div></div><div className="draft-meta"><span><Icon name="terminal" size={14} /> Python policy</span><span><Icon name="shield" size={14} /> {artifact.severity} severity</span><span><Icon name="clock" size={14} /> {artifact.test_cases.length} scenarios returned</span></div><div className="code-preview"><div className="code-head"><span><i /> <i /> <i /> policy.py</span><span>Read-only artifact</span></div><pre><code>{artifact.python_source}</code></pre></div><div className="assumptions"><Icon name="alert" size={16} /><div><strong>Backend assumptions</strong>{artifact.assumptions.map((assumption) => <span key={assumption}>{assumption}</span>)}</div></div><div className="test-summary"><div><strong>{testRun ? `${testRun.summary.passed} / ${testRun.summary.total}` : 'Ready to test'}</strong><span>mandatory scenarios</span></div><div className="test-progress"><span style={{ width: testRun ? `${(testRun.summary.passed / Math.max(testRun.summary.total, 1)) * 100}%` : '0%' }} /></div>{testRun ? <Badge tone={testRun.status === 'passed' ? 'success' : 'danger'}>{testRun.status === 'passed' ? 'All passed' : 'Failed'}</Badge> : <Button variant="secondary" icon="flask" onClick={onTest} disabled={busy}>Run API test suite</Button>}</div>{testRun && <div className="test-results">{testRun.results.map((result) => <div key={result.case_name}><span className={`result-check ${result.passed ? '' : 'result-failed'}`}><Icon name={result.passed ? 'check' : 'alert'} size={13} /></span><span>{result.case_name}</span><Badge tone={result.passed ? 'success' : 'danger'}>{result.passed ? 'Passed' : 'Failed'}</Badge></div>)}</div>}<div className="draft-footer"><span><Icon name="check" size={14} /> {stage === 'tested' && testRun?.status === 'passed' ? 'Validated and ready to deploy' : 'Draft requires a passing API test run'}</span><Button variant="primary" icon="rocket" disabled={busy || stage !== 'tested' || testRun?.status !== 'passed'} onClick={onDeploy}>Deploy policy</Button></div></div>;
}

function Policies({ policies, onToggle, onToast }: { policies: Policy[]; onToggle: (policy: Policy) => void; onToast: (message: string) => void }) {
  const [query, setQuery] = useState('');
  const filtered = policies.filter((policy) => `${policy.name} ${policy.source} ${policy.severity}`.toLowerCase().includes(query.toLowerCase()));
  const totalEvaluations = policies.reduce((sum, policy) => sum + (Number(policy.evaluations.replace(/[^0-9.]/g, '')) * (policy.evaluations.includes('k') ? 1000 : 1) || 0), 0);
  const totalTriggers = policies.reduce((sum, policy) => sum + policy.triggers, 0);
  const activeCoverage = policies.length ? Math.round((policies.filter((policy) => policy.status === 'enabled').length / policies.length) * 1000) / 10 : 0;
  return <><div className="page-toolbar"><div className="search-input"><Icon name="search" size={16} /><input placeholder="Search policies" value={query} onChange={(e) => setQuery(e.target.value)} /></div><div className="toolbar-actions"><Button variant="secondary" icon="filter">Filter <span className="button-count">{policies.length}</span></Button><Button variant="secondary" icon="refresh" onClick={() => onToast('Policy data refreshed')}>Refresh</Button></div></div><div className="policy-overview"><div><span>Active coverage</span><strong>{activeCoverage}%</strong><small>based on enabled policies</small></div><div><span>Events evaluated</span><strong>{totalEvaluations.toLocaleString()}</strong><small>across connected sources</small></div><div><span>Open triggers</span><strong>{totalTriggers}</strong><small>from current policy inventory</small></div><div className="policy-mini-chart"><span>Evaluation health</span><div className="mini-bars">{[38, 48, 41, 65, 54, 78, 65, 89, 76, 83, 94, 88].map((height, i) => <i key={i} style={{ height: `${height}%` }} />)}</div></div></div><section className="panel table-panel"><div className="table-head"><div><h2>Policy inventory</h2><span>{filtered.length} policies in this workspace</span></div><button className="icon-button"><Icon name="sliders" /></button></div><div className="table-scroll"><table><thead><tr><th>Policy</th><th>Source</th><th>Severity</th><th>Status</th><th>Evaluations</th><th>Triggers</th><th>Last evaluation</th><th /></tr></thead><tbody>{filtered.map((policy) => <tr key={policy.id}><td><div className="policy-name"><span className={`policy-shield severity-${policy.severity}`}><Icon name="shield" size={16} /></span><div><strong>{policy.name}</strong><span>{policy.version} · {policy.description}</span></div></div></td><td><span className="source-cell"><i className="source-dot" />{policy.source}</span></td><td><span className={`severity-text severity-text-${policy.severity}`}>{policy.severity}</span></td><td><StatusBadge status={policy.status} /></td><td className="mono">{policy.evaluations}</td><td className={policy.triggers > 0 ? 'trigger-count' : ''}>{policy.triggers}</td><td><span className="last-eval"><i className={policy.status === 'enabled' ? 'live-dot' : ''} />{policy.lastTrigger}</span></td><td><button className="icon-button" aria-label={`Open ${policy.name}`} onClick={() => onToggle(policy)}><Icon name="more" /></button></td></tr>)}</tbody></table>{filtered.length === 0 && <div className="empty-state"><Icon name="search" size={22} /><strong>No policies match</strong><span>Try a different search term.</span></div>}</div></section></>;
}

function Actions({ actions, onUpdate, onToast }: { actions: ActionDefinition[]; onUpdate: (actions: ActionDefinition[]) => void; onToast: (message: string) => void }) {
  const [showModal, setShowModal] = useState(false); const [history, setHistory] = useState(true);
  const toggle = (action: ActionDefinition) => { onUpdate(actions.map((item) => item.id === action.id ? { ...item, status: item.status === 'active' ? 'paused' : 'active' } : item)); onToast(`${action.name} ${action.status === 'active' ? 'paused' : 'activated'}`); };
  const save = async (action: ActionDefinition) => { if (!apiConfig.isDemo) { try { const type = action.type === 'MFA challenge' ? 'mfa' : action.type.toLowerCase(); const mode = action.mode === 'Require approval' ? 'approval' : action.mode === 'Dry-run' ? 'dry_run' : 'automatic'; const created = await api.createAction<{ id: string }>({ name: action.name, action_type: type, mode, provider: action.provider }); onUpdate([...actions, { ...action, id: created.id }]); } catch { onToast('Action could not be saved'); return; } } else onUpdate([...actions, action]); setShowModal(false); onToast(`${action.name} configured`); };
  return <><div className="page-toolbar"><div className="filter-tabs"><button className="active">All <span>{actions.length}</span></button><button>Active <span>{actions.filter((a) => a.status === 'active').length}</span></button><button>Paused <span>{actions.filter((a) => a.status === 'paused').length}</span></button></div><Button variant="primary" icon="plus" onClick={() => setShowModal(true)}>Configure action</Button></div><div className="action-grid">{actions.map((action) => <div className="action-card" key={action.id}><div className="action-card-top"><span className="action-type" style={{ color: action.color }}><Icon name={action.type === 'Escalate' ? 'bolt' : action.type === 'MFA challenge' ? 'shield' : action.type === 'Block' ? 'alert' : 'check'} size={18} /></span><div className="action-card-menu"><StatusBadge status={action.status === 'active' ? 'enabled' : 'disabled'} /><button className="icon-button"><Icon name="more" /></button></div></div><h3>{action.name}</h3><p>{action.type} · {action.provider}</p><div className="action-details"><span><small>Mode</small><strong>{action.mode}</strong></span><span><small>Executions</small><strong>{action.executions}</strong></span></div><div className="action-card-footer"><span><i className={action.status === 'active' ? 'live-dot' : 'paused-dot'} />{action.status === 'active' ? 'Ready to execute' : 'Paused'}</span><button className="switch" onClick={() => toggle(action)} aria-label={`${action.status === 'active' ? 'Pause' : 'Activate'} ${action.name}`}><span className={action.status === 'active' ? 'on' : ''} /></button></div></div>)}<button className="add-card action-add" onClick={() => setShowModal(true)}><span><Icon name="plus" size={22} /></span><strong>Create a response action</strong><small>Block, MFA, escalate, or allow</small></button></div><section className="panel action-history"><div className="table-head"><div><h2>Configured actions</h2><span>Source-of-truth action definitions</span></div><button className="text-button" onClick={() => setHistory(!history)}>{history ? 'Hide list' : 'Show list'} <Icon name="chevron" size={14} /></button></div>{history && <div className="execution-list">{actions.map((action) => <div className="execution-row" key={`configured-${action.id}`}><span className={`execution-icon execution-${action.status === 'active' ? 'success' : 'warning'}`}><Icon name={action.status === 'active' ? 'check' : 'clock'} size={15} /></span><div><strong>{action.name}</strong><span>{action.provider} · {action.mode}</span></div><Badge tone={action.status === 'active' ? 'success' : 'warning'}>{action.status === 'active' ? 'Ready' : 'Paused'}</Badge><time>{action.executions} executions</time><button className="icon-button"><Icon name="external" size={15} /></button></div>)}</div>}</section>{showModal && <ActionModal onClose={() => setShowModal(false)} onSave={(action) => void save(action)} />}</>;
}

function LegacyActionModal({ onClose, onSave }: { onClose: () => void; onSave: (action: ActionDefinition) => void }) {
  const [name, setName] = useState(''); const [type, setType] = useState<ActionDefinition['type']>('Escalate'); const [mode, setMode] = useState<ActionDefinition['mode']>('Require approval');
  return <Modal title="Configure response action" subtitle="Actions are scoped to this workspace" onClose={onClose}><form onSubmit={(event) => { event.preventDefault(); onSave({ id: `action-${Date.now()}`, name: name || 'New response action', type, provider: type === 'Escalate' ? 'Email · security@acme.io' : 'Select a provider', mode, status: 'active', executions: 0, color: type === 'Escalate' ? '#a78bfa' : '#4ade80' }); }}><label>Action name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Notify security team" autoFocus /></label><label>Response type<select value={type} onChange={(e) => setType(e.target.value as ActionDefinition['type'])}><option>Escalate</option><option>Block</option><option>MFA challenge</option><option>Allow</option></select></label><label>Execution mode<select value={mode} onChange={(e) => setMode(e.target.value as ActionDefinition['mode'])}><option>Require approval</option><option>Automatic</option><option>Dry-run</option></select></label><div className="form-note"><Icon name="bolt" size={15} />Every execution is idempotent and recorded in the audit trail.</div><div className="modal-actions"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" type="submit" icon="check">Save action</Button></div></form></Modal>;
}

function ActionModal({ onClose, onSave }: { onClose: () => void; onSave: (action: ActionDefinition) => void }) {
  const [name, setName] = useState('');
  const [type, setType] = useState<ActionDefinition['type']>('Escalate');
  const [mode, setMode] = useState<ActionDefinition['mode']>('Require approval');
  const [provider, setProvider] = useState('');
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    onSave({ id: `action-${Date.now()}`, name: name.trim(), type, provider: provider.trim() || 'Not configured', mode, status: 'active', executions: 0, color: type === 'Escalate' ? '#a78bfa' : '#4ade80' });
  };
  return <Modal title="Configure response action" subtitle="Actions are scoped to this workspace" onClose={onClose}><form onSubmit={submit}><label>Action name<input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Notify security team" autoFocus /></label><label>Response type<select value={type} onChange={(e) => setType(e.target.value as ActionDefinition['type'])}><option>Escalate</option><option>Block</option><option>MFA challenge</option><option>Allow</option></select></label><label>Execution mode<select value={mode} onChange={(e) => setMode(e.target.value as ActionDefinition['mode'])}><option>Require approval</option><option>Automatic</option><option>Dry-run</option></select></label><label>Provider reference<input value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="e.g. SMTP or webhook reference" /></label><div className="form-note"><Icon name="bolt" size={15} />Execution is recorded in the audit trail after a provider is configured.</div><div className="modal-actions"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" type="submit" icon="check">Save action</Button></div></form></Modal>;
}

export default function App() {
  const [area, setArea] = useState<Area>('dashboard');
  const [data, setData] = useState<DashboardData>(demoData);
  const [demo, setDemo] = useState(apiConfig.isDemo); const [loading, setLoading] = useState(true); const [toast, setToast] = useState(''); const [mobileNav, setMobileNav] = useState(false);
  useEffect(() => { void getDashboard().then(({ data: next, demo: fallback }) => { setData(next); setDemo(fallback); setLoading(false); }).catch(() => { setData({ vendors: [], policies: [], actions: [], activity: [], metrics: { events: '0', eventsDelta: '—', triggers: '0', triggerDelta: '—', latency: '—', latencyDelta: '—' } }); setDemo(false); setLoading(false); setToast('The policy API could not be reached; no fallback records were loaded.'); }); }, []);
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(''), 3000); return () => window.clearTimeout(timer); }, [toast]);
  const copy = pageCopy[area];
  const updateVendors = (vendors: Vendor[]) => setData((current) => ({ ...current, vendors }));
  const updateActions = (actions: ActionDefinition[]) => setData((current) => ({ ...current, actions }));
  const deployPolicy = (policy: Policy) => { setData((current) => ({ ...current, policies: [policy, ...current.policies] })); setArea('policies'); setToast('Policy deployment started'); };
  const togglePolicy = async (policy: Policy) => { const enabled = policy.status !== 'enabled'; if (!apiConfig.isDemo) { try { await api.togglePolicy(policy.id, enabled); } catch { setToast('Policy change could not be saved'); return; } } setData((current) => ({ ...current, policies: current.policies.map((item) => item.id === policy.id ? { ...item, status: enabled ? 'enabled' : 'disabled' } : item) })); setToast(`${policy.name} ${enabled ? 'enabled' : 'disabled'}`); };
  const content = useMemo(() => {
    if (loading) return <LoadingState />;
    if (area === 'dashboard') return <Dashboard data={data} onNavigate={setArea} />;
    if (area === 'vendors') return <Vendors vendors={data.vendors} onUpdate={updateVendors} onToast={setToast} />;
    if (area === 'agent') return <AgentLive onToast={setToast} onDeploy={deployPolicy} />;
    if (area === 'policies') return <Policies policies={data.policies} onToggle={(policy) => void togglePolicy(policy)} onToast={setToast} />;
    return <Actions actions={data.actions} onUpdate={updateActions} onToast={setToast} />;
  }, [area, data, loading]);
  return <div className="app-shell"><aside className={`sidebar ${mobileNav ? 'mobile-open' : ''}`}><div className="brand"><span className="brand-mark"><Icon name="shield" size={20} /></span><span>sentinel</span><button className="mobile-close icon-button" onClick={() => setMobileNav(false)}><Icon name="x" /></button></div><div className="workspace-switch"><span className="workspace-avatar">A</span><div><strong>Acme Inc.</strong><small>Security workspace</small></div><Icon name="chevron" size={14} /></div><nav><span className="nav-label">Workspace</span>{navItems.map((item) => <button key={item.id} className={`nav-item ${area === item.id ? 'active' : ''}`} onClick={() => { setArea(item.id); setMobileNav(false); }}><Icon name={item.icon} size={18} /><span>{item.label}</span>{item.hint && <small className={item.hint === 'AI' ? 'ai-hint' : ''}>{item.hint}</small>}</button>)}</nav><div className="sidebar-bottom"><div className="sidebar-status"><span className="live-dot" /><div><strong>System healthy</strong><small>All services operational</small></div></div><button className="nav-item"><Icon name="settings" size={18} /><span>Settings</span></button><div className="user-row"><span className="user-avatar">AC</span><div><strong>Alex Chen</strong><small>Administrator</small></div><Icon name="more" size={17} /></div></div></aside><main className="main"><header className="topbar"><button className="mobile-menu icon-button" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Icon name="grid" /></button><div className="breadcrumbs"><span>Workspace</span><Icon name="chevron" size={13} /><strong>{copy.title === 'Good morning, Alex' ? 'Overview' : copy.title}</strong></div><div className="top-actions"><div className="global-search"><Icon name="search" size={17} /><span>Search anything</span><kbd>⌘ K</kbd></div><button className="icon-button notification" aria-label="Notifications"><Icon name="bell" size={18} /><i /></button><div className="top-user">AC<Icon name="chevron" size={13} /></div></div></header><div className="content"><div className="page-heading"><div><span className="eyebrow">{copy.eyebrow}</span><h1>{copy.title}</h1><p>{copy.description}</p></div><div className="heading-meta">{demo && <span className="demo-pill"><span />Demo workspace · seeded records</span>}<span className="last-sync"><Icon name="clock" size={14} />Synced just now</span></div></div>{content}</div></main>{toast && <div className="toast"><span><Icon name="check" size={15} /></span>{toast}<button onClick={() => setToast('')} aria-label="Dismiss notification"><Icon name="x" size={14} /></button></div>}</div>;
}

function LoadingState() { return <div className="loading-state"><div className="loading-spinner" /><strong>Loading workspace</strong><span>Connecting to the policy control plane…</span></div>; }
