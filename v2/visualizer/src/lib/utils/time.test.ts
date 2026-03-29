import { describe, it, expect } from 'vitest';
import { dateInTz, formatTimestampTz, tzAbbr } from './time';

describe('dateInTz', () => {
  it('returns same day for UTC midnight', () => {
    expect(dateInTz('2024-01-15T00:00:00Z', 'UTC')).toBe('2024-01-15');
  });

  it('stays on same day in London (winter, UTC=GMT)', () => {
    // 22:30 UTC on Jan 15 is still Jan 15 in London (winter = UTC+0)
    expect(dateInTz('2024-01-15T22:30:00Z', 'Europe/London')).toBe('2024-01-15');
  });

  it('advances to next day for IST (UTC+5:30)', () => {
    // 22:30 UTC Jan 15 = 04:00 Jan 16 IST — crosses midnight
    expect(dateInTz('2024-01-15T22:30:00Z', 'Asia/Kolkata')).toBe('2024-01-16');
  });

  it('stays same day for IST when not crossing midnight', () => {
    // 10:00 UTC Jan 15 = 15:30 IST Jan 15
    expect(dateInTz('2024-01-15T10:00:00Z', 'Asia/Kolkata')).toBe('2024-01-15');
  });

  it('goes back a day for UTC-8 (Los Angeles, winter)', () => {
    // 02:00 UTC Jan 15 = 18:00 Jan 14 PST (UTC-8)
    expect(dateInTz('2024-01-15T02:00:00Z', 'America/Los_Angeles')).toBe('2024-01-14');
  });

  it('handles DST: London in summer is UTC+1', () => {
    // 23:30 UTC Jun 15 = 00:30 Jun 16 BST (UTC+1)
    expect(dateInTz('2024-06-15T23:30:00Z', 'Europe/London')).toBe('2024-06-16');
  });

  it('handles DST: London in summer, not crossing midnight', () => {
    // 10:00 UTC Jun 15 = 11:00 BST Jun 15
    expect(dateInTz('2024-06-15T10:00:00Z', 'Europe/London')).toBe('2024-06-15');
  });

  it('returns YYYY-MM-DD format', () => {
    const result = dateInTz('2024-01-05T12:00:00Z', 'UTC');
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(result).toBe('2024-01-05');
  });

  it('falls back to sliced ISO string on invalid tz', () => {
    expect(dateInTz('2024-01-15T12:00:00Z', 'Not/ATimezone')).toBe('2024-01-15');
  });

  it('handles AEST (UTC+10/+11)', () => {
    // 14:00 UTC Jan 15 = 00:00 Jan 16 AEDT (UTC+11 in summer)
    expect(dateInTz('2024-01-15T13:00:00Z', 'Australia/Sydney')).toBe('2024-01-16');
  });
});

describe('formatTimestampTz', () => {
  it('formats time in UTC', () => {
    const result = formatTimestampTz('2024-01-15T14:30:00Z', 'UTC');
    expect(result).toBe('2:30 PM');
  });

  it('formats time in IST (UTC+5:30)', () => {
    // 14:30 UTC = 20:00 IST
    const result = formatTimestampTz('2024-01-15T14:30:00Z', 'Asia/Kolkata');
    expect(result).toBe('8:00 PM');
  });

  it('formats midnight in UTC', () => {
    const result = formatTimestampTz('2024-01-15T00:00:00Z', 'UTC');
    expect(result).toBe('12:00 AM');
  });

  it('uses uppercase AM/PM', () => {
    const result = formatTimestampTz('2024-01-15T02:00:00Z', 'UTC');
    expect(result).toMatch(/AM|PM/);
  });

  it('falls back to original string on invalid tz', () => {
    const ts = '2024-01-15T14:30:00Z';
    expect(formatTimestampTz(ts, 'Not/ATimezone')).toBe(ts);
  });
});

describe('tzAbbr', () => {
  it('returns a non-empty string for UTC', () => {
    // Node and browsers may return 'UTC' or 'GMT' — both are valid
    const result = tzAbbr('UTC');
    expect(result.length).toBeGreaterThan(0);
    expect(['UTC', 'GMT']).toContain(result);
  });

  it('returns a non-empty string for London (GMT or BST or GMT+1)', () => {
    // Node may return 'GMT+1' during BST instead of 'BST'
    const result = tzAbbr('Europe/London');
    expect(result.length).toBeGreaterThan(0);
    expect(result).toMatch(/^(GMT|BST|GMT[+-]\d)$/);
  });

  it('returns an offset or named abbreviation for Kolkata', () => {
    // Node may return 'GMT+5:30' instead of 'IST'
    const result = tzAbbr('Asia/Kolkata');
    expect(result.length).toBeGreaterThan(0);
    expect(result).toMatch(/^(IST|GMT\+5:30)$/);
  });

  it('falls back to tz string on invalid timezone', () => {
    expect(tzAbbr('Not/ATimezone')).toBe('Not/ATimezone');
  });

  it('returns a non-empty string for New York', () => {
    const result = tzAbbr('America/New_York');
    expect(result.length).toBeGreaterThan(0);
  });
});
