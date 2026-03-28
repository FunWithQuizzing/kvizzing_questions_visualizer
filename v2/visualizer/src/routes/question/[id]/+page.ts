import { error } from '@sveltejs/kit';

export const prerender = true;

export async function load({ params, parent }) {
  const { questions } = await parent();
  const question = questions.find((q: { id: string }) => q.id === params.id);
  if (!question) throw error(404, 'Question not found');
  return { question };
}
