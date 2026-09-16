/** ask_user 选项：离散标签 vs 需要用户在卡片里自述。 */

export type AskUserOption = {
  id: string;
  label: string;
  input?: boolean;
};

// 原则：标签在邀请用户写出内容，而不是给出可直接采用的完整答案。
const INPUT_HINT =
  /我来描述|我来写|我来说|说说看|自己说|自己写|自行填写|自行描述|自定义|补充说明|不限于|please specify|write your own|^(其他|其它|Other)$|^(其他|其它|Other)[（(—\-\s:：]/;

export function optionInvitesInput(label: string): boolean {
  const text = (label || "").trim();
  return Boolean(text && INPUT_HINT.test(text));
}

export function optionAllowsInput(
  option: AskUserOption,
  opts?: { sandbox?: boolean },
): boolean {
  if (opts?.sandbox) return false;
  if (option.input === true) return true;
  return optionInvitesInput(option.label);
}

export function formatChoiceLabel(label: string, inputText?: string): string {
  const note = (inputText || "").trim();
  return note ? `${label}：${note}` : label;
}

export function optionIsChosen(label: string, resolved: string): boolean {
  if (!label || !resolved) return false;
  if (resolved === label) return true;
  if (resolved.startsWith(`${label}：`) || resolved.startsWith(`${label}:`)) {
    return true;
  }
  return resolved.split("、").some(
    (part) =>
      part === label ||
      part.startsWith(`${label}：`) ||
      part.startsWith(`${label}:`),
  );
}

export function extractChoiceNote(label: string, resolved: string): string {
  if (!label || !resolved) return "";
  const prefixes = [`${label}：`, `${label}:`];
  const candidates = [resolved, ...resolved.split("、")];
  for (const part of candidates) {
    for (const prefix of prefixes) {
      if (part.startsWith(prefix)) return part.slice(prefix.length);
    }
  }
  return "";
}
