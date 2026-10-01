/** 用量/费用展示：无货币符号，与价目表单位一致。 */
export function fmtCost(n: number | null | undefined, known: boolean): string {
  if (!known || n == null) return "—";
  if (n < 0.01) return n.toFixed(6);
  if (n < 1) return n.toFixed(4);
  return n.toFixed(2);
}
