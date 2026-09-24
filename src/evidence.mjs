export const kinds = ['goal', 'artifact', 'system', 'constraint', 'entity', 'memory_reference'];
export function segments(text, spans) {
  const parts = []; let cursor = 0;
  for (const span of [...spans].sort((a, b) => a.start - b.start || a.end - b.end)) {
    if (!Number.isInteger(span.start) || !Number.isInteger(span.end) || span.start < cursor || span.end <= span.start || span.end > text.length || text.slice(span.start, span.end) !== span.value || !kinds.includes(span.kind)) continue;
    parts.push({text: text.slice(cursor, span.start)});
    parts.push({text: span.value, kind: span.kind}); cursor = span.end;
  }
  parts.push({text: text.slice(cursor)}); return parts;
}
