# 🌉 STUDENTUP.IN → Student Portal navigation bridge

**Goal:** students landing on the main website **studentup.in** (WordPress)
tap one icon and reach the Student Portal on the subdomain
**quiz.studentup.in** — Smart Advanced Quiz, Live Exams, exam-wise
Quiz/Mocks, Previous Papers and ALL portal features.

## How it is connected

| Surface | URL | What it serves |
|---|---|---|
| Main website (WordPress, separate repo) | `https://studentup.in` | Blog / brand site (WP = blog master) |
| Student Portal (this platform) | `https://quiz.studentup.in` (also `exam.` / `app.` / `portal.` subdomains, or `/portal` path) | Daily Quiz, Live Exams, Mocks, PYQ Papers, Reports |

Repo separation is unchanged (see `docs/BRIDGE_PLAN.md`): WordPress stays
blog-master, this platform stays quiz-master. The bridge is **links with
deep-link parameters**, not code merging.

## Deep links (portal understands `?go=`)

The portal reads `?go=` on entry, remembers it through registration/login,
and auto-scrolls to the exact section:

| Link | Lands on |
|---|---|
| `https://quiz.studentup.in/?go=quiz` | 🧠 Smart Advanced Quiz (Today's Daily Quiz, PYQ-first) |
| `https://quiz.studentup.in/?go=exams` | 🔴 Live & Upcoming Exams (+ Weekly Grand Test) |
| `https://quiz.studentup.in/?go=mocks` | 🎓 Exam-wise Mock Tests grid |
| `https://quiz.studentup.in/?go=papers` | 📜 Previous Papers (Real PYQ) |
| `https://quiz.studentup.in/` | 🌟 Portal home — all features |

Implementation: `init()` stores `go` → `localStorage.su_go`; `loadHome()`
calls `_applyGo()` which maps the value to a section id and scrolls with a
highlight flash (`scrollDoor`). Unknown values fall back to the quiz section.

## What to add on studentup.in (WordPress side)

Ready-to-paste snippet: **`integrations/wordpress/studentup-portal-icon.html`**

1. **Homepage block (recommended):** add a *Custom HTML* block under the
   hero and paste the snippet — renders the 🚀 main button + 5 icon tiles.
2. **Menu items:** Appearance → Menus → Custom Links (text variant is in a
   comment at the bottom of the snippet): 🧠 Smart Quiz, 🔴 Live Exams,
   🎓 Exam-wise Mocks, 🚀 Student Portal.
3. Optional: reuse the same snippet in the footer widget so every blog
   article ends with a path into the portal.

If the portal is ever served from a path instead of a subdomain
(`https://studentup.in/portal`), replace `https://quiz.studentup.in`
with that base in the snippet — the `?go=` deep links work the same.

## Already live in this platform (no WP change needed)

- Public pages (`/`, `/site`, …) nav now carries a **🚀 Student Portal**
  entry on every page.
- The public home shows the **🚀 StudentUp Portal — Anni Okka Chota**
  icon grid with the same deep links (Smart Advanced Quiz, Live Exams,
  Exam-wise Quiz & Mocks, Previous Papers, Exams Hub, All Features).
- `PORTAL_BASE_URL` env overrides the portal base used by public pages
  (default `/portal`).
