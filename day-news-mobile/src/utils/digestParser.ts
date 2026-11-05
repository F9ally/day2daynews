import { DigestItem, ParsedDigestItem } from '../types';
import { TOPIC_EMOJIS } from '../constants/theme';

/**
 * Strip common markdown syntax and collapse whitespace.
 * Mirrors _strip_markdown from Python backend.
 */
function stripMarkdown(text: string): string {
  if (!text) return '';
  let t = text;
  // Remove fenced code blocks
  t = t.replace(/```[\s\S]*?```/g, ' ');
  // Strip headings
  t = t.replace(/^\s*#{1,6}\s+/gm, '');
  // Bold/italic markers
  t = t.replace(/\*\*/g, '').replace(/__/g, '').replace(/\*/g, '').replace(/_/g, '');
  // Inline code backticks
  t = t.replace(/`/g, '');
  // Replace markdown bullets with separators
  t = t.replace(/^[\s>*\-•]+/gm, '• ');
  // Remove markdown links [text](url) -> text
  t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  // Collapse whitespace
  t = t.replace(/\s+/g, ' ').trim();
  return t;
}

/**
 * Decode HTML entities. Light version for the most common ones.
 */
function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'");
}

/**
 * Extract headline and summary from raw Ollama output.
 * Mirrors _extract_headline_and_points from Python backend.
 */
function extractHeadlineAndSummary(
  text: string,
): { headline: string; summary: string } {
  const cleaned = stripMarkdown(text);
  const decoded = decodeHtmlEntities(cleaned);

  let headline = '';
  let summary = '';

  // Capture headline up to "Summary:" or end of string
  const hMatch = decoded.match(/Headline:\s*(.+?)(?:\s+Summary:|$)/is);
  if (hMatch) {
    headline = hMatch[1].trim();
    if (headline.length > 180) {
      headline = headline.slice(0, 180).trimEnd();
    }
  }

  // Capture summary after "Summary:"
  const sMatch = decoded.match(/Summary:\s*(.+)/is);
  if (sMatch) {
    summary = sMatch[1].trim();
  }

  return { headline, summary };
}

/**
 * Parse raw DigestItem array from the site data into display-ready items.
 */
export function parseDigestItems(items: DigestItem[]): ParsedDigestItem[] {
  const seen = new Set<string>();

  return items
    .filter((item) => {
      // Skip error entries
      if (item.summary && item.summary.includes('[ERROR:')) return false;
      const key = item.topic?.toLowerCase() ?? '';
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((item) => {
      const topicKey = item.topic?.toLowerCase().replace(/\s/g, '') ?? 'general';
      const emoji = TOPIC_EMOJIS[topicKey] ?? '❓';

      const { headline, summary } = extractHeadlineAndSummary(item.summary);

      return {
        topic: topicKey === 'us' ? 'US' : (item.topic || 'General'),
        emoji,
        headline: headline || item.title || 'Untitled',
        summary: summary || '',
        url: item.url || null,
        title: item.title || null,
      };
    });
}

/**
 * Parse compiled HTML string into native digest items.
 * Used as fallback when items array is not available.
 */
export function parseCompiledHtml(html: string): ParsedDigestItem[] {
  const results: ParsedDigestItem[] = [];
  // Match each digest-topic section
  const sectionRegex =
    /<section class="digest-topic">([\s\S]*?)<\/section>/gi;
  let sectionMatch;

  while ((sectionMatch = sectionRegex.exec(html)) !== null) {
    const block = sectionMatch[1];

    // Extract topic from h2
    const h2Match = block.match(/<h2[^>]*>([\s\S]*?)<\/h2>/i);
    let topicText = '';
    let url: string | null = null;

    if (h2Match) {
      // Check if h2 contains a link
      const linkMatch = h2Match[1].match(
        /href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/i,
      );
      if (linkMatch) {
        url = decodeHtmlEntities(linkMatch[1]);
        topicText = linkMatch[2];
      } else {
        topicText = h2Match[1];
      }
    }

    // Strip HTML tags and emojis from topic
    topicText = topicText.replace(/<[^>]+>/g, '').trim();
    // Extract emoji (first character if it's an emoji)
    const emojiMatch = topicText.match(
      /^([\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F900}-\u{1F9FF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}]+)\s*/u,
    );
    const emoji = emojiMatch ? emojiMatch[1] : '❓';
    const topicName = topicText
      .replace(
        /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F900}-\u{1F9FF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}]+/gu,
        '',
      )
      .trim();

    // Extract headline from h3
    const h3Match = block.match(
      /<h3 class="digest-headline"[^>]*>([\s\S]*?)<\/h3>/i,
    );
    let headline = '';
    if (h3Match) {
      const headLinkMatch = h3Match[1].match(/<a[^>]*>([\s\S]*?)<\/a>/i);
      headline = headLinkMatch
        ? headLinkMatch[1].replace(/<[^>]+>/g, '').trim()
        : h3Match[1].replace(/<[^>]+>/g, '').trim();

      // Extract URL from headline link if not already found
      if (!url) {
        const hrefMatch = h3Match[1].match(/href="([^"]*)"/i);
        if (hrefMatch) url = decodeHtmlEntities(hrefMatch[1]);
      }
    }

    // Extract summary from digest-points
    const pointsMatch = block.match(
      /<div class="digest-points">([\s\S]*?)<\/div>/i,
    );
    let summary = '';
    if (pointsMatch) {
      summary = pointsMatch[1]
        .replace(/<p>/gi, '')
        .replace(/<\/p>/gi, '\n')
        .replace(/<[^>]+>/g, '')
        .trim();
    }

    headline = decodeHtmlEntities(headline);
    summary = decodeHtmlEntities(summary);

    results.push({
      topic: topicName || 'General',
      emoji,
      headline: headline || 'Untitled',
      summary,
      url,
      title: headline || null,
    });
  }

  return results;
}
