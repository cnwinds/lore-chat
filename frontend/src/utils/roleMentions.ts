export type MentionRole = { id: string; name: string };

/** 从正文抽出 @token（不含 @）。 */
export function parseMentionTokens(text: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const re = /@([^\s@]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text || ""))) {
    const token = (m[1] || "").trim();
    if (!token || seen.has(token)) continue;
    seen.add(token);
    out.push(token);
  }
  return out;
}

export function resolveMentionRoleIds(
  text: string,
  roles: MentionRole[],
): string[] {
  const ids: string[] = [];
  const seen = new Set<string>();
  for (const token of parseMentionTokens(text)) {
    const byId = roles.find((r) => r.id === token);
    const exact = roles.filter((r) => r.name === token);
    const fuzzy = roles.filter(
      (r) => r.name.includes(token) || token.includes(r.name),
    );
    const hit = byId || (exact.length === 1 ? exact[0] : fuzzy.length === 1 ? fuzzy[0] : null);
    if (hit && !seen.has(hit.id)) {
      seen.add(hit.id);
      ids.push(hit.id);
    }
  }
  return ids;
}

export function mentionQueryAtCaret(
  text: string,
  caret: number,
): { start: number; query: string } | null {
  const before = (text || "").slice(0, Math.max(0, caret));
  const at = before.lastIndexOf("@");
  if (at < 0) return null;
  if (at > 0 && !/\s/.test(before[at - 1] || " ")) return null;
  const query = before.slice(at + 1);
  if (query.includes(" ") || query.includes("\n")) return null;
  return { start: at, query };
}
