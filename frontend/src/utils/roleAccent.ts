/** 用角色 id 生成稳定色相，作无头像时的识别色。 */
export function roleAccent(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return `hsl(${h % 360} 38% 42%)`;
}
