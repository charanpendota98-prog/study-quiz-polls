# 🌉 Bridge Plan — studentup.in (WordPress) ↔ StudentUp Platform

**Decision (smart rule): okko side ekkada strongo akkade master.**
Repos rendu alaage untayi — okka repo ga merge cheyyamu (WordPress PHP
theme ni Python app loki teste rendu break avthayi). Bridge tho sync.

| Content | Master | Sync direction | How |
|---|---|---|---|
| 📰 Blog posts | WordPress (editor + SEO + AdSense akkade strong) | WP → Platform | WP REST API (`/wp-json/wp/v2/posts`) → mana `/blog` page + 10-min cache. Drafts publish ayye varaku ravu — private safe. |
| 🎓 Quiz questions | Platform bank (validation, PYQ engine, Telugu, 1450+ Qs) | Platform → WP | Dashboard 📤 Export → WP quiz.php format JSON → `integrations/wordpress/studentup-quiz-sync.php` REST route → theme prefers synced bank. |
| 📢 Exam notices | Platform dashboard | Platform only | Portal + `/updates` (WP ki avasaram ledu). |
| 🏆 Winners/Toppers | Platform | Platform only | `/winners`, `/toppers` pages. |

## Already built (this repo)
- `GET /api/blog/posts` + public `/blog` page — WP published posts ikkada
  kanipisthayi (link studentup.in ke velthundi — SEO akkade untundi).
- `GET /api/wp/status` (connection test), `GET /api/wp/export` (today's
  daily quiz in WP `quiz.php` format: `q, a[4], c, why, cat, src, exam`).
- Dashboard → Exam tab → **🌉 WordPress Bridge** card.
- Env: `WP_SITE_URL` (default `https://studentup.in`).
- WP-side snippet: `integrations/wordpress/studentup-quiz-sync.php`
  (private REST route, `edit_posts` permission, sanitized, 50-Q cap).

## One-time WP setup (5 minutes, WP repo/admin side)
1. Copy `studentup-quiz-sync.php` into `wordpress-theme/studentup/inc/`.
2. `functions.php` lo okka line: `require_once get_template_directory() . '/inc/studentup-quiz-sync.php';`
3. Daily quiz synced bank use cheyyalante `inc/quiz.php` →
   `studentup_quiz_bank()` modalone:
   `$synced = studentup_synced_quiz_items(); if ($synced) { return $synced; }`
4. (Optional automation) WP Application Password create chesi, server
   cron nunchi daily export push cheyyandi (snippet header lo curl undi).

## Rollout phases
- **Phase 1 (done):** /blog syndication + quiz export + status test + docs.
- **Phase 2:** WP snippet deploy + quiz.php one-line hook → WP daily quiz
  = platform daily quiz (same paper everywhere: WP, portal, bots).
- **Phase 3 (310X — shipped, approve-to-live):** Daily draft
  auto-builds (`core/publish_queue.py`: daily quiz + today's live
  exams + Sunday Weekly Grand + WP payload) and **nothing goes live
  until the owner approves** — dashboard 🚦 Publish Center
  (Approve → Push to WordPress → Go Live, full audit history).
  WP push (`core/wp_push.py`) posts to `studentup/v1/quiz` with a
  revocable **Application Password from env/.env only**
  (`WP_USERNAME`/`WP_APP_PASSWORD` — never via chat/API). Remaining
  optional: unattended cron push for pre-approved days, blog-publish
  → Telegram/WhatsApp announcement hook, PYQ Import Center publish.

## Merge cheyyakudadhu (intentional)
- Git repos merge/subtree — PHP theme + Python app vere stacks; deploy
  cycles vere. Bridge = rendu safe ga independent ga grow avthayi.
- WordPress DB/users ikkadiki move cheyyamu — blog audience akkade.
- Question authoring rendu chotla cheyyakudadhu — okka brain (platform
  bank) nunchi anni faces (WP/Telegram/WhatsApp/Portal) tintayi.
