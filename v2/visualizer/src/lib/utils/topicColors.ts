export interface TopicMeta {
  id: string;
  label: string;
  /** Tailwind classes for the soft-tint chip (card badge + filter chip) */
  cls: string;
  /** Tailwind ring class for active filter chips */
  ring: string;
}

export const TOPICS: TopicMeta[] = [
  { id: 'history',       label: 'History',       cls: 'bg-amber-100 text-amber-800 hover:bg-amber-200',       ring: 'ring-amber-400' },
  { id: 'science',       label: 'Science',        cls: 'bg-sky-100 text-sky-800 hover:bg-sky-200',             ring: 'ring-sky-400' },
  { id: 'technology',    label: 'Technology',     cls: 'bg-indigo-100 text-indigo-800 hover:bg-indigo-200',    ring: 'ring-indigo-400' },
  { id: 'sports',        label: 'Sports',         cls: 'bg-green-100 text-green-800 hover:bg-green-200',       ring: 'ring-green-400' },
  { id: 'geography',     label: 'Geography',      cls: 'bg-teal-100 text-teal-800 hover:bg-teal-200',          ring: 'ring-teal-400' },
  { id: 'entertainment', label: 'Entertainment',  cls: 'bg-violet-100 text-violet-800 hover:bg-violet-200',    ring: 'ring-violet-400' },
  { id: 'food_drink',    label: 'Food & Drink',   cls: 'bg-orange-100 text-orange-800 hover:bg-orange-200',    ring: 'ring-orange-400' },
  { id: 'art_culture',   label: 'Art & Culture',  cls: 'bg-fuchsia-100 text-fuchsia-800 hover:bg-fuchsia-200', ring: 'ring-fuchsia-400' },
  { id: 'literature',    label: 'Literature',     cls: 'bg-red-100 text-red-800 hover:bg-red-200',             ring: 'ring-red-400' },
  { id: 'business',      label: 'Business',       cls: 'bg-slate-100 text-slate-700 hover:bg-slate-200',       ring: 'ring-slate-400' },
  { id: 'general',       label: 'General',        cls: 'bg-lime-100 text-lime-800 hover:bg-lime-200',          ring: 'ring-lime-400' },
];

export const TOPIC_MAP = new Map(TOPICS.map(t => [t.id, t]));

export function topicCls(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.cls ?? 'bg-gray-100 text-gray-700 hover:bg-gray-200';
}

export function topicLabel(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.label ?? topicId.replace('_', ' & ');
}
