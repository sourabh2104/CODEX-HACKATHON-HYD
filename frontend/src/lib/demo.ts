import type { DashboardData, Vendor, Policy, ActionDefinition, Activity } from '../types';

export const demoVendors: Vendor[] = [
  { id: 'github', name: 'GitHub Enterprise', key: 'github', category: 'Version control', description: 'Repository and organization activity', status: 'connected', events: '18.4k', lastEvent: '24 sec ago', icon: 'GH', color: '#a78bfa', capabilities: ['Audit log', 'Webhooks', 'Repository events'] },
  { id: 'aws', name: 'AWS CloudTrail', key: 'aws', category: 'Cloud infrastructure', description: 'Management and data events', status: 'connected', events: '9.8k', lastEvent: '2 min ago', icon: 'AWS', color: '#f5a524', capabilities: ['Management events', 'Data events', 'Insights'] },
  { id: 'okta', name: 'Okta Workforce', key: 'okta', category: 'Identity', description: 'Sign-ins and identity lifecycle', status: 'degraded', events: '3.1k', lastEvent: '18 min ago', icon: 'O', color: '#48a7ff', capabilities: ['System log', 'Sign-in events', 'Lifecycle events'] },
  { id: 'jira', name: 'Jira Cloud', key: 'jira', category: 'Project management', description: 'Issue and project activity', status: 'disabled', events: '—', lastEvent: 'Never', icon: 'J', color: '#579dff', capabilities: ['Issue events', 'Project events', 'Webhooks'] },
];

export const demoPolicies: Policy[] = [
  { id: 'p-1', name: 'After-hours repository access', description: 'Detects repository activity outside the approved operating window.', version: 'v1.4', status: 'enabled', severity: 'high', source: 'GitHub', evaluations: '12,402', triggers: 34, lastTrigger: '8 min ago', latency: '42 ms' },
  { id: 'p-2', name: 'Unusual admin console login', description: 'Flags privileged sign-ins from new locations or unmanaged devices.', version: 'v2.1', status: 'enabled', severity: 'critical', source: 'AWS · Okta', evaluations: '8,932', triggers: 7, lastTrigger: '1 hr ago', latency: '58 ms' },
  { id: 'p-3', name: 'Production branch protection', description: 'Blocks direct pushes to protected production branches.', version: 'v1.0', status: 'warning', severity: 'medium', source: 'GitHub', evaluations: '5,124', triggers: 12, lastTrigger: '3 hr ago', latency: '31 ms' },
  { id: 'p-4', name: 'Dormant credential use', description: 'Monitors service credentials that return to activity after an idle period.', version: 'v0.9', status: 'disabled', severity: 'high', source: 'AWS', evaluations: '—', triggers: 0, lastTrigger: 'Never', latency: '—' },
];

export const demoActions: ActionDefinition[] = [
  { id: 'a-1', name: 'Revoke session', type: 'Block', provider: 'Okta Workforce', mode: 'Require approval', status: 'active', executions: 18, color: '#f87171' },
  { id: 'a-2', name: 'Security escalation', type: 'Escalate', provider: 'Email · security@acme.io', mode: 'Automatic', status: 'active', executions: 42, color: '#a78bfa' },
  { id: 'a-3', name: 'Step-up authentication', type: 'MFA challenge', provider: 'Okta Workforce', mode: 'Automatic', status: 'active', executions: 11, color: '#4ade80' },
  { id: 'a-4', name: 'Quarantine repository', type: 'Block', provider: 'GitHub Enterprise', mode: 'Dry-run', status: 'paused', executions: 0, color: '#f5a524' },
];

export const demoActivity: Activity[] = [
  { id: 'e1', title: 'Policy triggered', detail: 'After-hours repository access · alice@acme.io', time: '8 min ago', tone: 'danger', icon: 'shield' },
  { id: 'e2', title: 'Action approved', detail: 'Revoke session · review by M. Chen', time: '11 min ago', tone: 'success', icon: 'check' },
  { id: 'e3', title: 'Connector degraded', detail: 'Okta Workforce · missing System Log scope', time: '18 min ago', tone: 'warning', icon: 'link' },
  { id: 'e4', title: 'Policy deployed', detail: 'Unusual admin console login · v2.1', time: '1 hr ago', tone: 'neutral', icon: 'rocket' },
  { id: 'e5', title: 'Test suite passed', detail: 'Production branch protection · 6 scenarios', time: '2 hr ago', tone: 'success', icon: 'flask' },
];

export const demoData: DashboardData = {
  vendors: demoVendors,
  policies: demoPolicies,
  actions: demoActions,
  activity: demoActivity,
  metrics: { events: '31,276', eventsDelta: '+12.8%', triggers: '53', triggerDelta: '+4.2%', latency: '46 ms', latencyDelta: '-8.1%' },
};
