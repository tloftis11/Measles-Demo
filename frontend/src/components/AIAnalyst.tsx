import { useCallback, useEffect, useRef, useState } from "react";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Status = "idle" | "loading" | "streaming" | "done" | "error";

function isSectionHeader(line: string): boolean {
  const t = line.trim();
  return t.length > 3 && t === t.toUpperCase() && /^[A-Z\s&\-]+$/.test(t);
}

function AnalysisText({ text, streaming }: { text: string; streaming: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (streaming) bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [text, streaming]);

  return (
    <div style={{ fontSize: 13, lineHeight: 1.75, color: "#1A2744" }}>
      {text.split("\n").map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} style={{ height: 8 }} />;
        if (isSectionHeader(t)) return (
          <div key={i} style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.12em",
            textTransform: "uppercase", color: "#E8700A",
            marginTop: i === 0 ? 0 : 16, marginBottom: 6,
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

interface Props {
  fips: string;
  countyName: string;
  autoRun?: boolean;
}

export function AIAnalyst({ fips, countyName, autoRun }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [text, setText] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  // Core fetch — takes fips + signal so it's free of stale closure issues
  const doFetch = useCallback(async (targetFips: string, signal: AbortSignal) => {
    setText("");
    setErrorMsg("");
    setStatus("loading");
    try {
      const resp = await fetch(`${BASE}/api/ai/analyst`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fips: targetFips, state: "tx" }),
        signal,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      setStatus("streaming");

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
            const evt = JSON.parse(raw) as { type: string; delta?: string; message?: string };
            if (evt.type === "text" && evt.delta) setText((p) => p + evt.delta);
            else if (evt.type === "error") { setErrorMsg(evt.message ?? "Error"); setStatus("error"); return; }
          } catch { /* skip */ }
        }
      }
      setStatus("done");
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") { setStatus("idle"); return; }
      setErrorMsg(err instanceof Error ? err.message : "Request failed");
      setStatus("error");
    }
  }, []);

  // When fips changes: reset + auto-start if autoRun
  useEffect(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    if (autoRun) {
      doFetch(fips, ctrl.signal);
    } else {
      setStatus("idle");
      setText("");
      setErrorMsg("");
    }
    return () => ctrl.abort();
  }, [fips, autoRun, doFetch]);

  const handleClick = () => {
    if (status === "streaming" || status === "loading") {
      abortRef.current?.abort();
      setStatus("idle");
      return;
    }
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    doFetch(fips, ctrl.signal);
  };

  const isDone   = status === "done";
  const isActive = status === "streaming" || status === "loading";

  return (
    <div>
      {/* Status row */}
      <div style={{
        display: "flex", alignItems: "center",
        justifyContent: "space-between", marginBottom: 14,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div style={{
            width: 7, height: 7, borderRadius: "50%",
            background: status === "streaming" ? "#E8700A"
              : isDone ? "#1E8A4C" : "#C0CBD8",
            animation: status === "streaming" ? "aiPulse 1.2s ease-in-out infinite" : "none",
          }} />
          <span style={{
            fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em",
            color: "#7A92AB", fontFamily: "'Trebuchet MS', Arial, sans-serif",
          }}>
            {status === "loading"   ? `Analyzing ${countyName}…`
             : status === "streaming" ? "Streaming analysis"
             : isDone               ? "Analysis complete"
             : "Claude Opus · AI Analysis"}
          </span>
        </div>

        {/* Show button once there's something to do — not on first idle in autoRun */}
        {(isDone || isActive || status === "error" || (!autoRun && status === "idle")) && (
          <button
            onClick={handleClick}
            disabled={status === "loading"}
            style={{
              background: isActive ? "#fff3e8" : "#f0f4f8",
              color: isActive ? "#D45F00" : "#4A5E78",
              border: isActive ? "1px solid #D45F00" : "1px solid #D0DAE8",
              borderRadius: 5, padding: "4px 11px",
              fontSize: 11, fontWeight: 700,
              fontFamily: "'Trebuchet MS', Arial, sans-serif",
              cursor: status === "loading" ? "not-allowed" : "pointer",
              opacity: status === "loading" ? 0.5 : 1,
              transition: "all 0.15s",
            }}
          >
            {status === "loading" ? "Thinking…" : isActive ? "Stop" : "Re-run"}
          </button>
        )}
      </div>

      {/* Loading dots */}
      {status === "loading" && (
        <div style={{ display: "flex", gap: 5, alignItems: "center", padding: "8px 0 14px" }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{
              width: 7, height: 7, borderRadius: "50%", background: "#E8700A",
              animation: `aiPulse 1.2s ease-in-out ${i * 0.2}s infinite`,
            }} />
          ))}
          <span style={{ fontSize: 11, color: "#7A92AB", marginLeft: 6, fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>
            Analyzing {countyName} County…
          </span>
        </div>
      )}

      {/* Idle state — only shown in manual mode */}
      {status === "idle" && !autoRun && (
        <div style={{
          background: "#f6f8fc", border: "1px solid #D0DAE8",
          borderRadius: 8, padding: "20px 16px", textAlign: "center",
        }}>
          <div style={{ fontSize: 12, color: "#7A92AB", marginBottom: 12, fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>
            AI analysis of {countyName} County — risk drivers, trend context, and recommended actions.
          </div>
          <button
            onClick={handleClick}
            style={{
              background: "#1A2744", color: "#fff", border: "none",
              borderRadius: 6, padding: "8px 20px",
              fontSize: 12, fontWeight: 700, cursor: "pointer",
              fontFamily: "'Trebuchet MS', Arial, sans-serif",
            }}
          >
            Run AI Analysis
          </button>
        </div>
      )}

      {/* Error */}
      {status === "error" && (
        <div style={{
          background: "#fceaea", border: "1px solid #f0c0c0",
          borderRadius: 6, padding: "10px 14px",
          fontSize: 12, color: "#C22828", lineHeight: 1.5,
          fontFamily: "'Trebuchet MS', Arial, sans-serif",
        }}>
          {errorMsg || "Analysis failed — check ANTHROPIC_API_KEY"}
        </div>
      )}

      {/* Analysis text */}
      {(status === "streaming" || isDone) && text && (
        <div style={{
          background: "#f9fafc", border: "1px solid #e0e8f4",
          borderRadius: 8, padding: "16px",
        }}>
          <AnalysisText text={text} streaming={status === "streaming"} />
        </div>
      )}

      <style>{`
        @keyframes aiPulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50%       { opacity: 1;   transform: scale(1.2); }
        }
      `}</style>
    </div>
  );
}
