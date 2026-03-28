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
