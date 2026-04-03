/**
 * Strip [image: ...], [video: ...], [audio: ...] inline annotations from
 * question text when actual media attachments are present. These tags are
 * inserted during LLM extraction and become redundant once files are uploaded.
 */
export function displayText(text: string, hasMedia: boolean): string {
  if (!hasMedia) return text;
  return text
    .replace(/\s*\[(image|video|audio|sticker|gif):[^\]]*\]/gi, '')
    .trim();
}
