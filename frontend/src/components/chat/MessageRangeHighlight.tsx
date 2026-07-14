import { splitForHighlight } from "../../utils/unicodeHighlight";

export function MessageRangeHighlight({
  text,
  start,
  end,
}: {
  text: string;
  start: number;
  end: number;
}) {
  const { before, highlight, after } = splitForHighlight(text, start, end);
  return (
    <span>
      {before}
      <mark className="message-range-highlight">{highlight}</mark>
      {after}
    </span>
  );
}
