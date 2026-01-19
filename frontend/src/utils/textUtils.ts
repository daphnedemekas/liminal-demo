/**
 * Strips markdown formatting from text, especially useful for titles and headings
 * that should be displayed as plain text.
 */
export function stripMarkdown(text: string): string {
  if (!text) return text
  
  return text
    // Remove bold markdown (**text** or __text__)
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    // Remove italic markdown (*text* or _text_) - only if it's a complete word/phrase
    .replace(/\*([^*\n]+?)\*/g, '$1')
    .replace(/_([^_\n]+?)_/g, '$1')
    // Remove code blocks (```code```)
    .replace(/```[\s\S]*?```/g, '')
    // Remove inline code (`code`)
    .replace(/`([^`]+)`/g, '$1')
    // Remove links [text](url)
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
    // Remove images ![alt](url)
    .replace(/!\[([^\]]*)\]\([^\)]+\)/g, '$1')
    // Clean up any remaining markdown characters
    .trim()
}

