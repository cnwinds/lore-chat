/** 左栏副标题只用人设，不用最后一条消息。 */
export function rolePersonaPreview(role: {
  system_prompt?: string | null;
}): string {
  return (role.system_prompt || "").replace(/\s+/g, " ").trim();
}
