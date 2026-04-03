export interface TopicMeta {
  id: string;
  label: string;
  /** Tailwind classes for the solid chip (primary category badge) */
  cls: string;
  /** Tailwind classes for the outlined chip (secondary category badge) */
  secondary_cls: string;
  /** Tailwind ring class for active filter chips */
  ring: string;
  /** Tailwind class for bar fill in charts */
  barCls: string;
  /** Hex color for SVG rendering (Tailwind *-400 equivalent) */
  hex: string;
}

/**
 * Topic definitions. To add a new topic:
 * 1. Add an entry to v2/pipeline/config/topics.json (id, label, color, hex)
 * 2. Add the Tailwind color mapping below in COLOR_MAP
 * That's it — pipeline schema and audit derive from the same JSON automatically.
 */
/**
 * Topic definitions. To add a new topic:
 * 1. Add an entry to v2/pipeline/config/topics.json (id, label, color)
 * 2. Pick a Tailwind color name from COLOR_MAP below
 * That's it — pipeline schema, audit, and UI all derive from the same JSON.
 */

/** Tailwind color-400 hex values (used for SVG charts) */
const HEX_MAP: Record<string, string> = {
  amber: '#fbbf24', sky: '#38bdf8', indigo: '#818cf8', green: '#4ade80',
  teal: '#2dd4bf', violet: '#a78bfa', orange: '#fb923c', fuchsia: '#e879f9',
  red: '#f87171', slate: '#94a3b8', rose: '#fb7185', purple: '#c084fc',
  stone: '#a8a29e', yellow: '#facc15', lime: '#a3e635', cyan: '#22d3ee',
  emerald: '#34d399', pink: '#f472b6', blue: '#60a5fa', zinc: '#a1a1aa',
};

const COLOR_MAP: Record<string, { cls: string; secondary_cls: string; ring: string; barCls: string }> = {
  amber:   { cls: 'bg-amber-100 text-amber-800 hover:bg-amber-200',       secondary_cls: 'border border-amber-400 text-amber-700 hover:bg-amber-50 dark:border-amber-600 dark:text-amber-400 dark:hover:bg-amber-900/20',       ring: 'ring-amber-400',   barCls: 'bg-amber-400' },
  sky:     { cls: 'bg-sky-100 text-sky-800 hover:bg-sky-200',             secondary_cls: 'border border-sky-400 text-sky-700 hover:bg-sky-50 dark:border-sky-600 dark:text-sky-400 dark:hover:bg-sky-900/20',             ring: 'ring-sky-400',     barCls: 'bg-sky-400' },
  indigo:  { cls: 'bg-indigo-100 text-indigo-800 hover:bg-indigo-200',    secondary_cls: 'border border-indigo-400 text-indigo-700 hover:bg-indigo-50 dark:border-indigo-500 dark:text-indigo-400 dark:hover:bg-indigo-900/20',    ring: 'ring-indigo-400',  barCls: 'bg-indigo-400' },
  green:   { cls: 'bg-green-100 text-green-800 hover:bg-green-200',       secondary_cls: 'border border-green-400 text-green-700 hover:bg-green-50 dark:border-green-600 dark:text-green-400 dark:hover:bg-green-900/20',       ring: 'ring-green-400',   barCls: 'bg-green-400' },
  teal:    { cls: 'bg-teal-100 text-teal-800 hover:bg-teal-200',          secondary_cls: 'border border-teal-400 text-teal-700 hover:bg-teal-50 dark:border-teal-600 dark:text-teal-400 dark:hover:bg-teal-900/20',          ring: 'ring-teal-400',    barCls: 'bg-teal-400' },
  violet:  { cls: 'bg-violet-100 text-violet-800 hover:bg-violet-200',    secondary_cls: 'border border-violet-400 text-violet-700 hover:bg-violet-50 dark:border-violet-500 dark:text-violet-400 dark:hover:bg-violet-900/20',    ring: 'ring-violet-400',  barCls: 'bg-violet-400' },
  orange:  { cls: 'bg-orange-100 text-orange-800 hover:bg-orange-200',    secondary_cls: 'border border-orange-400 text-orange-700 hover:bg-orange-50 dark:border-orange-600 dark:text-orange-400 dark:hover:bg-orange-900/20',    ring: 'ring-orange-400',  barCls: 'bg-orange-400' },
  fuchsia: { cls: 'bg-fuchsia-100 text-fuchsia-800 hover:bg-fuchsia-200', secondary_cls: 'border border-fuchsia-400 text-fuchsia-700 hover:bg-fuchsia-50 dark:border-fuchsia-500 dark:text-fuchsia-400 dark:hover:bg-fuchsia-900/20', ring: 'ring-fuchsia-400', barCls: 'bg-fuchsia-400' },
  red:     { cls: 'bg-red-100 text-red-800 hover:bg-red-200',             secondary_cls: 'border border-red-400 text-red-700 hover:bg-red-50 dark:border-red-600 dark:text-red-400 dark:hover:bg-red-900/20',             ring: 'ring-red-400',     barCls: 'bg-red-400' },
  slate:   { cls: 'bg-slate-100 text-slate-700 hover:bg-slate-200',       secondary_cls: 'border border-slate-400 text-slate-600 hover:bg-slate-50 dark:border-slate-500 dark:text-slate-400 dark:hover:bg-slate-900/20',       ring: 'ring-slate-400',   barCls: 'bg-slate-400' },
  rose:    { cls: 'bg-rose-100 text-rose-800 hover:bg-rose-200',          secondary_cls: 'border border-rose-400 text-rose-700 hover:bg-rose-50 dark:border-rose-600 dark:text-rose-400 dark:hover:bg-rose-900/20',          ring: 'ring-rose-400',    barCls: 'bg-rose-400' },
  purple:  { cls: 'bg-purple-100 text-purple-800 hover:bg-purple-200',    secondary_cls: 'border border-purple-400 text-purple-700 hover:bg-purple-50 dark:border-purple-500 dark:text-purple-400 dark:hover:bg-purple-900/20',    ring: 'ring-purple-400',  barCls: 'bg-purple-400' },
  stone:   { cls: 'bg-stone-100 text-stone-800 hover:bg-stone-200',       secondary_cls: 'border border-stone-400 text-stone-700 hover:bg-stone-50 dark:border-stone-500 dark:text-stone-400 dark:hover:bg-stone-900/20',       ring: 'ring-stone-400',   barCls: 'bg-stone-400' },
  yellow:  { cls: 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200',    secondary_cls: 'border border-yellow-400 text-yellow-700 hover:bg-yellow-50 dark:border-yellow-500 dark:text-yellow-400 dark:hover:bg-yellow-900/20',    ring: 'ring-yellow-400',  barCls: 'bg-yellow-400' },
  lime:    { cls: 'bg-lime-100 text-lime-800 hover:bg-lime-200',          secondary_cls: 'border border-lime-400 text-lime-700 hover:bg-lime-50 dark:border-lime-600 dark:text-lime-400 dark:hover:bg-lime-900/20',          ring: 'ring-lime-400',    barCls: 'bg-lime-400' },
  cyan:    { cls: 'bg-cyan-100 text-cyan-800 hover:bg-cyan-200',          secondary_cls: 'border border-cyan-400 text-cyan-700 hover:bg-cyan-50 dark:border-cyan-600 dark:text-cyan-400 dark:hover:bg-cyan-900/20',          ring: 'ring-cyan-400',    barCls: 'bg-cyan-400' },
  emerald: { cls: 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200', secondary_cls: 'border border-emerald-400 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-600 dark:text-emerald-400 dark:hover:bg-emerald-900/20', ring: 'ring-emerald-400', barCls: 'bg-emerald-400' },
  pink:    { cls: 'bg-pink-100 text-pink-800 hover:bg-pink-200',          secondary_cls: 'border border-pink-400 text-pink-700 hover:bg-pink-50 dark:border-pink-600 dark:text-pink-400 dark:hover:bg-pink-900/20',          ring: 'ring-pink-400',    barCls: 'bg-pink-400' },
};

const DEFAULT_COLOR = COLOR_MAP['slate'];

// Import from shared config — the single source of truth for topic categories
import topicsConfig from '../../../../pipeline/config/topics.json';

export const TOPICS: TopicMeta[] = topicsConfig.map(t => {
  const colors = COLOR_MAP[t.color] ?? DEFAULT_COLOR;
  return { id: t.id, label: t.label, hex: HEX_MAP[t.color] ?? '#94a3b8', ...colors };
});

export const TOPIC_MAP = new Map(TOPICS.map(t => [t.id, t]));

export function topicCls(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.cls ?? 'bg-gray-100 text-gray-700 hover:bg-gray-200';
}

export function topicClsSecondary(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.secondary_cls ?? 'border border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-800';
}

export function topicLabel(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.label ?? topicId.replace('_', ' & ');
}

export function topicBarCls(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.barCls ?? 'bg-gray-400';
}

export function topicHex(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.hex ?? '#9ca3af';
}
