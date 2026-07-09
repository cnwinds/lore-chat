const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function ingest(text: string) {
  const r = await fetch(`${BASE}/api/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function ask(query: string) {
  const r = await fetch(`${BASE}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  return r.json();
}

export async function uploadFile(file: File, category: string) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("category", category);
  const r = await fetch(`${BASE}/api/upload`, { method: "POST", body: fd });
  return r.json();
}

export async function getTree() {
  const r = await fetch(`${BASE}/api/tree`);
  return r.json();
}

export async function getQuestions() {
  const r = await fetch(`${BASE}/api/questions`);
  return r.json();
}

export async function resolveQuestion(qid: string, choice: string) {
  const r = await fetch(`${BASE}/api/questions/${qid}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ choice }),
  });
  return r.json();
}

export function downloadUrl(path: string) {
  return `${BASE}/api/download?path=${encodeURIComponent(path)}`;
}
