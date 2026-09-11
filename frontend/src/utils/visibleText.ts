/** 模型漏出的工具/函数协议 XML，不是给用户看的正文。 */

const TAG_NAME =
  "(?:[\\w.-]+:)?(?:old[_-])?(?:function|tool)[_-](?:calls?|results?|responses?|outputs?)";

const FENCE = /(```[\s\S]*?```|~~~[\s\S]*?~~~)/g;

function stripUnfenced(text: string): string {
  const block = new RegExp(`<(${TAG_NAME})\\s*>[\\s\\S]*?<\\/\\1\\s*>`, "gi");
  const qwenBlock = /<(function|parameter)=[^\s>/]+>[\s\S]*?<\/\1\s*>/gi;
  const selfClosing = new RegExp(`<(${TAG_NAME})\\s*\\/>`, "gi");
  const anyTag = new RegExp(`<\\/?(${TAG_NAME})\\s*\\/?>`, "gi");
  const qwenAttr = /<\/?(?:function|parameter)(?:=[^\s>/]+)?\s*>/gi;
  return text
    .replace(block, "")
    .replace(qwenBlock, "")
    .replace(selfClosing, "")
    .replace(anyTag, "")
    .replace(qwenAttr, "");
}

function tidy(text: string): string {
  return text.replace(/\n{3,}/g, "\n\n").replace(/^\n+|\n+$/g, "");
}

/** 从完整助手正文里剥掉 function/tool 协议标签（含已落库的旧消息）。 */
export function stripProtocolMarkup(text: string): string {
  if (!text) return text;
  if (text.includes("<")) {
    const parts = text.split(FENCE);
    text = parts.map((part, i) => (i % 2 === 1 ? part : stripUnfenced(part))).join("");
  }
  return tidy(text);
}
