const PALETTE = [
  '#F97316', '#3B82F6', '#10B981', '#8B5CF6',
  '#EF4444', '#F59E0B', '#06B6D4', '#EC4899',
  '#84CC16', '#6366F1', '#14B8A6', '#F43F5E',
  '#A855F7', '#0EA5E9', '#22C55E', '#FB923C'
];

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit int
  }
  return Math.abs(hash);
}

export function getMemberColor(username: string, configColor?: string | null): string {
  if (configColor) return configColor;
  return PALETTE[hashString(username) % PALETTE.length];
}

export function getMemberInitials(displayName: string): string {
  const parts = displayName.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
