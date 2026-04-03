export async function load({ fetch }) {
  const [threads, questions] = await Promise.all([
    fetch('/data/rejected_candidates.json').then(r => r.ok ? r.json() : []).catch(() => []),
    fetch('/data/questions.json').then(r => r.ok ? r.json() : []).catch(() => []),
  ]);
  // Build a map of question_timestamp → { id, text } for cross-referencing context
  const questionsByTs = new Map<string, { id: string; text: string }>();
  for (const q of questions) {
    if (q.question?.timestamp) {
      questionsByTs.set(q.question.timestamp, { id: q.id, text: q.question.text });
    }
  }
  return { threads, questionsByTs };
}
