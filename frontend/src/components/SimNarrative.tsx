import { useCallback, useEffect, useRef, useState } from "react";
import type { SimResult } from "../types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Status = "idle" | "loading" | "streaming" | "done" | "error";

function isSectionHeader(line: string): boolean {
  const t = line.trim();
  return t.length > 3 && t === t.toUpperCase() && /^[A-Z\s&\-]+$/.test(t);
}

function NarrativeText({ text, streaming }: { text: string; streaming: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (streaming) bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [text, streaming]);

  return (
    <div style={{ fontSize: 13, lineHeight: 1.7, color: "#1A2744" }}>
      {text.split("\n").map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} style={{ height: 8 }} />;
        if (isSectionHeader(t)) return (
          <div key={i} style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "#E8700A", marginTop: i === 0 ? 0 : 14, marginBottom: 5, paddingBottom: 4, borderBottom: "1px solid #e8eef6", fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>
            {t}
          </div>
        );
        if (t.startsWith("•") || t.startsWith("-")) return (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5, fontFamily: "Georgia, serif" }}>
            <span style={{ color: "#E8700A", flexShrink: 0 }}>•</span>
            <span>{t.replace(/^[•\-]\s*/, "")}</span>
          </div>
        );
        const numMatch = t.match(/^(\d+)\.\s+(.+)/);
        if (numMatch) return (
          <div key={i} style={{ display: "flex", gap: 10, marginBottom: 6, fontFamily: "Georgia, serif" }}>
            <span style={{ background: "#1A2744", color: "#fff", borderRadius: "50%", width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, flexShrink: 0, marginTop: 2, fontFamily: "monospace" }}>{numMatch[1]}</span>
            <span>{numMatch[2]}</span>
          </div>
        );
        return <p key={i} style={{ margin: "0 0 6px", fontFamily: "Georgia, serif", color: "#2A3A58" }}>{t}</p>;
      })}
      {streaming && <span style={{ display: "inline-block", width: 2, height: "1em", background: "#E8700A", marginLeft: 1, animation: "blink 0.8s step-end infinite", verticalAlign: "text-bottom" }} />}
      <div ref={bottomRef} />
      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}`}</style>
    </div>
  );
}

export function SimNarrative({ fips, result }: { fips: string; result: SimResult }) {
  const [status, setStatus] = useState<Status>("idle");
  const [text, setText]     = useState("");
  const [err, setErr]       = useState("");
  const abortRef            = useRef<AbortController | null>(null);

  // Auto-reset when fips or result changes
  useEffect(() => {
    abortRef.current?.abort();
    setStatus("idle");
    setText("");
    setErr("");
  }, [fips, result]);

  const run = useCallback(async () => {
    if (status === "streaming" || status === "loading") {
      abortRef.current?.abort();
      setStatus("idle");
      return;
    }
    setText(""); setErr(""); setStatus("loading");
    abortRef.current = new AbortController();
    try {
      const resp = await fetch(`${BASE}/api/ai/narrative`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fips, simulation_result: result }),
        signal: abortRef.current.signal,
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
            const e = JSON.parse(raw) as { type: string; delta?: string; message?: string };
            if (e.type === "text" && e.delta) setText((p) => p + e.delta);
            else if (e.type === "error") { setErr(e.message ?? "Error"); setStatus("error"); return; }
          } catch { /* skip */ }
        }
      }
      setStatus("done");
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") { setStatus("idle"); return; }
      setErr(e instanceof Error ? e.message : "Failed");
      setStatus("error");
    }
  }, [fips, result, status]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: status === "streaming" ? "#E8700A" : status === "done" ? "#1E8A4C" : "#7A92AB", animation: status === "streaming" ? "pulse 1.2s ease-in-out infinite" : "none" }} />
          <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", color: "#7A92AB", fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>Claude Opus Narrative</span>
        </div>
        <button onClick={run} disabled={status === "loading"} style={{ background: status === "streaming" ? "#fff3e8" : "#1A2744", color: status === "streaming" ? "#D45F00" : "#fff", border: status === "streaming" ? "1px solid #D45F00" : "none", borderRadius: 5, padding: "5px 12px", fontSize: 11, fontWeight: 700, fontFamily: "'Trebuchet MS', Arial, sans-serif", cursor: status === "loading" ? "not-allowed" : "pointer", opacity: status === "loading" ? 0.55 : 1 }}>
          {status === "loading" ? "Thinking…" : status === "streaming" ? "Stop" : status === "done" ? "Re-run" : "Generate Narrative"}
        </button>
      </div>

      {status === "loading" && (
        <div style={{ display: "flex", gap: 5, alignItems: "center", padding: "8px 0" }}>
          {[0,1,2].map((i) => <div key={i} style={{ width: 7, height: 7, borderRadius: "50%", background: "#E8700A", animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }} />)}
          <span style={{ fontSize: 11, color: "#7A92AB", marginLeft: 6 }}>Interpreting trajectory…</span>
        </div>
      )}
      {status === "error" && <div style={{ background: "#fceaea", borderRadius: 6, padding: "10px 12px", fontSize: 12, color: "#C22828" }}>{err}</div>}
      {(status === "streaming" || status === "done") && text && (
        <div style={{ background: "#f9fafc", border: "1px solid #e0e8f4", borderRadius: 7, padding: "14px 16px" }}>
          <NarrativeText text={text} streaming={status === "streaming"} />
        </div>
      )}
      <style>{`@keyframes pulse{0%,100%{opacity:0.3;transform:scale(0.8)}50%{opacity:1;transform:scale(1.2)}}`}</style>
    </div>
  );
}
