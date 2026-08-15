import { useCallback, useEffect, useRef, useState } from "react";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Status = "idle" | "loading" | "streaming" | "done" | "error";

// Detect ALL-CAPS section headers like "RISK SUMMARY" or "KEY RISK DRIVERS"
function isSectionHeader(line: string): boolean {
  const trimmed = line.trim();
  return (
    trimmed.length > 3 &&
    trimmed === trimmed.toUpperCase() &&
    /^[A-Z\s&\-]+$/.test(trimmed)
  );
}

function AnalysisText({ text, streaming }: { text: string; streaming: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom while streaming
  useEffect(() => {
    if (streaming) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [text, streaming]);

  const lines = text.split("\n");

  return (
    <div style={{ fontSize: 13, lineHeight: 1.7, color: "#1A2744" }}>
      {lines.map((line, i) => {
        const trimmed = line.trim();

        if (trimmed === "") {
          return <div key={i} style={{ height: 8 }} />;
        }

        if (isSectionHeader(trimmed)) {
          return (
            <div key={i} style={{
              fontFamily: "'Trebuchet MS', Arial, sans-serif",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "#E8700A",
              marginTop: i === 0 ? 0 : 16,
              marginBottom: 6,
              paddingBottom: 4,
              borderBottom: "1px solid #e8eef6",
            }}>
              {trimmed}
            </div>
          );
        }

        // Bullet points (• or -)
        if (trimmed.startsWith("•") || trimmed.startsWith("-")) {
          return (
            <div key={i} style={{
              display: "flex",
              gap: 8,
              marginBottom: 5,
              fontFamily: "Georgia, serif",
            }}>
              <span style={{ color: "#E8700A", flexShrink: 0, marginTop: 1 }}>•</span>
              <span style={{ color: "#1A2744" }}>
                {trimmed.replace(/^[•\-]\s*/, "")}
              </span>
            </div>
          );
        }

        // Numbered list items (1. 2. 3. etc.)
        const numMatch = trimmed.match(/^(\d+)\.\s+(.+)/);
        if (numMatch) {
          return (
            <div key={i} style={{
              display: "flex",
              gap: 10,
              marginBottom: 6,
              fontFamily: "Georgia, serif",
            }}>
              <span style={{
                background: "#1A2744",
                color: "#fff",
                borderRadius: "50%",
                width: 20,
                height: 20,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 10,
                fontWeight: 700,
                flexShrink: 0,
                marginTop: 2,
                fontFamily: "monospace",
              }}>
                {numMatch[1]}
              </span>
              <span style={{ color: "#1A2744" }}>{numMatch[2]}</span>
            </div>
          );
        }

        // Normal paragraph text
        return (
          <p key={i} style={{
            margin: "0 0 6px",
            fontFamily: "Georgia, serif",
            color: "#2A3A58",
          }}>
            {trimmed}
          </p>
        );
      })}

      {streaming && (
        <span style={{
          display: "inline-block",
          width: 2,
          height: "1em",
          background: "#E8700A",
          marginLeft: 1,
          animation: "blink 0.8s step-end infinite",
          verticalAlign: "text-bottom",
        }} />
      )}

      <div ref={bottomRef} />
    </div>
  );
}

interface Props {
  fips: string;
  countyName: string;
}

export function AIAnalyst({ fips, countyName }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [text, setText] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  // Reset when county changes
  useEffect(() => {
    abortRef.current?.abort();
    setStatus("idle");
    setText("");
    setErrorMsg("");
  }, [fips]);

  const run = useCallback(async () => {
    if (status === "streaming" || status === "loading") {
      abortRef.current?.abort();
      setStatus("idle");
      return;
    }

    setText("");
    setErrorMsg("");
    setStatus("loading");
    abortRef.current = new AbortController();

    try {
      const resp = await fetch(`${BASE}/api/ai/analyst`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fips, state: "tx" }),
        signal: abortRef.current.signal,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      setStatus("streaming");

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") { setStatus("done"); return; }
          try {
            const evt = JSON.parse(raw) as { type: string; delta?: string; message?: string };
            if (evt.type === "text" && evt.delta) {
              setText((prev) => prev + evt.delta);
            } else if (evt.type === "error") {
              setErrorMsg(evt.message ?? "Unknown error");
              setStatus("error");
              return;
            }
          } catch { /* skip malformed */ }
        }
      }
      setStatus("done");
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") { setStatus("idle"); return; }
      setErrorMsg(err instanceof Error ? err.message : "Request failed");
      setStatus("error");
    }
  }, [fips, status]);

  const buttonLabel =
    status === "loading"   ? "Thinking…"
    : status === "streaming" ? "Stop"
    : status === "done"      ? "Re-run"
    : "Run AI Analysis";

  return (
    <div style={{ borderTop: "1px solid #e8eef6", marginTop: 14, paddingTop: 14 }}>

      {/* Row: label + button */}
      <div style={{
        display: "flex", alignItems: "center",
        justifyContent: "space-between", marginBottom: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{
            width: 6, height: 6, borderRadius: "50%",
            background: status === "streaming" ? "#E8700A" : status === "done" ? "#1E8A4C" : "#7A92AB",
            animation: status === "streaming" ? "pulse 1.2s ease-in-out infinite" : "none",
          }} />
          <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", color: "#7A92AB", fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>
            Claude Opus Analysis
          </span>
        </div>
        <button
          onClick={run}
          disabled={status === "loading"}
          style={{
            background: status === "streaming" ? "#fff3e8"
              : status === "done" ? "#edf2f8"
              : "#1A2744",
            color: status === "streaming" ? "#D45F00"
              : status === "done" ? "#1A2744"
              : "#fff",
            border: status === "streaming" ? "1px solid #D45F00"
              : status === "done" ? "1px solid #D0DAE8"
              : "none",
            borderRadius: 5,
            padding: "5px 12px",
            fontSize: 11,
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
            fontWeight: 700,
            cursor: status === "loading" ? "not-allowed" : "pointer",
            letterSpacing: "0.04em",
            opacity: status === "loading" ? 0.55 : 1,
            transition: "background 0.15s, opacity 0.15s",
          }}
        >
          {buttonLabel}
        </button>
      </div>

      {/* Loading dots */}
      {status === "loading" && (
        <div style={{ display: "flex", gap: 5, alignItems: "center", padding: "6px 0 10px" }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{
              width: 7, height: 7, borderRadius: "50%", background: "#E8700A",
              animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
            }} />
          ))}
          <span style={{ fontSize: 11, color: "#7A92AB", marginLeft: 6, fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>
            Analyzing {countyName} County…
          </span>
        </div>
      )}

      {/* Error */}
      {status === "error" && (
        <div style={{
          background: "#fceaea", border: "1px solid #f0c0c0",
          borderRadius: 6, padding: "10px 12px",
          fontSize: 12, color: "#C22828", lineHeight: 1.5,
          fontFamily: "'Trebuchet MS', Arial, sans-serif",
        }}>
          {errorMsg || "Analysis failed — check that ANTHROPIC_API_KEY is set in backend/.env"}
        </div>
      )}

      {/* Analysis text */}
      {(status === "streaming" || status === "done") && text && (
        <div style={{
          background: "#f9fafc",
          border: "1px solid #e0e8f4",
          borderRadius: 7,
          padding: "14px 16px",
        }}>
          <AnalysisText text={text} streaming={status === "streaming"} />
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.2); }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
