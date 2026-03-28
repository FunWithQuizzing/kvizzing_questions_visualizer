import { error } from '@sveltejs/kit';

export const prerender = true;

export async function load({ params, parent }) {
  const { sessions, questions } = await parent();
  const session = sessions.find((s: { id: string }) => s.id === params.id);
  if (!session) throw error(404, 'Session not found');

  const sessionQuestions = questions
    .filter((q: { session: { id: string } | null }) => q.session?.id === params.id)
    .sort((a: { session: { question_number: number } }, b: { session: { question_number: number } }) =>
      (a.session?.question_number ?? 0) - (b.session?.question_number ?? 0)
    );

  return { session, sessionQuestions };
}
