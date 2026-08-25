import { useRef, useState } from "react";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Role = "user" | "assistant";
type MsgStatus = "done" | "streaming" | "error";

interface Message {
  id: number;
  role: Role;
  content: string;
  status: MsgStatus;
  toolCalls?: string[];  // descriptions of SQL queries fired
}

function isSectionHeader(line: string): boolean {
  const t = line.trim();
  return t.length > 3 && t === t.toUpperCase() && /^[A-Z\s&\-\/]+$/.test(t);
}

function MessageText({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <div style={{ fontSize: 13, lineHeight: 1.75, color: "#1A2744" }}>
      {text.split("\n").map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} style={{ height: 6 }} />;
        if (isSectionHeader(t)) return (
          <div key={i} style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.12em",
            textTransform: "uppercase", color: "#E8700A",
            marginTop: i === 0 ? 0 : 14, marginBottom: 4,
            paddingBottom: 3, borderBottom: "1px solid #e8eef6",
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
          }}>{t}</div>
        );
        if (t.startsWith("•") || t.startsWith("-")) return (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4, fontFamily: "Georgia, serif" }}>
            <span style={{ color: "#E8700A", flexShrink: 0 }}>•</span>
            <span>{t.replace(/^[•\-]\s*/, "")}</span>
          </div>
        );
        const nm = t.match(/^(\d+)\.\s+(.+)/);
        if (nm) return (
          <div key={i} style={{ display: "flex", gap: 10, marginBottom: 5, fontFamily: "Georgia, serif" }}>
            <span style={{
              background: "#1A2744", color: "#fff", borderRadius: "50%",
              width: 18, height: 18, display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 9, fontWeight: 700,
              flexShrink: 0, marginTop: 3, fontFamily: "monospace",
            }}>{nm[1]}</span>
            <span>{nm[2]}</span>
          </div>
        );
        return <p key={i} style={{ margin: "0 0 5px", fontFamily: "Georgia, serif", color: "#2A3A58" }}>{t}</p>;
      })}
      {streaming && (
        <span style={{
          display: "inline-block", width: 2, height: "1em",
          background: "#E8700A", marginLeft: 1,
          animation: "blink 0.8s step-end infinite", verticalAlign: "text-bottom",
        }} />
      )}
      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}`}</style>
    </div>
  );
}

const SAMPLE_QUESTIONS: Record<string, string[]> = {
  tx: [
    "Which counties should we prioritize for vaccination outreach this month?",
    "Design an intervention plan for the Permian Basin cluster",
    "How do we approach vaccine-hesitant communities with high religious exemption rates?",
    "How many children are unprotected in HIGH and CRITICAL counties?",
    "What does the wastewater signal actually tell us, and what are its limitations?",
    "Compare risk profiles of our top 10 most at-risk counties",
    "Which border counties need immediate attention and why?",
    "Explain how measles achieves outbreak conditions — what has to go wrong?",
    "What early warning signs preceded the Gaines County 2025 outbreak?",
    "How should we communicate risk to parents in exemption-heavy communities?",
  ],
  id: [
    "Which Idaho counties have the highest non-medical exemption rates and what does that mean?",
    "Design an outreach plan for Blaine County's high-exemption community",
    "How does Idaho's philosophical exemption policy compare to neighboring states?",
    "How many Idaho children are unprotected in HIGH and CRITICAL counties?",
    "What importation risk do Bonner and Boundary counties face from Canada?",
    "Compare risk profiles of Idaho's top 10 most at-risk counties",
    "Explain what makes Blaine and Teton counties particularly high-risk",
    "How should we approach vaccine-hesitant families in rural Idaho communities?",
    "What would a measles outbreak in a rural Idaho county actually look like?",
    "How should public health communicate risk without increasing vaccine resistance?",
  ],
  pa: [
    "Which Pennsylvania counties are at highest risk and why?",
    "Design an intervention plan for the central PA Amish belt",
    "How should we approach outreach in Lancaster County's Amish community?",
    "How many unvaccinated children live in HIGH and CRITICAL Pennsylvania counties?",
    "What's the relationship between religious exemptions and outbreak risk in PA?",
    "Compare risk profiles of Pennsylvania's top 10 most at-risk counties",
    "What early warning signs should we watch for in Lancaster County?",
    "How do we communicate risk without stigmatizing religious communities?",
    "What makes the Mifflin-Juniata-Snyder cluster uniquely dangerous?",
    "Explain the epidemiological risk of a measles outbreak in an Amish community.",
  ],
};

interface Props {
  state?: string;
  stateName?: string;
}

export function QueryPanel({ state = "tx", stateName }: Props = {}) {
  const questions = SAMPLE_QUESTIONS[state] ?? SAMPLE_QUESTIONS.tx;
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput]       = useState("");
  const [busy, setBusy]         = useState(false);
  const abortRef                = useRef<AbortController | null>(null);
  const bottomRef               = useRef<HTMLDivElement>(null);
  const inputRef                = useRef<HTMLTextAreaElement>(null);
  let nextId                    = useRef(0);

  const scrollBottom = () => setTimeout(() =>
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50
  );

  const send = async (question: string) => {
    if (!question.trim() || busy) return;
    const q = question.trim();
    setInput("");

    // Build history for API (only completed assistant messages)
    const history = messages.flatMap((m) =>
      m.status === "done"
        ? [{ role: m.role, content: m.content }]
        : []
    );

    const userMsg: Message = { id: nextId.current++, role: "user", content: q, status: "done" };
    const botId = nextId.current++;
    const botMsg: Message = { id: botId, role: "assistant", content: "", status: "streaming", toolCalls: [] };

    setMessages((prev) => [...prev, userMsg, botMsg]);
    setBusy(true);
    scrollBottom();

    abortRef.current = new AbortController();
    try {
      const resp = await fetch(`${BASE}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history, state }),
        signal: abortRef.current.signal,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n"); buf = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") {
            setMessages((prev) => prev.map((m) =>
              m.id === botId ? { ...m, status: "done" } : m
            ));
            setBusy(false);
            scrollBottom();
            return;
          }
          try {
            const e = JSON.parse(raw) as { type: string; delta?: string; message?: string; description?: string };
            if (e.type === "text" && e.delta) {
              setMessages((prev) => prev.map((m) =>
                m.id === botId ? { ...m, content: m.content + e.delta } : m
              ));
              scrollBottom();
            } else if (e.type === "tool_call" && e.description) {
              setMessages((prev) => prev.map((m) =>
                m.id === botId ? { ...m, toolCalls: [...(m.toolCalls ?? []), e.description!] } : m
              ));
            } else if (e.type === "error") {
              setMessages((prev) => prev.map((m) =>
                m.id === botId ? { ...m, content: e.message ?? "Error", status: "error" } : m
              ));
              setBusy(false);
              return;
            }
          } catch { /* skip */ }
        }
      }

      setMessages((prev) => prev.map((m) =>
        m.id === botId ? { ...m, status: "done" } : m
      ));
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        setMessages((prev) => prev.map((m) =>
          m.id === botId ? { ...m, status: "done" } : m
        ));
      } else {
        setMessages((prev) => prev.map((m) =>
          m.id === botId
            ? { ...m, content: err instanceof Error ? err.message : "Request failed", status: "error" }
            : m
        ));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  return (
    <div style={{
      height: "100%", display: "flex", flexDirection: "column",
      fontFamily: "'Trebuchet MS', Arial, sans-serif",
    }}>
      {/* Header */}
      <div style={{
        background: "#fff", borderBottom: "1px solid #D0DAE8",
        padding: "12px 28px", flexShrink: 0,
      }}>
        <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.14em", color: "#7A92AB", marginBottom: 2 }}>
          AI Advisor
        </div>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#1A2744" }}>
          Ask anything about measles, public health response, or the {stateName ?? "state"} data
        </div>
        <div style={{ fontSize: 11, color: "#7A92AB", marginTop: 2 }}>
          Outbreak analysis · Intervention planning · Epidemiology · Policy · Community engagement
        </div>
      </div>

      {/* Message area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 28px" }}>
        {messages.length === 0 && (
          <div>
            <div style={{ fontSize: 12, color: "#7A92AB", marginBottom: 14 }}>
              Ask about the data, measles biology, outbreak history, intervention design, or communication strategy — or try a sample:
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {questions.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  style={{
                    background: "#f4f7fb", border: "1px solid #D0DAE8",
                    borderRadius: 20, padding: "7px 14px",
                    fontSize: 12, color: "#1A2744", cursor: "pointer",
                    fontFamily: "'Trebuchet MS', Arial, sans-serif",
                    transition: "background 0.12s",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#e8f0fb")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "#f4f7fb")}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} style={{
            display: "flex",
            flexDirection: msg.role === "user" ? "row-reverse" : "row",
            marginBottom: 16, gap: 10, alignItems: "flex-start",
          }}>
            {/* Avatar */}
            <div style={{
              width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
              background: msg.role === "user" ? "#1A2744" : "#E8700A",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, fontWeight: 700, color: "#fff",
              fontFamily: "monospace",
            }}>
              {msg.role === "user" ? "U" : "AI"}
            </div>

            <div style={{ maxWidth: "75%", minWidth: 80 }}>
              {/* Tool calls pill */}
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div style={{ marginBottom: 6 }}>
                  {msg.toolCalls.map((tc, i) => (
                    <div key={i} style={{
                      display: "inline-flex", alignItems: "center", gap: 5,
                      background: "#f0f4f8", border: "1px solid #D0DAE8",
                      borderRadius: 12, padding: "3px 10px", fontSize: 10.5,
                      color: "#4A5E78", marginRight: 6, marginBottom: 4,
                    }}>
                      <span style={{ fontSize: 9, color: "#7A92AB" }}>SQL</span>
                      {tc}
                    </div>
                  ))}
                </div>
              )}

              {/* Bubble */}
              <div style={{
                background: msg.role === "user" ? "#1A2744" : "#fff",
                color: msg.role === "user" ? "#fff" : "#1A2744",
                border: msg.role === "user" ? "none" : "1px solid #D0DAE8",
                borderRadius: msg.role === "user" ? "16px 16px 4px 16px" : "4px 16px 16px 16px",
                padding: "10px 14px",
                ...(msg.status === "error" ? { background: "#fceaea", border: "1px solid #f0c0c0", color: "#C22828" } : {}),
              }}>
                {msg.role === "user"
                  ? <span style={{ fontSize: 13, lineHeight: 1.5 }}>{msg.content}</span>
                  : msg.status === "streaming" && !msg.content
                    ? (
                      <div style={{ display: "flex", gap: 5, alignItems: "center", padding: "4px 0" }}>
                        {[0, 1, 2].map((i) => (
                          <div key={i} style={{
                            width: 6, height: 6, borderRadius: "50%", background: "#E8700A",
                            animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                          }} />
                        ))}
                        <span style={{ fontSize: 11, color: "#7A92AB", marginLeft: 4 }}>Querying database…</span>
                      </div>
                    )
                    : <MessageText text={msg.content} streaming={msg.status === "streaming"} />
                }
              </div>
            </div>
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={{
        background: "#fff", borderTop: "1px solid #D0DAE8",
        padding: "12px 20px", flexShrink: 0,
        display: "flex", gap: 10, alignItems: "flex-end",
      }}>
        {messages.length > 0 && (
          <button
            onClick={() => { abortRef.current?.abort(); setMessages([]); setBusy(false); }}
            title="Clear conversation"
            style={{
              background: "#f4f7fb", border: "1px solid #D0DAE8", borderRadius: 6,
              padding: "8px 12px", fontSize: 11, color: "#7A92AB", cursor: "pointer",
              fontFamily: "'Trebuchet MS', Arial, sans-serif", flexShrink: 0, alignSelf: "flex-end",
              marginBottom: 1,
            }}
          >
            Clear
          </button>
        )}
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          disabled={busy}
          placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
          rows={2}
          style={{
            flex: 1, resize: "none", border: "1px solid #D0DAE8", borderRadius: 8,
            padding: "10px 14px", fontSize: 13, color: "#1A2744",
            fontFamily: "'Trebuchet MS', Arial, sans-serif", lineHeight: 1.5,
            outline: "none", background: busy ? "#f9fafc" : "#fff",
          }}
        />
        <button
          onClick={() => send(input)}
          disabled={busy || !input.trim()}
          style={{
            background: busy || !input.trim() ? "#D0DAE8" : "#1A2744",
            color: busy || !input.trim() ? "#7A92AB" : "#fff",
            border: "none", borderRadius: 8, padding: "10px 20px",
            fontSize: 13, fontWeight: 700,
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
            cursor: busy || !input.trim() ? "not-allowed" : "pointer",
            flexShrink: 0, alignSelf: "flex-end",
            transition: "background 0.15s",
          }}
        >
          {busy ? "…" : "Ask"}
        </button>
      </div>

      <style>{`@keyframes pulse{0%,100%{opacity:0.3;transform:scale(0.8)}50%{opacity:1;transform:scale(1.2)}}`}</style>
    </div>
  );
}
