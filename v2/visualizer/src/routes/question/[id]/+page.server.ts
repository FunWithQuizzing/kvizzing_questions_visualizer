import { readFileSync } from 'node:fs';

export function entries() {
  const questions = JSON.parse(readFileSync('static/data/questions.json', 'utf-8'));
  return questions.map((q: { id: string }) => ({ id: q.id }));
}
