export type Area = 'dashboard' | 'vendors' | 'agent' | 'policies' | 'actions';
export type Severity = 'low' | 'medium' | 'high' | 'critical';

export interface ConnectionCheck { name: string; status: string; code?: string; message?: string; }
export interface ActivityEvent { event_id: string; event_type: string; occurred_at: string; actor?: { id?: string | null; name?: string | null }; resource?: { name?: string | null }; }
export interface PolicyTestCase { name: string; input_event: Record<string, unknown>; expected_matched: boolean; mandatory?: boolean; scenario_type?: string; }
export interface PolicyArtifact { policy_name: string; summary: string; assumptions: string[]; severity: Severity; python_source: string; source_sha256: string; test_cases: PolicyTestCase[]; }
export interface PolicyTestResult { case_name: string; expected_matched: boolean; actual_matched?: boolean | null; passed: boolean; reason_code?: string | null; explanation?: string | null; error?: string | null; }
export interface PolicyTestRun { status: 'passed' | 'failed'; results: PolicyTestResult[]; summary: { total: number; passed: number; failed: number }; }

export interface Vendor {
  id: string;
  name: string;
  key: string;
  category: string;
  description: string;
  status: 'connected' | 'degraded' | 'disabled' | 'testing';
  events: string;
  lastEvent: string;
  icon: string;
  color: string;
  capabilities: string[];
  checks?: ConnectionCheck[];
  remediation?: { summary: string; steps: string[]; test_actions: string[] } | null;
  eventLog?: ActivityEvent[];
}

export interface Policy {
  id: string;
  name: string;
  description: string;
  version: string;
  status: 'enabled' | 'disabled' | 'deploying' | 'warning';
  severity: Severity;
  source: string;
  evaluations: string;
  triggers: number;
  lastTrigger: string;
  latency: string;
}

export interface ActionDefinition {
  id: string;
  name: string;
  type: 'Block' | 'MFA challenge' | 'Escalate' | 'Allow';
  provider: string;
  mode: 'Automatic' | 'Require approval' | 'Dry-run';
  status: 'active' | 'paused';
  executions: number;
  color: string;
}

export interface Activity {
  id: string;
  title: string;
  detail: string;
  time: string;
  tone: 'success' | 'warning' | 'danger' | 'neutral';
  icon: string;
}

export interface DashboardData {
  demo?: boolean;
  vendors: Vendor[];
  policies: Policy[];
  actions: ActionDefinition[];
  activity: Activity[];
  metrics: { events: string; eventsDelta: string; triggers: string; triggerDelta: string; latency: string; latencyDelta: string };
}
