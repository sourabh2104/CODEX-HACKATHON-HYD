import { demoData } from './demo';
import type { ActivityEvent, ConnectionCheck, DashboardData } from '../types';

const configuredBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '');

export const apiConfig = {
  baseUrl: configuredBaseUrl || '',
  isDemo: !configuredBaseUrl,
};

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!apiConfig.baseUrl) throw new Error('Demo mode is active');
  const response = await fetch(`${apiConfig.baseUrl}${path}`, {
    ...init,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export async function getDashboard(): Promise<{ data: DashboardData; demo: boolean }> {
  if (apiConfig.isDemo) return { data: demoData, demo: true };
  const data = await request<DashboardData>('/api/v1/dashboard');
  return { data, demo: Boolean(data.demo) };
}

export const api = {
  testConnection: (id: string) => request<{ status: string; checks?: ConnectionCheck[]; remediation?: Record<string, unknown> }>(`/api/v1/connections/${id}/test`, { method: 'POST' }),
  connectionEvents: (id: string, refresh = false) => request<ActivityEvent[]>(`/api/v1/connections/${id}/events${refresh ? '?refresh=true' : ''}`),
  enableConnection: (id: string) => request(`/api/v1/connections/${id}/enable`, { method: 'POST' }),
  createConnection: <T = Record<string, unknown>>(payload: unknown) => request<T>('/api/v1/connections', { method: 'POST', body: JSON.stringify(payload) }),
  generatePolicy: <T = { id: string }>(payload: unknown) => request<T>('/api/v1/policy-drafts', { method: 'POST', body: JSON.stringify(payload) }),
  generateDraft: <T = Record<string, unknown>>(id: string) => request<T>(`/api/v1/policy-drafts/${id}/generate`, { method: 'POST' }),
  testDraft: <T = Record<string, unknown>>(id: string) => request<T>(`/api/v1/policy-drafts/${id}/test`, { method: 'POST' }),
  deployDraft: <T = Record<string, unknown>>(id: string) => request<T>(`/api/v1/policy-drafts/${id}/deploy`, { method: 'POST' }),
  togglePolicy: (id: string, enabled: boolean) => request(`/api/v1/policies/${id}/${enabled ? 'enable' : 'disable'}`, { method: 'POST' }),
  createAction: <T = Record<string, unknown>>(payload: unknown) => request<T>('/api/v1/actions', { method: 'POST', body: JSON.stringify(payload) }),
};
