import { readFileSync } from 'fs';

export function entries() {
  const sessions = JSON.parse(readFileSync('static/data/sessions.json', 'utf-8'));
  return sessions.map((s: { id: string }) => ({ id: s.id }));
}
