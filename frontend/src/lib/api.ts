export interface BullseyeUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  admin: boolean;
  schools: { id: number; display_name: string }[];
  current_school?: { id: number; display_name: string };
}

export interface Auth {
  token: string;
  user: BullseyeUser;
}

export interface Artifact {
  thread: string;
  url: string;
  updated_at?: string;
}

export interface ChatResult {
  reply: string;
  session_id: string;
  chat_id: string;
  active_artifact: Artifact | null;
  artifacts: Artifact[];
  cost_usd: number | null;
}

const t0 = () => performance.now();
const since = (start: number) => `${((performance.now() - start) / 1000).toFixed(1)}s`;

function clog(...args: unknown[]) {
  console.log(
    `%c[copilot]%c ${new Date().toLocaleTimeString()}`,
    "color:#0f9200;font-weight:bold",
    "color:#999",
    ...args,
  );
}

export async function login(email: string, password: string): Promise<Auth> {
  const start = t0();
  clog("login →", email);
  const r = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) {
    const detail = await r.json().then((d) => d.detail).catch(() => null);
    clog("login failed:", r.status, detail);
    throw new Error(detail || "Sign-in failed");
  }
  const data = await r.json();
  clog(`login ok in ${since(start)} ·`, data.user.full_name);
  return { token: data.token, user: data.user };
}

export interface StreamHandlers {
  onTool: (label: string, name: string) => void;
  onText: (delta: string) => void;
  onResult: (result: ChatResult) => void;
  onError: (detail: string) => void;
}

/** POST /api/chat/stream and dispatch SSE events. EventSource can't POST,
 * so we parse the event stream off fetch's ReadableStream ourselves. */
export async function streamChat(
  body: {
    token: string;
    message: string;
    session_id?: string | null;
    chat_id?: string | null;
    user: BullseyeUser;
    model: string;
    effort: string;
  },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const start = t0();
  let firstText = true;
  clog("turn →", JSON.stringify(body.message.slice(0, 60)), body.session_id ? `(resume ${body.session_id.slice(0, 8)})` : "(new session)");

  const r = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) {
    clog("turn failed:", r.status);
    handlers.onError(`request failed (${r.status})`);
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);

      let event = "";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!event || !data) continue;

      const payload = JSON.parse(data);
      if (event === "text") {
        if (firstText) {
          clog(`first text at ${since(start)}`);
          firstText = false;
        }
        handlers.onText(payload.delta);
      } else if (event === "tool") {
        clog(`tool at ${since(start)} ·`, payload.name);
        handlers.onTool(payload.label, payload.name);
      } else if (event === "result") {
        const res = payload as ChatResult;
        clog(
          `done in ${since(start)} ·`,
          `${res.reply.length} chars,`,
          `${res.artifacts.length} artifact(s),`,
          `active=${res.active_artifact?.thread ?? "none"}`,
        );
        handlers.onResult(res);
      } else if (event === "error") {
        clog(`error at ${since(start)} ·`, payload.detail);
        handlers.onError(payload.detail);
      }
    }
  }
}
