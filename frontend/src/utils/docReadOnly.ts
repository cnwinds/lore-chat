export function isReadOnlyPath(path: string): boolean {
  const norm = path.replace(/\\/g, "/");
  return (
    norm.startsWith(".kb/") ||
    norm.startsWith(".git/") ||
    norm === ".kb" ||
    norm === ".git"
  );
}
