/**
 * Data files must be available at /data/*.json during dev and build.
 * Easiest setup: run `ln -s ../../data static/data` from the visualizer directory.
 * Or copy the files: cp -r ../data/* static/data/
 */

export const prerender = true;

export async function load({ fetch }) {
  const [questions, sessions, members] = await Promise.all([
    fetch('/data/questions.json').then(r => r.json()),
    fetch('/data/sessions.json').then(r => r.json()),
    fetch('/data/members.json').then(r => r.json()),
  ]);
  return { questions, sessions, members };
}
