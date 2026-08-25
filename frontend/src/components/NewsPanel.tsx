import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { NewsBriefing } from "../types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Status = "loading" | "streaming" | "done" | "error";

function isSectionHeader(line: string): boolean {
  const t = line.trim();
  return t.length > 3 && t === t.toUpperCase() && /^[A-Z\s&\-/]+$/.test(t);
}

function formatAge(fetchedAt: string | null): string {
  if (!fetchedAt) return "";
  const fetched = new Date(fetchedAt);
  const ageMs = Date.now() - fetched.getTime();
  const ageMin = Math.floor(ageMs / 60000);
  if (ageMin < 2) return "just now";
  if (ageMin < 60) return `${ageMin} min ago`;
  const ageHr = Math.floor(ageMin / 60);
  if (ageHr < 24) return `${ageHr}h ago`;
  return `${Math.floor(ageHr / 24)}d ago`;
}

function BriefingText({ text, streaming }: { text: string; streaming: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (streaming) bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [text, streaming]);

  const lines = text.split("\n");
  const sourcesIdx = lines.findIndex((l) => isSectionHeader(l.trim()) && l.trim() === "SOURCES");
  const bodyLines = sourcesIdx >= 0 ? lines.slice(0, sourcesIdx) : lines;

  return (
    <div style={{ fontSize: 13, lineHeight: 1.75, color: "#1A2744" }}>
      {bodyLines.map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} style={{ height: 8 }} />;
        if (isSectionHeader(t)) return (
          <div key={i} style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.12em",
            textTransform: "uppercase", color: "#E8700A",
            marginTop: i === 0 ? 0 : 18, marginBottom: 6,
            paddingBottom: 4, borderBottom: "1px solid #e8eef6",
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
          }}>{t}</div>
        );
        if (t.startsWith("•") || t.startsWith("-")) return (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5, fontFamily: "Georgia, serif" }}>
            <span style={{ color: "#E8700A", flexShrink: 0, marginTop: 1 }}>•</span>
            <span style={{ color: "#1A2744" }}>{t.replace(/^[•\-]\s*/, "")}</span>
          </div>
        );
        const nm = t.match(/^(\d+)\.\s+(.+)/);
        if (nm) return (
          <div key={i} style={{ display: "flex", gap: 10, marginBottom: 6, fontFamily: "Georgia, serif" }}>
            <span style={{
              background: "#1A2744", color: "#fff", borderRadius: "50%",
              width: 20, height: 20, display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 10, fontWeight: 700,
              flexShrink: 0, marginTop: 2, fontFamily: "monospace",
            }}>{nm[1]}</span>
            <span style={{ color: "#1A2744" }}>{nm[2]}</span>
          </div>
        );
        return <p key={i} style={{ margin: "0 0 6px", fontFamily: "Georgia, serif", color: "#2A3A58" }}>{t}</p>;
      })}
      {streaming && (
        <span style={{
          display: "inline-block", width: 2, height: "1em",
          background: "#E8700A", marginLeft: 1,
          animation: "blink 0.8s step-end infinite", verticalAlign: "text-bottom",
        }} />
      )}
      <div ref={bottomRef} />
      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}`}</style>
    </div>
  );
}

function SourcesList({ sources }: { sources: string[] }) {
  if (!sources.length) return null;
  return (
    <div style={{
      marginTop: 20, paddingTop: 16, borderTop: "1px solid #e0e8f4",
    }}>
      <div style={{
        fontSize: 10, fontWeight: 700, letterSpacing: "0.12em",
        textTransform: "uppercase", color: "#E8700A",
        marginBottom: 10, fontFamily: "'Trebuchet MS', Arial, sans-serif",
      }}>Sources</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {sources.map((url, i) => {
          let domain = url;
          try { domain = new URL(url).hostname.replace(/^www\./, ""); } catch { /* keep raw */ }
          return (
            <a
              key={i}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                fontSize: 12, color: "#2662C8", textDecoration: "none",
                fontFamily: "'Trebuchet MS', Arial, sans-serif",
                display: "flex", alignItems: "center", gap: 6,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.textDecoration = "underline")}
              onMouseLeave={(e) => (e.currentTarget.style.textDecoration = "none")}
            >
              <span style={{
                display: "inline-block", width: 16, height: 16,
                background: "#e8eef6", borderRadius: 3,
                fontSize: 9, fontWeight: 700, color: "#4A5E78",
                flexShrink: 0, textAlign: "center", lineHeight: "16px",
              }}>{i + 1}</span>
              <span style={{ color: "#7A92AB", flexShrink: 0, fontSize: 11 }}>{domain}</span>
              <span style={{
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                minWidth: 0, color: "#2662C8",
              }}>{url}</span>
            </a>
          );
        })}
      </div>
    </div>
  );
}

const STATE_LABELS: Record<string, string> = { tx: "Texas", id: "Idaho", pa: "Pennsylvania" };

export function NewsPanel({ state = "tx" }: { state?: string }) {
  const [status, setStatus] = useState<Status>("loading");
  const [text, setText] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const startRefresh = useCallback(async (currentState: string, signal: AbortSignal) => {
    setText("");
    setSources([]);
    setErrorMsg("");
    setStatus("streaming");
    try {
      const resp = await fetch(`${BASE}/api/news/refresh?state=${currentState}`, { method: "POST", signal });
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
          if (raw === "[DONE]") { setStatus("done"); return; }
          try {
            const evt = JSON.parse(raw) as {
              type: string; delta?: string; message?: string;
              fetched_at?: string; briefing?: string; sources?: string[];
            };
            if (evt.type === "text" && evt.delta) {
              setText((p) => p + evt.delta);
            } else if (evt.type === "done") {
              if (evt.briefing) setText(evt.briefing);
              if (evt.sources) setSources(evt.sources);
              if (evt.fetched_at) setFetchedAt(evt.fetched_at);
              setStatus("done");
              return;
            } else if (evt.type === "error") {
              setErrorMsg(evt.message ?? "Error"); setStatus("error"); return;
            }
          } catch { /* skip */ }
        }
      }
      setStatus("done");
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      setErrorMsg(err instanceof Error ? err.message : "Request failed");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setText("");
    setSources([]);
    setFetchedAt(null);
    setStatus("loading");

    api.getNews(state).then((cached: NewsBriefing) => {
      if (ctrl.signal.aborted) return;
      if (cached.is_fresh && cached.briefing) {
        setText(cached.briefing);
        setSources(cached.sources);
        setFetchedAt(cached.fetched_at);
        setStatus("done");
      } else {
        startRefresh(state, ctrl.signal);
      }
    }).catch(() => {
      if (!ctrl.signal.aborted) startRefresh(state, ctrl.signal);
    });

    return () => ctrl.abort();
  }, [state, startRefresh]);

  const handleRefresh = () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    startRefresh(state, ctrl.signal);
  };

  const isStreaming = status === "streaming";

  return (
    <div style={{
      height: "100%", display: "flex", flexDirection: "column",
      background: "#f6f8fc", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        background: "#fff", borderBottom: "1px solid #e0e8f4",
        padding: "14px 24px", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <div style={{
            fontSize: 14, fontWeight: 700, color: "#1A2744",
            fontFamily: "'Trebuchet MS', Arial, sans-serif", letterSpacing: "0.03em",
          }}>
            {STATE_LABELS[state] ?? state.toUpperCase()} Measles Intelligence Briefing
          </div>
          <div style={{
            fontSize: 11, color: "#7A92AB", marginTop: 2,
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
            display: "flex", alignItems: "center", gap: 8,
          }}>
            {isStreaming ? (
              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ color: "#E8700A", fontWeight: 700 }}>Live</span>
                — fetching {STATE_LABELS[state] ?? state.toUpperCase()} measles intelligence via web search
              </span>
            ) : status === "loading" ? (
              "Checking cache…"
            ) : status === "error" ? (
              <span style={{ color: "#C22828" }}>Fetch failed</span>
            ) : fetchedAt ? (
              <>
                <span style={{
                  background: "#e8f4ec", color: "#1E8A4C",
                  borderRadius: 3, padding: "1px 6px",
                  fontSize: 10, fontWeight: 700, letterSpacing: "0.06em",
                  fontFamily: "'Trebuchet MS', Arial, sans-serif",
                }}>CACHED</span>
                Updated {formatAge(fetchedAt)} · refreshes every 6 hours
              </>
            ) : "AI-synthesized from live web search · Claude Opus"}
          </div>
        </div>

        <button
          onClick={handleRefresh}
          disabled={isStreaming || status === "loading"}
          style={{
            background: isStreaming ? "#fff3e8" : "#f0f4f8",
            color: isStreaming ? "#D45F00" : "#4A5E78",
            border: isStreaming ? "1px solid #D45F00" : "1px solid #D0DAE8",
            borderRadius: 5, padding: "5px 12px",
            fontSize: 11, fontWeight: 700,
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
            cursor: (isStreaming || status === "loading") ? "not-allowed" : "pointer",
            opacity: (isStreaming || status === "loading") ? 0.6 : 1,
            transition: "all 0.15s",
          }}
        >
          {isStreaming ? "Fetching…" : "Refresh"}
        </button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>

        {/* Initial loading state */}
        {status === "loading" && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "24px 0" }}>
            {[0, 1, 2].map((i) => (
              <div key={i} style={{
                width: 8, height: 8, borderRadius: "50%", background: "#E8700A",
                animation: `newsPulse 1.2s ease-in-out ${i * 0.2}s infinite`,
              }} />
            ))}
            <span style={{ fontSize: 12, color: "#7A92AB", fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>
              Checking for cached briefing…
            </span>
          </div>
        )}

        {/* Streaming indicator banner */}
        {isStreaming && !text && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 0" }}>
            {[0, 1, 2].map((i) => (
              <div key={i} style={{
                width: 8, height: 8, borderRadius: "50%", background: "#E8700A",
                animation: `newsPulse 1.2s ease-in-out ${i * 0.2}s infinite`,
              }} />
            ))}
            <span style={{ fontSize: 12, color: "#7A92AB", fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>
              Searching for measles intelligence — this may take 30–60 seconds…
            </span>
          </div>
        )}

        {/* Error */}
        {status === "error" && (
          <div style={{
            background: "#fceaea", border: "1px solid #f0c0c0",
            borderRadius: 8, padding: "14px 18px",
            fontSize: 13, color: "#C22828", lineHeight: 1.6,
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
          }}>
            <strong>Fetch failed</strong> — {errorMsg || "Check ANTHROPIC_API_KEY and web search access."}<br />
            <span style={{ fontSize: 11, color: "#C22828", opacity: 0.8 }}>
              Try refreshing. Web search requires a supported Claude model and API key.
            </span>
          </div>
        )}

        {/* Briefing text */}
        {text && (
          <div style={{
            background: "#fff", border: "1px solid #e0e8f4",
            borderRadius: 10, padding: "20px 22px",
            boxShadow: "0 1px 6px rgba(0,0,0,0.04)",
          }}>
            <BriefingText text={text} streaming={isStreaming} />
            {!isStreaming && <SourcesList sources={sources} />}
          </div>
        )}
      </div>

      <style>{`
        @keyframes newsPulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50%       { opacity: 1;   transform: scale(1.2); }
        }
      `}</style>
    </div>
  );
}
