import { format, formatDistanceToNow, parseISO, differenceInSeconds } from 'date-fns';

export function formatDate(dateStr: string): string {
  try {
    const date = parseISO(dateStr);
    return format(date, 'MMM d, yyyy');
  } catch {
    return dateStr;
  }
}

export function formatDateShort(dateStr: string): string {
  try {
    const date = parseISO(dateStr);
    return format(date, 'MMM d');
  } catch {
    return dateStr;
  }
}

export function formatRelative(dateStr: string): string {
  try {
    const date = parseISO(dateStr);
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return dateStr;
  }
}

export function formatTime(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  const total = Math.round(seconds);
  if (total < 60) return `${total}s`;
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (secs === 0) return `${mins}m`;
  return `${mins}m ${secs}s`;
}

export function formatTimestamp(ts: string): string {
  try {
    const date = parseISO(ts);
    return format(date, 'h:mm a');
  } catch {
    return ts;
  }
}

export function formatTimestampTz(ts: string, tz: string): string {
  try {
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: tz,
    }).format(new Date(ts));
  } catch {
    return ts;
  }
}

/** Returns YYYY-MM-DD in the given timezone for a full ISO timestamp. */
export function dateInTz(isoTs: string, tz: string): string {
  try {
    // en-CA locale formats as YYYY-MM-DD natively
    return new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(new Date(isoTs));
  } catch {
    return isoTs.slice(0, 10);
  }
}

export function tzAbbr(tz: string): string {
  try {
    return new Intl.DateTimeFormat('en', { timeZone: tz, timeZoneName: 'shortOffset' })
      .formatToParts(new Date())
      .find(p => p.type === 'timeZoneName')?.value ?? tz;
  } catch {
    return tz;
  }
}

/** Formats a date for display in the given timezone.
 *  Accepts either a full ISO timestamp (with 'T') or a plain YYYY-MM-DD string.
 *  When a full timestamp is given, the date shown reflects the calendar date in `tz`. */
export function formatDateTz(tsOrDate: string, tz: string): string {
  try {
    const dateStr = tsOrDate.includes('T') ? dateInTz(tsOrDate, tz) : tsOrDate;
    return format(parseISO(dateStr), 'MMM d, yyyy');
  } catch {
    return tsOrDate;
  }
}

export function getDurationBetween(start: string, end: string): string {
  try {
    const s = parseISO(start);
    const e = parseISO(end);
    const secs = differenceInSeconds(e, s);
    return formatTime(secs);
  } catch {
    return '—';
  }
}
