# Moving Bullseye Copilot to LangGraph — A Plain‑English Plan

This explains, in simple terms, how we'd rebuild the Bullseye Copilot on a new
foundation called **LangGraph**, without changing anything the user sees or how
the assistant behaves.

---

## What we're doing, and why

Right now the copilot runs on Anthropic's **Claude Agent SDK** — think of it as
the "engine" that lets the assistant think, call tools, write files, and reply.
It works well, but we want to move to **LangGraph**, a different engine that
gives us more control over how the assistant makes decisions (especially around
asking for confirmation before changing data) and isn't tied to one vendor's
runtime.

**The golden rule of this migration:** the user should not notice. Same look,
same answers, same speed, same safety. We're swapping the engine, not redesigning
the car.

---

## What the copilot does today (so we know what to preserve)

The assistant currently can:

- **Read Bullseye data** — sessions, scores, goals, people, the dashboard, and
  next steps — through a set of tools.
- **Change next steps** — create, edit, complete, or delete them (after asking
  the user first).
- **Do its own work in a private scratch space** — a per‑conversation folder
  where it can save data, run small calculations, and build things.
- **Build visual reports** — HTML "artifacts" that show up in a side panel.
- **Answer "how do I…" questions** — using a built‑in copy of the Bullseye help
  center.
- **Speak to three audiences** — coaches, teachers, and admins — adjusting tone.
- **Stream its reply live** — text appears as it's written, with little status
  labels like "Reading a session…".
- **Keep each user's data separate and secure.**

**Every one of these must still work after the move.** That list is our
checklist.

---

## The one big decision up front

LangGraph has an optional "batteries‑included" layer on top of it called
**Deep Agents**. It comes with ready‑made pieces for exactly the things this app
needs: a file/scratch‑space system, the "ask before doing something risky"
behaviour, the help‑center lookups, and memory.

So there are two ways to go:

1. **Plain LangGraph** (what was asked for) — we build those pieces ourselves.
   More work, but full control over every detail.
2. **Deep Agents on top of LangGraph** — several of the hardest parts come for
   free, so the project is meaningfully smaller.

**Recommendation:** decide this on day one. This plan follows **plain LangGraph**
as requested, but flags the spots where Deep Agents would save real time — worth
a serious look before we start hand‑building.

---

## How the new version is shaped

The web server in front (the part the frontend talks to) **stays the same**.
Behind it, we replace the old engine with LangGraph. At a high level, each user
message flows like this:

```
User sends a message
      ↓
We attach who they are (login, school, role) and point to their scratch folder
      ↓
The LangGraph "assistant" thinks and decides what to do
      ↓
It uses tools:  read Bullseye data · change a next step · run a calculation ·
                search the help center · write a report
      ↓
Before any change to real data, it pauses and asks the user to confirm
      ↓
The reply streams back to the screen, with any report shown in the side panel
```

The tools, the safety check, and the streaming are the three pieces we care
most about getting right.

---

## The plan, step by step

We'll work in phases so there's something working early, and the riskiest parts
get attention before the deadline.

### Phase 1 — Get a basic assistant talking
Stand up a minimal LangGraph assistant that can hold a conversation (no tools
yet). This proves the new engine works and connects to Claude.

### Phase 2 — Reconnect the Bullseye data tools
The good news: the existing tool layer (the part that actually talks to
Bullseye) can be **reused as‑is** — LangGraph has a standard way to plug into it.
So all the careful work already done on next steps, sessions, people, etc.
carries straight over. (Later, if we want, we can rewrite them in LangGraph's
own style, but there's no rush.)

### Phase 3 — Let the assistant use those tools
Hook the tools up to the assistant and confirm it picks the right one and reads
data correctly. At this point it can answer real questions about real data.

### Phase 4 — Rebuild the private scratch space
Recreate the per‑conversation folder and the ability to read/write files inside
it — and *only* inside it (no reaching outside its own space). We'll reuse the
existing safety tests to prove it stays locked in.
*(This is one of the parts Deep Agents would hand us for free.)*

### Phase 5 — Rebuild the "run a calculation" ability
Today the assistant can safely run small Python scripts to crunch numbers over
the data it pulled (e.g. "4 of 6 objectives improved"). The old engine gave us a
secure, offline, locked‑down place to do that automatically. We have to rebuild
that safe space ourselves. **This is the single hardest part of the project** —
flag it early and give it real time, because doing it badly is a security risk.

### Phase 6 — Make "ask before changing data" rock‑solid
Right now, "confirm before you create/edit/delete" is an instruction in the
prompt — the assistant is *told* to ask. In the new version we can make it a
hard rule the system *enforces*: before any change to real Bullseye data, the
assistant pauses, shows the user plainly what it's about to do, and only
continues once they say yes. This is a real safety upgrade.
*(Also something Deep Agents provides ready‑made.)*

### Phase 7 — Remember each conversation
Make conversations resume properly — full history, and the ability to pause for a
confirmation and pick up exactly where it left off. This needs to be in place
before Phase 6's "pause and ask" can work.

### Phase 8 — Keep every user separate and secure
Make sure each request carries that user's own login and school, and that two
people using the copilot at once can never see each other's data. This is
non‑negotiable and gets its own testing.

### Phase 9 — Match the live, streaming experience exactly
Reproduce the live‑typing replies, the status labels ("Reading a session…"), the
confirmation prompts, and the side‑panel reports — using the **same signals the
frontend already expects**, so the frontend needs no changes.

### Phase 10 — Switch over carefully
Run the old and new engines side by side, compare their answers on a fixed set
of test questions until we're confident they match, then flip the default to the
new one and remove the old code and update the docs.

---

## Suggested order of work

1. **Phases 1–3** first — a working assistant that can read real data. Quick win.
2. **Phases 7 then 6** — memory, then the enforced "ask before changing." This
   unlocks safe writing.
3. **Phases 4–5** — the scratch space and the secure calculation sandbox. The
   heaviest lifting.
4. **Phases 8–9** — security and the polished streaming experience.
5. **Phase 10** — compare, switch, clean up.

---

## The main risks to watch

| Risk | Why it matters | How we handle it |
|---|---|---|
| **The secure calculation sandbox** | The old engine gave it for free; rebuilding it safely is hard | Treat it as its own mini‑project (Phase 5); never cut corners on security |
| **Keeping users separate** | A leak between users would be serious | Carry each user's login per‑request; never share; test it explicitly |
| **Matching the streaming feel** | Frontend expects exact signals; drift breaks the UI | Reproduce the existing signals precisely and test against the real frontend |
| **The scratch space staying locked in** | The assistant must not reach outside its folder | Reuse the existing security tests on the new file tools |

---

## How we'll know it's done

The move is complete when, on the new engine:

- Reading data (sessions, goals, people, dashboard, next steps) works.
- Creating, editing, completing, and deleting next steps works — and each one
  asks for confirmation first.
- The private scratch space, file handling, and calculations all behave as
  before, and stay safely locked in.
- Help‑center answers work and link to the real help pages.
- Visual reports appear in the side panel just like today.
- Live‑typing replies, status labels, and confirmation prompts feel identical.
- Two users at once never see each other's data.
- Conversations resume with full history.
- The old engine is removed and the docs are updated.

---

## One‑line summary

We're swapping the assistant's engine from the Claude Agent SDK to LangGraph,
reusing the existing Bullseye tools, rebuilding the scratch space and secure
calculations ourselves, and upgrading "ask before changing data" from a polite
instruction into an enforced rule — all while keeping the experience exactly the
same for users. **(And if we're open to it, the Deep Agents add‑on would make
several of the hardest phases much shorter.)**
