import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamChat } from "../lib/api";
import type { Artifact, Auth } from "../lib/api";
import ArtifactPanel from "./ArtifactPanel";

interface Msg {
  role: "user" | "assistant";
  content: string;
  error?: boolean;
  artifactThread?: string; // set when this reply produced/updated an artifact
  cost?: number | null; // USD cost of the turn that produced this reply
}

interface Convo {
  messages: Msg[];
  sessionId: string | null;
  chatId: string | null;
  artifacts: Artifact[];
  activeThread: string | null;
}

const CONVO_KEY = "bullseye.convo";
const MODEL_KEY = "bullseye.model";
const EFFORT_KEY = "bullseye.effort";
const MODELS = [
  { id: "gpt", label: "GPT-5.4", desc: "OpenAI reasoning model", provider: "openai" },
  { id: "opus", label: "Opus 4.8", desc: "For complex tasks", provider: "anthropic" },
  { id: "sonnet", label: "Sonnet 4.6", desc: "For everyday tasks", provider: "anthropic" },
  { id: "haiku", label: "Haiku 4.5", desc: "Fastest, for simple tasks", provider: "anthropic" },
] as const;
const DEFAULT_MODEL_ID = import.meta.env.VITE_DEFAULT_MODEL || "gpt";
const DEFAULT_EFFORT_ID = import.meta.env.VITE_DEFAULT_EFFORT || "low";
const EFFORTS = [
  { id: "minimal", label: "Minimal" },
  { id: "low", label: "Low" },
  { id: "medium", label: "Medium" },
  { id: "high", label: "High" },
  { id: "xhigh", label: "X-High" },
  { id: "max", label: "Max" },
] as const;

// Effort levels each provider actually supports / that are distinct for it.
//  - openai (gpt-5.4): none/low/medium/high/xhigh (Minimal→none); "Max" is
//    redundant with X-High, so it's omitted.
//  - anthropic (Claude): thinking budgets — Minimal≡Low (no thinking), so Minimal
//    is omitted; Max (32k budget) is the top.
const EFFORTS_BY_PROVIDER: Record<string, string[]> = {
  openai: ["minimal", "low", "medium", "high", "xhigh"],
  anthropic: ["low", "medium", "high", "xhigh", "max"],
};
const providerOf = (modelId: string) =>
  MODELS.find((m) => m.id === modelId)?.provider ?? "anthropic";
const effortsFor = (modelId: string) => {
  const allowed = EFFORTS_BY_PROVIDER[providerOf(modelId)] ?? EFFORTS.map((e) => e.id);
  return EFFORTS.filter((e) => allowed.includes(e.id));
};

const EMPTY_CONVO: Convo = {
  messages: [],
  sessionId: null,
  chatId: null,
  artifacts: [],
  activeThread: null,
};

function loadConvo(): Convo {
  try {
    const raw = sessionStorage.getItem(CONVO_KEY);
    return raw ? { ...EMPTY_CONVO, ...JSON.parse(raw) } : EMPTY_CONVO;
  } catch {
    return EMPTY_CONVO;
  }
}

const OBSERVER_STARTERS = [
  "Brief me before my next walkthrough",
  "What should I focus on today?",
  "Which next steps are overdue?",
  "Show recent sessions across my staff",
];

const ADMIN_STARTERS = [
  "Build me an Insights Dashboard showing coaching progress over all of the sessions",
  "Summarize coaching activity this month",
  "Who hasn't had feedback recently?",
  "How do I set an individual goal?",
];

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function formatCost(usd: number): string {
  if (usd <= 0) return "$0.00";
  // Sub-cent turns keep more precision so they don't all read as "$0.00".
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

/** Selected-item checkmark for the model/effort menu. */
function Check({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 14 14"
      className={`h-3.5 w-3.5 flex-shrink-0 ${className}`}
      fill="none"
    >
      <path
        d="M2.5 7.5l3 3 6-7"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-bullseye">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function AssistantCard({
  children,
  delay = 0,
}: {
  children: React.ReactNode;
  delay?: number;
}) {
  return (
    <div
      className="animate-rise flex gap-3.5"
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="relative mt-1.5 flex h-5 w-5 flex-shrink-0 items-center justify-center">
        <span className="absolute h-5 w-5 rounded-full border-[1.5px] border-leaf/35" />
        <span className="absolute h-3 w-3 rounded-full border-[1.5px] border-leaf/60" />
        <span className="absolute h-1.5 w-1.5 rounded-full bg-leaf" />
      </span>
      <div className="min-w-0 flex-1 rounded-xl rounded-tl-sm border border-line bg-paper-raised px-5 py-4 shadow-card">
        {children}
      </div>
    </div>
  );
}

export default function Chat({
  auth,
  onLogout,
  onSchoolChange,
}: {
  auth: Auth;
  onLogout: () => void;
  onSchoolChange: (school: { id: number; display_name: string }) => void;
}) {
  const [convo, setConvo] = useState<Convo>(loadConvo);
  const [model, setModel] = useState<string>(
    () => localStorage.getItem(MODEL_KEY) || DEFAULT_MODEL_ID,
  );
  const [effort, setEffort] = useState<string>(
    () => localStorage.getItem(EFFORT_KEY) || DEFAULT_EFFORT_ID,
  );
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [bust, setBust] = useState(() => Date.now());
  const [artifactsOpen, setArtifactsOpen] = useState(true);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [submenu, setSubmenu] = useState<"effort" | "models" | null>(null);
  const [panelWidth, setPanelWidth] = useState<number>(() => {
    const saved = Number(localStorage.getItem("bullseye.panelWidth"));
    return saved >= 25 && saved <= 75 ? saved : 46;
  });
  const [resizing, setResizing] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  function startResize(e: React.PointerEvent) {
    e.preventDefault();
    setResizing(true);
    const onMove = (ev: PointerEvent) => {
      const pct = ((window.innerWidth - ev.clientX) / window.innerWidth) * 100;
      setPanelWidth(Math.min(75, Math.max(25, pct)));
    };
    const onUp = () => {
      setResizing(false);
      setPanelWidth((w) => {
        localStorage.setItem("bullseye.panelWidth", String(Math.round(w)));
        return w;
      });
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  const schools = auth.user.schools ?? [];
  const school = auth.user.current_school ?? schools[0];
  const firstName = auth.user.first_name || auth.user.full_name;
  const starters = auth.user.admin ? ADMIN_STARTERS : OBSERVER_STARTERS;

  useEffect(() => {
    sessionStorage.setItem(CONVO_KEY, JSON.stringify(convo));
  }, [convo]);

  useEffect(() => {
    localStorage.setItem(MODEL_KEY, model);
  }, [model]);

  useEffect(() => {
    localStorage.setItem(EFFORT_KEY, effort);
  }, [effort]);

  // Effort options the selected model's provider actually supports.
  const visibleEfforts = effortsFor(model);

  // Keep the chosen effort valid for the current provider (covers initial load
  // from localStorage and switching to a model whose provider lacks it).
  useEffect(() => {
    const allowed = visibleEfforts.map((e) => e.id);
    if (!allowed.includes(effort)) {
      setEffort(allowed.includes(DEFAULT_EFFORT_ID) ? DEFAULT_EFFORT_ID : allowed[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [convo.messages, draft, status]);

  function newConversation() {
    abortRef.current?.abort();
    setConvo(EMPTY_CONVO);
    setDraft("");
    setStatus(null);
    setStreaming(false);
  }

  function openArtifact(thread: string) {
    setConvo((c) => ({ ...c, activeThread: thread }));
    setArtifactsOpen(true);
  }

  function closeModelMenu() {
    setModelMenuOpen(false);
    setSubmenu(null);
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || streaming) return;

    setInput("");
    setStreaming(true);
    setDraft("");
    setStatus("Thinking…");
    setConvo((c) => ({
      ...c,
      messages: [...c.messages, { role: "user", content: message }],
    }));

    const controller = new AbortController();
    abortRef.current = controller;
    let acc = "";

    try {
      await streamChat(
        {
          token: auth.token,
          message,
          session_id: convo.sessionId,
          chat_id: convo.chatId,
          user: auth.user,
          model,
          effort,
        },
        {
          onTool: (label) => {
            setStatus(label);
            // Interstitial narration ("let me pull these…") always precedes a
            // tool call. Discard the draft the moment a tool fires, so only the
            // final answer — the text that streams after the last tool — survives
            // to be shown. The status label takes over until that text arrives.
            acc = "";
            setDraft("");
          },
          onText: (delta) => {
            acc += delta;
            setDraft(acc);
            setStatus(null);
          },
          onResult: (result) => {
            setConvo((c) => ({
              messages: [
                ...c.messages,
                {
                  role: "assistant",
                  content: result.reply,
                  artifactThread: result.active_artifact?.thread,
                  cost: result.cost_usd,
                },
              ],
              sessionId: result.session_id,
              chatId: result.chat_id,
              artifacts: result.artifacts,
              activeThread:
                result.active_artifact?.thread ?? c.activeThread,
            }));
            if (result.active_artifact) {
              setBust(Date.now());
              setArtifactsOpen(true); // a freshly produced artifact reopens the panel
            }
            setDraft("");
          },
          onError: (detail) => {
            setConvo((c) => ({
              ...c,
              messages: [
                ...c.messages,
                {
                  role: "assistant",
                  content: `Something went wrong: ${detail}`,
                  error: true,
                },
              ],
            }));
            setDraft("");
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setConvo((c) => ({
          ...c,
          messages: [
            ...c.messages,
            {
              role: "assistant",
              content: "The connection dropped — please try again.",
              error: true,
            },
          ],
        }));
      }
      setDraft("");
    } finally {
      setStreaming(false);
      setStatus(null);
      abortRef.current = null;
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  const showArtifacts = convo.artifacts.length > 0;

  return (
    <div className="flex h-full flex-col">
      {/* Charcoal chrome */}
      <header className="flex items-center justify-between bg-ink px-5 py-2.5 text-paper">
        <div className="flex items-center gap-3">
          <img src="/bullseye-logo.svg" alt="" className="h-7 w-7" />
          <span className="font-display text-lg font-medium tracking-tight">
            Bullseye <em className="text-leaf-bright">Copilot</em>
          </span>
        </div>

        {schools.length > 1 ? (
          <div className="relative hidden md:flex">
            <span className="pointer-events-none absolute top-1/2 left-3 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-leaf-bright" />
            <select
              value={String(school?.id ?? "")}
              onChange={(e) => {
                const next = schools.find((s) => String(s.id) === e.target.value);
                if (next && next.id !== school?.id) {
                  onSchoolChange(next);
                  newConversation(); // school changes the data context — start fresh
                }
              }}
              title="Active school"
              className="cursor-pointer appearance-none rounded-full border border-ink-line bg-ink-soft py-1.5 pr-9 pl-7 text-[13px] font-medium text-sage transition hover:border-leaf-bright focus:border-leaf-bright focus:outline-none"
            >
              {schools.map((s) => (
                <option key={s.id} value={String(s.id)} className="bg-ink text-paper">
                  {s.display_name}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-[10px] text-sage/60">
              ▾
            </span>
          </div>
        ) : (
          school && (
            <div className="hidden items-center gap-2 rounded-full border border-ink-line bg-ink-soft px-4 py-1.5 md:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-leaf-bright" />
              <span className="text-[13px] font-medium text-sage">
                {school.display_name}
              </span>
            </div>
          )
        )}

        <div className="flex items-center gap-2">
          {showArtifacts && (
            <button
              onClick={() => setArtifactsOpen((o) => !o)}
              aria-pressed={artifactsOpen}
              title={artifactsOpen ? "Hide artifact panel" : "Show artifact panel"}
              className={`rounded-full border px-3.5 py-1.5 text-[13px] font-semibold transition ${
                artifactsOpen
                  ? "border-leaf-bright/60 text-leaf-bright"
                  : "border-ink-line text-sage hover:border-leaf-bright hover:text-leaf-bright"
              }`}
            >
              {artifactsOpen ? "Hide panel" : "Show panel"}
            </button>
          )}
          <button
            onClick={newConversation}
            className="rounded-full border border-ink-line px-3.5 py-1.5 text-[13px] font-semibold text-sage transition hover:border-leaf-bright hover:text-leaf-bright"
          >
            + New conversation
          </button>
          <span className="hidden px-2 text-[13px] text-sage/70 sm:block">
            {auth.user.full_name}
          </span>
          <button
            onClick={onLogout}
            className="rounded-full px-3 py-1.5 text-[13px] text-sage/60 transition hover:text-paper"
            title="Sign out"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Chat column */}
        <main className="relative flex min-w-0 flex-1 flex-col">
          <div
            ref={scrollRef}
            className="scroll-quiet min-h-0 flex-1 overflow-y-auto"
          >
            <div className="mx-auto w-full max-w-3xl px-6 pt-8 pb-44">
              {convo.messages.length === 0 && !streaming ? (
                /* Empty state */
                <div className="pt-[9vh]">
                  <p
                    className="animate-rise font-mono text-[11px] tracking-[0.22em] text-leaf-deep uppercase"
                    style={{ animationDelay: "40ms" }}
                  >
                    {new Date().toLocaleDateString(undefined, {
                      weekday: "long",
                      month: "long",
                      day: "numeric",
                    })}
                  </p>
                  <h1
                    className="font-display animate-rise mt-3 text-5xl leading-[1.08] font-light text-ink"
                    style={{ animationDelay: "110ms" }}
                  >
                    {greeting()}, <span className="font-medium">{firstName}</span>.
                  </h1>
                  <p
                    className="animate-rise mt-4 max-w-lg text-[15px] leading-relaxed text-muted"
                    style={{ animationDelay: "180ms" }}
                  >
                    Ask about your sessions, feedback, goals, and next steps —
                    answers come straight from your Bullseye data.
                  </p>

                  <div className="mt-10 grid gap-2.5 sm:grid-cols-2">
                    {starters.map((s, i) => (
                      <button
                        key={s}
                        onClick={() => void send(s)}
                        className="animate-rise group flex items-center gap-3 rounded-xl border border-line bg-paper-raised px-4 py-3.5 text-left text-sm font-medium text-ink shadow-card transition hover:-translate-y-0.5 hover:border-leaf/50 hover:shadow-lift"
                        style={{ animationDelay: `${250 + i * 70}ms` }}
                      >
                        <span className="relative flex h-4 w-4 flex-shrink-0 items-center justify-center">
                          <span className="absolute h-4 w-4 rounded-full border border-sage transition group-hover:border-leaf/50" />
                          <span className="absolute h-1.5 w-1.5 rounded-full bg-sage transition group-hover:bg-leaf" />
                        </span>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                /* Transcript */
                <div className="space-y-7">
                  {convo.messages.map((m, i) =>
                    m.role === "user" ? (
                      <div key={i} className="animate-rise flex justify-end">
                        <div className="max-w-[78%] rounded-2xl rounded-br-sm bg-ink px-4.5 py-3 text-[15px] leading-relaxed text-paper shadow-card">
                          {m.content}
                        </div>
                      </div>
                    ) : (
                      <AssistantCard key={i}>
                        {m.error ? (
                          <p className="text-sm text-clay">{m.content}</p>
                        ) : (
                          <Markdown text={m.content} />
                        )}
                        {m.artifactThread &&
                          convo.artifacts.some(
                            (a) => a.thread === m.artifactThread,
                          ) && (
                            <button
                              onClick={() => openArtifact(m.artifactThread!)}
                              className="mt-3 inline-flex items-center gap-2 rounded-lg border border-line bg-paper px-3 py-1.5 text-[13px] font-medium text-ink transition hover:border-leaf/50 hover:bg-leaf-wash"
                            >
                              <span className="relative flex h-3.5 w-3.5 items-center justify-center">
                                <span className="absolute h-3.5 w-3.5 rounded-full border border-leaf/50" />
                                <span className="h-1.5 w-1.5 rounded-full bg-leaf" />
                              </span>
                              View artifact ·{" "}
                              <span className="text-muted">
                                {m.artifactThread.replace(/[-_]/g, " ")}
                              </span>
                            </button>
                          )}
                        {m.cost != null && (
                          <div
                            title="Estimated cost of this response"
                            className="mt-2.5 font-mono text-[10.5px] tracking-wide text-muted/70"
                          >
                            {formatCost(m.cost)}
                          </div>
                        )}
                      </AssistantCard>
                    ),
                  )}

                  {/* Live streaming card */}
                  {streaming && (
                    <AssistantCard>
                      {draft && <Markdown text={draft} />}
                      {draft && !status ? (
                        <span className="animate-blink ml-0.5 inline-block h-4 w-2 translate-y-0.5 bg-leaf" />
                      ) : (
                        /* A tool firing after some text was already streamed still
                           shows up here, below the partial reply — not just before
                           the first token. */
                        <div
                          className={`flex items-center gap-3 py-0.5 ${draft ? "mt-3" : ""}`}
                        >
                          <span className="relative flex h-3.5 w-3.5 items-center justify-center">
                            <span className="animate-radar absolute h-3.5 w-3.5 rounded-full border-2 border-leaf" />
                            <span className="h-1.5 w-1.5 rounded-full bg-leaf" />
                          </span>
                          <span className="font-mono text-[12.5px] text-muted">
                            {status ?? "Working…"}
                          </span>
                        </div>
                      )}
                    </AssistantCard>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Composer */}
          <div className="absolute right-0 bottom-0 left-0 bg-gradient-to-t from-paper via-paper/95 to-transparent pt-10 pb-6">
            <form onSubmit={submit} className="mx-auto w-full max-w-3xl px-6">
              <div className="rounded-2xl border border-line bg-paper-raised p-2 shadow-lift transition focus-within:border-leaf/60">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send(input);
                    }
                  }}
                  rows={1}
                  placeholder={
                    streaming
                      ? "Copilot is working…"
                      : "Ask about sessions, goals, next steps…"
                  }
                  disabled={streaming}
                  className="max-h-40 min-h-[44px] w-full resize-none bg-transparent px-3 py-2.5 text-[15px] text-ink outline-none placeholder:text-muted/70 disabled:opacity-60"
                />
                <div className="flex items-center justify-between gap-2 px-1 pt-1">
                  {/* Model selector — opens upward from the chatbox */}
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => {
                        setModelMenuOpen((o) => !o);
                        setSubmenu(null);
                      }}
                      aria-haspopup="menu"
                      aria-expanded={modelMenuOpen}
                      title="Model & reasoning effort for the next message"
                      className="flex items-center gap-2 rounded-lg bg-paper-sunken px-3 py-1.5 text-[13px] font-medium text-ink transition hover:bg-sage/25"
                    >
                      <span>
                        {MODELS.find((m) => m.id === model)?.label ?? model}
                      </span>
                      <span className="font-normal text-muted">
                        {EFFORTS.find((e) => e.id === effort)?.label ?? effort}
                      </span>
                      <span className="text-[10px] text-muted">⌄</span>
                    </button>
                    {modelMenuOpen && (
                      <>
                        <div
                          className="fixed inset-0 z-30"
                          onClick={closeModelMenu}
                        />
                        {/* Main panel */}
                        <div
                          role="menu"
                          className="animate-rise absolute bottom-full left-0 z-40 mb-2 w-60 rounded-2xl border border-line bg-paper-raised p-1.5 shadow-lift"
                        >
                          {/* Current model */}
                          <div className="flex items-start gap-2.5 px-2.5 py-2">
                            <span className="min-w-0 flex-1">
                              <span className="block text-[14px] font-medium text-ink">
                                {MODELS.find((m) => m.id === model)?.label ?? model}
                              </span>
                              <span className="block text-[12px] leading-snug text-muted">
                                {MODELS.find((m) => m.id === model)?.desc}
                              </span>
                            </span>
                            <Check className="mt-1 text-leaf" />
                          </div>

                          <div className="mx-2.5 my-1 h-px bg-line" />

                          {/* Effort row → flyout */}
                          <button
                            type="button"
                            onClick={() =>
                              setSubmenu((s) => (s === "effort" ? null : "effort"))
                            }
                            aria-haspopup="menu"
                            aria-expanded={submenu === "effort"}
                            className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[14px] transition ${
                              submenu === "effort"
                                ? "bg-leaf-wash"
                                : "hover:bg-leaf-wash/50"
                            }`}
                          >
                            <span className="flex-1 text-ink">Effort</span>
                            <span className="text-[13px] text-muted">
                              {EFFORTS.find((e) => e.id === effort)?.label ?? effort}
                            </span>
                            <span className="text-muted">›</span>
                          </button>

                          <div className="mx-2.5 my-1 h-px bg-line" />

                          {/* More models row → flyout */}
                          <button
                            type="button"
                            onClick={() =>
                              setSubmenu((s) => (s === "models" ? null : "models"))
                            }
                            aria-haspopup="menu"
                            aria-expanded={submenu === "models"}
                            className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[14px] transition ${
                              submenu === "models"
                                ? "bg-leaf-wash"
                                : "hover:bg-leaf-wash/50"
                            }`}
                          >
                            <span className="flex-1 text-ink">More models</span>
                            <span className="text-muted">›</span>
                          </button>

                          {/* Effort submenu */}
                          {submenu === "effort" && (
                            <div className="animate-rise absolute bottom-0 left-full z-40 ml-2 w-64 rounded-2xl border border-line bg-paper-raised p-1.5 shadow-lift">
                              <p className="px-2.5 py-2 text-[12px] leading-snug text-muted">
                                Higher effort means more thorough responses, but
                                takes longer and costs more.
                              </p>
                              {visibleEfforts.map((e) => {
                                const active = effort === e.id;
                                return (
                                  <button
                                    key={e.id}
                                    type="button"
                                    role="menuitemradio"
                                    aria-checked={active}
                                    onClick={() => {
                                      setEffort(e.id);
                                      closeModelMenu();
                                    }}
                                    className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[14px] transition ${
                                      active
                                        ? "bg-leaf-wash"
                                        : "hover:bg-leaf-wash/50"
                                    }`}
                                  >
                                    <span
                                      className={`flex-1 ${
                                        active
                                          ? "font-semibold text-leaf-deep"
                                          : "text-ink"
                                      }`}
                                    >
                                      {e.label}
                                    </span>
                                    {e.id === DEFAULT_EFFORT_ID && (
                                      <span className="rounded bg-sage/30 px-1.5 py-0.5 text-[10px] font-medium text-muted">
                                        Default
                                      </span>
                                    )}
                                    {active && <Check className="text-leaf" />}
                                  </button>
                                );
                              })}
                            </div>
                          )}

                          {/* More models submenu */}
                          {submenu === "models" && (
                            <div className="animate-rise absolute bottom-0 left-full z-40 ml-2 w-64 rounded-2xl border border-line bg-paper-raised p-1.5 shadow-lift">
                              {MODELS.map((m) => {
                                const active = model === m.id;
                                return (
                                  <button
                                    key={m.id}
                                    type="button"
                                    role="menuitemradio"
                                    aria-checked={active}
                                    onClick={() => {
                                      setModel(m.id);
                                      closeModelMenu();
                                    }}
                                    className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition ${
                                      active
                                        ? "bg-leaf-wash"
                                        : "hover:bg-leaf-wash/50"
                                    }`}
                                  >
                                    <span className="min-w-0 flex-1">
                                      <span
                                        className={`block text-[14px] ${
                                          active
                                            ? "font-semibold text-leaf-deep"
                                            : "text-ink"
                                        }`}
                                      >
                                        {m.label}
                                      </span>
                                      <span className="block text-[12px] leading-snug text-muted">
                                        {m.desc}
                                      </span>
                                    </span>
                                    {active && (
                                      <Check className="mt-1 text-leaf" />
                                    )}
                                  </button>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                  {streaming ? (
                    <button
                      type="button"
                      onClick={() => abortRef.current?.abort()}
                      title="Stop"
                      className="relative flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-ink text-paper transition hover:bg-ink-soft"
                    >
                      <span className="animate-radar absolute h-7 w-7 rounded-full border border-leaf-bright" />
                      <span className="h-3 w-3 rounded-[3px] bg-paper" />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={!input.trim()}
                      title="Send"
                      className="group flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-leaf text-white shadow-card transition hover:bg-leaf-deep active:scale-95 disabled:opacity-40"
                    >
                      {/* bullseye send mark */}
                      <span className="relative flex h-5 w-5 items-center justify-center">
                        <span className="absolute h-5 w-5 rounded-full border-[1.5px] border-white/50 transition group-hover:scale-110" />
                        <span className="absolute h-2 w-2 rounded-full bg-white" />
                      </span>
                    </button>
                  )}
                </div>
              </div>
              <p className="mt-2 text-center font-mono text-[10.5px] tracking-wide text-muted/70">
                Grounded in your Bullseye data · read-only
              </p>
            </form>
          </div>
        </main>

        {showArtifacts && artifactsOpen && (
          <ArtifactPanel
            artifacts={convo.artifacts}
            activeThread={convo.activeThread}
            bust={bust}
            width={panelWidth}
            resizing={resizing}
            onResizeStart={startResize}
            onClose={() => setArtifactsOpen(false)}
            onSelect={(thread) =>
              setConvo((c) => ({ ...c, activeThread: thread }))
            }
          />
        )}
      </div>
    </div>
  );
}
