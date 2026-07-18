import { describe, expect, it } from 'vitest';
import { demoData } from './demo';

describe('demo workspace fixtures', () => {
  it('contains the core operational areas', () => {
    expect(demoData.vendors.length).toBeGreaterThanOrEqual(3);
    expect(demoData.policies.some((policy) => policy.status === 'enabled')).toBe(true);
    expect(demoData.actions.some((action) => action.mode === 'Require approval')).toBe(true);
    expect(demoData.activity.length).toBeGreaterThan(0);
  });

  it('keeps degraded vendor state visible for remediation flows', () => {
    const degraded = demoData.vendors.find((vendor) => vendor.status === 'degraded');
    expect(degraded?.name).toBe('Okta Workforce');
    expect(degraded?.capabilities).toContain('System log');
  });
});
