import { useEffect, useState } from "react";
import { getTree, getQuestions, resolveQuestion } from "../api";

type QuestionOption = { id: string; label: string };
type Question = { id: string; question: string; options: QuestionOption[] };

export function Sidebar() {
  const [docs, setDocs] = useState<string[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);

  async function refresh() {
    setDocs((await getTree()).docs);
    setQuestions((await getQuestions()).questions);
  }
  useEffect(() => {
    refresh();
  }, []);

  return (
    <div
      style={{
        width: 280,
        borderRight: "1px solid #eee",
        padding: 12,
        overflowY: "auto",
      }}
    >
      <h4>待我确认</h4>
      {questions.length === 0 && <div style={{ color: "#999" }}>无</div>}
      {questions.map((q) => (
        <div key={q.id} style={{ marginBottom: 12, fontSize: 13 }}>
          <div>{q.question}</div>
          {q.options.map((o) => (
            <button
              key={o.id}
              onClick={async () => {
                await resolveQuestion(q.id, o.id);
                refresh();
              }}
              style={{ marginRight: 6, marginTop: 4 }}
            >
              {o.label}
            </button>
          ))}
        </div>
      ))}
      <h4 style={{ marginTop: 16 }}>知识库目录</h4>
      {docs.map((d) => (
        <div key={d} style={{ fontSize: 13, padding: "2px 0" }}>
          {d}
        </div>
      ))}
      <button onClick={refresh} style={{ marginTop: 12 }}>
        刷新
      </button>
    </div>
  );
}
