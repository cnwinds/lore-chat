export function sliceByCodepoint(text: string, start: number, end: number): string {
  const chars = Array.from(text);
  return chars.slice(start, end).join("");
}

export function splitForHighlight(
  text: string,
  start: number,
  end: number,
): { before: string; highlight: string; after: string } {
  const chars = Array.from(text);
  return {
    before: chars.slice(0, start).join(""),
    highlight: chars.slice(start, end).join(""),
    after: chars.slice(end).join(""),
  };
}
