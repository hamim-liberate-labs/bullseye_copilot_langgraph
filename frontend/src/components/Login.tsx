import { useState } from "react";
import type { FormEvent } from "react";
import { login } from "../lib/api";
import type { Auth } from "../lib/api";

const RINGS = [120, 220, 340, 480, 640, 820];

export default function Login({ onLogin }: { onLogin: (a: Auth) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full">
      {/* Brand panel — charcoal field, drifting bullseye rings */}
      <div className="relative hidden w-[44%] overflow-hidden bg-ink text-sage lg:block">
        <div className="animate-ring-drift absolute -top-40 -left-40 h-[900px] w-[900px] opacity-[0.16]">
          {RINGS.map((d) => (
            <span
              key={d}
              className="rings top-1/2 left-1/2"
              style={{
                width: d,
                height: d,
                transform: "translate(-50%, -50%)",
                borderStyle: d % 220 === 0 ? "dashed" : "solid",
              }}
            />
          ))}
        </div>

        <div className="relative z-10 flex h-full flex-col justify-between p-12">
          <div className="flex items-center gap-3">
            <img src="/bullseye-logo.svg" alt="" className="h-10 w-10" />
            <span className="font-mono text-xs tracking-[0.25em] text-sage/70 uppercase">
              Bullseye for Schools
            </span>
          </div>

          <div>
            <h1 className="font-display text-6xl leading-[1.04] font-light text-paper">
              Coaching,
              <br />
              <em className="font-medium text-leaf-bright not-italic italic">
                on target.
              </em>
            </h1>
            <p className="mt-6 max-w-sm text-[15px] leading-relaxed text-sage/80">
              Your copilot for walkthroughs, feedback, and growth — grounded in
              your school's own sessions, goals, and next steps.
            </p>
          </div>

          <p className="font-mono text-[11px] tracking-widest text-sage/40 uppercase">
            growth, not gotcha
          </p>
        </div>
      </div>

      {/* Form panel */}
      <div className="relative flex flex-1 items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="animate-rise mb-10 lg:hidden" style={{ animationDelay: "0ms" }}>
            <img src="/bullseye-logo.svg" alt="Bullseye" className="h-12 w-12" />
          </div>

          <h2
            className="font-display animate-rise text-4xl font-medium text-ink"
            style={{ animationDelay: "60ms" }}
          >
            Welcome back
          </h2>
          <p
            className="animate-rise mt-2 text-sm text-muted"
            style={{ animationDelay: "120ms" }}
          >
            Sign in with your Bullseye account to open the copilot.
          </p>

          <label
            className="animate-rise mt-9 block"
            style={{ animationDelay: "180ms" }}
          >
            <span className="font-mono text-[11px] tracking-[0.18em] text-muted uppercase">
              Email
            </span>
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-line bg-paper-raised px-3.5 py-2.5 text-[15px] text-ink transition outline-none focus:border-leaf focus:ring-4 focus:ring-leaf/10"
              placeholder="you@school.edu"
            />
          </label>

          <label
            className="animate-rise mt-5 block"
            style={{ animationDelay: "240ms" }}
          >
            <span className="font-mono text-[11px] tracking-[0.18em] text-muted uppercase">
              Password
            </span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-line bg-paper-raised px-3.5 py-2.5 text-[15px] text-ink transition outline-none focus:border-leaf focus:ring-4 focus:ring-leaf/10"
              placeholder="••••••••"
            />
          </label>

          {error && (
            <p className="animate-rise mt-4 rounded-lg border border-clay/30 bg-clay/8 px-3.5 py-2.5 text-sm text-clay">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="animate-rise mt-8 w-full rounded-lg bg-leaf py-3 text-[15px] font-bold text-white shadow-card transition hover:bg-leaf-deep active:scale-[0.99] disabled:opacity-60"
            style={{ animationDelay: "300ms" }}
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
