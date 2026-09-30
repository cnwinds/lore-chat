export function statusLabel(status: string): string | null {
  switch (status) {
    case "ok":
      return null;
    case "error":
      return "失败";
    case "aborted":
      return "中断";
    case "pending":
      return "未完成";
    default:
      return status;
  }
}
