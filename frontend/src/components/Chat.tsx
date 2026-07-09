import { useState } from "react";
import { ingest, ask, uploadFile, downloadUrl } from "../api";

type Msg = {
  role: "user" | "assistant";
  text: string;
  sources?: string[];
  attachments?: string[];
};

export function Chat() {
  const [mode, setMode] = useState<"remember" | "recall">("remember");
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);

  async function send() {
    if (!input.trim()) return;
    const text = input;
    setMsgs((m) => [...m, { role: "user", text }]);
    setInput("");
    if (mode === "remember") {
      const r = await ingest(text);
      setMsgs((m) => [...m, { role: "assistant", text: r.message }]);
    } else {
      const r = await ask(text);
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: r.text,
          sources: r.sources,
          attachments: r.attachments,
        },
      ]);
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = await uploadFile(f, "未分类");
    setMsgs((m) => [
      ...m,
      { role: "assistant", text: `已保存文件：${r.attachment}` },
    ]);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: 8 }}>
        <button onClick={() => setMode("remember")} disabled={mode === "remember"}>
          记录
        </button>
        <button onClick={() => setMode("recall")} disabled={mode === "recall"}>
          提问
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
        {msgs.map((m, i) => (
          <div
            key={i}
            style={{
              margin: "8px 0",
              textAlign: m.role === "user" ? "right" : "left",
            }}
          >
            <div
              style={{
                display: "inline-block",
                padding: "8px 12px",
                borderRadius: 8,
                background: m.role === "user" ? "#daf1ff" : "#f0f0f0",
              }}
            >
              {m.text}
              {m.sources && m.sources.length > 0 && (
                <div style={{ fontSize: 12, color: "#666", marginTop: 6 }}>
                  来源：{m.sources.join("、")}
                </div>
              )}
              {m.attachments &&
                m.attachments.map((a) => (
                  <div key={a}>
                    <a href={downloadUrl(a)}>下载附件：{a.split("/").pop()}</a>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", padding: 8, gap: 8 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={
            mode === "remember"
              ? "告诉我要记住的内容…"
              : "问我任何已记录的内容…"
          }
          style={{ flex: 1, padding: 8 }}
        />
        <label style={{ padding: 8, cursor: "pointer" }}>
          📎
          <input type="file" hidden onChange={onFile} />
        </label>
        <button onClick={send}>发送</button>
      </div>
    </div>
  );
}
