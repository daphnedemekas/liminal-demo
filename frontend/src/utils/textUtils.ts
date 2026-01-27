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

/**
 * Strips ANSI escape sequences from terminal output.
 * Removes control sequences like bracketed paste mode ([?2004h, [?2004l),
 * cursor movement, colors, and other terminal control codes.
 */
export function stripAnsiEscapeSequences(text: string): string {
  if (!text) return text
  
  // First, normalize line endings and handle carriage returns
  let cleaned = text
    // Replace carriage returns followed by newlines with just newlines
    .replace(/\r\n/g, '\n')
    // Handle carriage returns that overwrite (common in terminal output)
    // Split by \r and take the last segment of each line
    .split('\r').map(line => {
      // If line has \r, take everything after the last \r
      const parts = line.split('\r')
      return parts[parts.length - 1]
    }).join('')
  
  // Now strip ANSI escape sequences
  cleaned = cleaned
    // Remove bracketed paste mode sequences (\x1b[?2004h and \x1b[?2004l)
    .replace(/\x1b\[\?2004[hl]/g, '')
    // Remove CSI sequences with question mark: \x1b[?<digits><letter> (like [?2026h, [?1004h, [?25l)
    .replace(/\x1b\[\?[0-9]+[hl]/g, '')
    // Remove cursor positioning sequences (like \x1b[<row>;<col>H or \x1b[<n>G)
    .replace(/\x1b\[[0-9;]*[Hf]/g, '')  // Cursor position
    .replace(/\x1b\[[0-9]*G/g, '')      // Cursor horizontal absolute
    .replace(/\x1b\[[0-9]*d/g, '')      // Cursor vertical absolute
    // Remove cursor movement sequences
    .replace(/\x1b\[[0-9]*[ABCD]/g, '') // Cursor up/down/forward/back
    // Remove erase sequences
    .replace(/\x1b\[[0-9]*[JK]/g, '')   // Erase in display/line
    // Remove CSI (Control Sequence Introducer) sequences: \x1b[...m (colors, styles)
    .replace(/\x1b\[[0-9;]*m/g, '')
    // Remove CSI sequences with parameters: \x1b[<n>;...<command>
    .replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')
    // Remove CSI sequences that might be malformed or partial
    .replace(/\x1b\[[^\x1b]*/g, '')
    // Remove OSC (Operating System Command) sequences: \x1b]...\x07 or \x1b]...\x1b\\
    .replace(/\x1b\][^\x07\x1b]*(\x07|\x1b\\)/g, '')
    // Remove other escape sequences (ESC followed by various characters)
    .replace(/\x1b[^\[\]]/g, '')
    // Remove any remaining escape characters that might have slipped through
    .replace(/\x1b/g, '')
    // Remove any remaining malformed sequences that look like ANSI but aren't properly escaped
    .replace(/\[\?[0-9]+[hl]/g, '')
    // Remove sequences that might appear without proper escape (like [?2026l[?1004h[?25l)
    .replace(/\[\?[0-9]+[hl]/g, '')
    // Clean up multiple spaces that might result from cursor movements
    .replace(/[ \t]+$/gm, '')  // Remove trailing spaces on each line
  
  return cleaned
}

