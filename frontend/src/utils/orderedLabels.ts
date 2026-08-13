/** 按预定义顺序排列键名，未知键按 zh-CN 排在已知键之后。 */
export function orderedKeys(keys: string[], order: readonly string[]): string[] {
  const orderIndex = (key: string) => {
    const i = order.indexOf(key);
    return i === -1 ? order.length : i;
  };
  return [...keys].sort((a, b) => {
    const d = orderIndex(a) - orderIndex(b);
    if (d !== 0) return d;
    return a.localeCompare(b, "zh-CN");
  });
}

export function labelFor(key: string, labels: Record<string, string>): string {
  return labels[key] ?? key;
}
