export interface TopicMeta {
  id: string;
  label: string;
  /** Tailwind classes for the soft-tint chip (card badge + filter chip) */
  cls: string;
  /** Tailwind ring class for active filter chips */
  ring: string;
  /** Tailwind class for bar fill in charts */
  barCls: string;
  /** Hex color for SVG rendering (Tailwind *-400 equivalent) */
  hex: string;
}

export const TOPICS: TopicMeta[] = [
  { id: 'history',       label: 'History',       cls: 'bg-amber-100 text-amber-800 hover:bg-amber-200',       ring: 'ring-amber-400',   barCls: 'bg-amber-400',   hex: '#fbbf24' },
  { id: 'science',       label: 'Science',        cls: 'bg-sky-100 text-sky-800 hover:bg-sky-200',             ring: 'ring-sky-400',     barCls: 'bg-sky-400',     hex: '#38bdf8' },
  { id: 'technology',    label: 'Technology',     cls: 'bg-indigo-100 text-indigo-800 hover:bg-indigo-200',    ring: 'ring-indigo-400',  barCls: 'bg-indigo-400',  hex: '#818cf8' },
  { id: 'sports',        label: 'Sports',         cls: 'bg-green-100 text-green-800 hover:bg-green-200',       ring: 'ring-green-400',   barCls: 'bg-green-400',   hex: '#4ade80' },
  { id: 'geography',     label: 'Geography',      cls: 'bg-teal-100 text-teal-800 hover:bg-teal-200',          ring: 'ring-teal-400',    barCls: 'bg-teal-400',    hex: '#2dd4bf' },
  { id: 'entertainment', label: 'Entertainment',  cls: 'bg-violet-100 text-violet-800 hover:bg-violet-200',    ring: 'ring-violet-400',  barCls: 'bg-violet-400',  hex: '#a78bfa' },
  { id: 'food_drink',    label: 'Food & Drink',   cls: 'bg-orange-100 text-orange-800 hover:bg-orange-200',    ring: 'ring-orange-400',  barCls: 'bg-orange-400',  hex: '#fb923c' },
  { id: 'art_culture',   label: 'Art & Culture',  cls: 'bg-fuchsia-100 text-fuchsia-800 hover:bg-fuchsia-200', ring: 'ring-fuchsia-400', barCls: 'bg-fuchsia-400', hex: '#e879f9' },
  { id: 'literature',    label: 'Literature',     cls: 'bg-red-100 text-red-800 hover:bg-red-200',             ring: 'ring-red-400',     barCls: 'bg-red-400',     hex: '#f87171' },
  { id: 'business',      label: 'Business',       cls: 'bg-slate-100 text-slate-700 hover:bg-slate-200',       ring: 'ring-slate-400',   barCls: 'bg-slate-400',   hex: '#94a3b8' },
  { id: 'etymology',     label: 'Etymology',      cls: 'bg-rose-100 text-rose-800 hover:bg-rose-200',          ring: 'ring-rose-400',    barCls: 'bg-rose-400',    hex: '#fb7185' },
  { id: 'general',       label: 'General',        cls: 'bg-lime-100 text-lime-800 hover:bg-lime-200',          ring: 'ring-lime-400',    barCls: 'bg-lime-400',    hex: '#a3e635' },
];

export const TOPIC_MAP = new Map(TOPICS.map(t => [t.id, t]));

export function topicCls(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.cls ?? 'bg-gray-100 text-gray-700 hover:bg-gray-200';
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
