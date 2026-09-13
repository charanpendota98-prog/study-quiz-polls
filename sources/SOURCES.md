# StudentUp — Complete Source Registry (v4.2, generated 2026-09-06)

Source of truth: `data/collector_sources.json` (regenerate with `python3 scripts/rebuild_registry.py`, then `python3 scripts/gen_sources_md.py`).

**Totals:** 303 sources — 84 live (verified, scraped daily), 128 candidates (auditor auto-enables once quiz content is confirmed), 91 archive/dead (never used).

Legend: 🟢 live · 🟡 candidate · `index` = deep crawl listing→articles, `rss` = feed · `te` = Telugu-native (no translation) · `pdf` = previous-paper PDFs auto-harvested. A source tagged for several exams appears under each.

## TSPSC (Telangana Groups / other TG exams)

### 🟢 Live (13)

| Source | Type | URL | Notes |
|---|---|---|---|
| GKToday Telangana GK | `index`  | https://www.gktoday.in/quizbase/telangana-gk-questions-for-telangana-state-public-service-commission | verified 06 Sep 2026 — TSPSC state GK — 2 pages, statement-type Qs |
| GKToday Telugu CA | `index`  | https://www.gktoday.in/quizbase/telugu-current-affairs | verified 06 Sep 2026 — NATIVE TELUGU current-affairs MCQs — no translation needed |
| Sakshi Telugu Daily CA MCQs | `index` `te` | https://education.sakshi.com/current-affairs/practice-test | verified 07 Sep 2026 — 25 Telugu CA MCQs per day, listing paginated ?page=N (3 months deep) |
| Sakshi TSPSC Groups Bitbank | `index` `te` | https://education.sakshi.com/groups/tspsc-bitbank | verified 07 Sep 2026 — Telugu bit bank hub: physics/chemistry/biology/S&T/TS history/TS geography/TS economy/polity, 25 Q per post ('1. ప్రశ్న? 1) .. 4) / సమాధా |
| FreshersNow Telangana GK Quiz | `index`  | https://www.freshersnow.com/telangana-gk-quiz/ | verified 07 Sep 2026 — 25 TS GK MCQs with answers+explanations (English) |
| FreshersNow GK Topic Quizzes | `index`  | https://www.freshersnow.com/gk-questions-answers/ | verified 07 Sep 2026 — Indian history/polity/economy/geography/science + state-wise GK quizzes |
| GKSeries Indian Polity Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — chapter-wise polity MCQs (FRs, DPSP, judiciary…) with explanations |
| GKSeries Indian History Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — IVC → national movement, chapter-wise with answers |
| GKSeries Geography Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — geomorphology/climatology/oceanography chapter MCQs |
| GKSeries Indian Economy Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — planning, banking system, fiscal system chapter MCQs |
| MCQBits TSPSC Previous Papers | `index`  | https://www.mcqbits.com/category/tspsc-mock-test/ | verified 07 Sep 2026 — Group-1/2/4, TSHC PYQs with answers (EN + TE posts) |
| MCQBits Previous Year Papers | `index`  | https://www.mcqbits.com/category/previous-year-question-papers/ | verified 07 Sep 2026 — TS/AP/central previous papers, paginated posts |
| Eenadu Pratibha PYQ PDFs (Groups) | `index` `pdf` | https://pratibha.eenadu.net/previouspapers/paperslist/jobs/2-1001-41 | verified 07 Sep 2026 — TGPSC/APPSC Group papers with key, PDF per paper (pratibhaassets ... .pdf) |

### 🟡 Candidates (14)

| Source | Type | URL | Notes |
|---|---|---|---|
| Eenadu Pratibha PYQ PDFs (DSC/TET) | `index`  | https://pratibha.eenadu.net/previouspapers/paperslist/jobs/2-1001-41-609 | TS DSC/TET papers with key (pedagogy heavy; content gate) |
| LSR Updates Telangana GK (Telugu) | `index` `te` | https://lsrupdates.com/category/telangana-history/ | Telugu 'Question No.N' + 'ఎ) బి) సి) డి)' + 'Answer : సి)' posts (fetch blocked from sandbox) |
| SRM Tutors GK Bits Telugu | `index` `te` | https://srmtutors.in/50-latest-gk-questions-in-telugu/ | '1000 GK bits in Telugu' PART-01..20 (Q + జవాబు one-liners; MCQ gate may reject) |
| QuizDunia Telugu GK 100-bit sets | `index` `te` | https://www.quizdunia.com/ | Blogger site: 10 x 100-bit + 10 x 50-bit Telugu MCQ sets, monthly Telugu CA MCQs (A./B./C./D. labels; answers may be JS-only) |
| Eenadu Pratibha Telugu Quiz — Reasoning | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDEw | Telugu-native 10-Q quizzes (89 sets); key served by AJAX — enable once answer endpoint mapped |
| Eenadu Pratibha Telugu Quiz — Polity | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDA4 | Telugu పాలిటీ quizzes — AJAX key (content gate) |
| Eenadu Pratibha Telugu Quiz — History | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDAx | Telugu చరిత్ర quizzes — AJAX key (content gate) |
| Eenadu Pratibha Telugu Quiz — Arithmetic | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDEx | Telugu అరిథ్‌మెటిక్‌ quizzes — AJAX key (content gate) |
| Sakshi TSPSC Previous Papers | `index`  | https://education.sakshi.com/tspsc-previous-papers | TSPSC previous papers listing (PDF/HTML mix; content gate) |
| Sakshi Bit Bank (English) | `index`  | https://education.sakshi.com/bitbank | legacy bit bank section — may redirect |
| Vyoma Telugu MCQs | `index`  | https://vyoma.net/mcqs/ | 2 lakh Telugu MCQs (APPSC/TSPSC exam-wise) — fetch blocked from crawler on 07 Sep |
| MCQAnswers TS/AP PYQs | `index`  | https://mcqanswers.com/appsc-tspsc-previous-year-papers/ | 3,500 APPSC/TSPSC PYQ MCQs in Telugu — fetch failed on 07 Sep |
| Adda247 Telugu Quiz | `index`  | https://www.adda247.com/te/category/quiz/ | Adda Telugu — quiz category 404 on 07 Sep 2026; re-check |
| Examveda State GK | `index`  | https://www.examveda.com/mcq-question-on-state-gk/ | state-wise GK — TS/AP pages content-gated |

## APPSC (AP Groups / other AP exams)

### 🟢 Live (13)

| Source | Type | URL | Notes |
|---|---|---|---|
| GKToday Andhra Pradesh GK | `index`  | https://www.gktoday.in/quizbase/appsc | verified 06 Sep 2026 — APPSC state GK — 5 pages (3000-MCQ course sample) |
| GKToday Telugu CA | `index`  | https://www.gktoday.in/quizbase/telugu-current-affairs | verified 06 Sep 2026 — NATIVE TELUGU current-affairs MCQs — no translation needed |
| Sakshi Telugu Daily CA MCQs | `index` `te` | https://education.sakshi.com/current-affairs/practice-test | verified 07 Sep 2026 — 25 Telugu CA MCQs per day, listing paginated ?page=N (3 months deep) |
| Sakshi APPSC Groups Practice | `index` `te` | https://education.sakshi.com/groups/practice-test | verified 07 Sep 2026 — AP economy, sciences, S&T, disaster management Telugu practice bits |
| FreshersNow Andhra Pradesh GK Quiz | `index`  | https://www.freshersnow.com/andhra-pradesh-gk-quiz/ | verified 07 Sep 2026 — 25 AP GK MCQs (Andhra history/polity) with answers |
| FreshersNow GK Topic Quizzes | `index`  | https://www.freshersnow.com/gk-questions-answers/ | verified 07 Sep 2026 — Indian history/polity/economy/geography/science + state-wise GK quizzes |
| GKSeries Indian Polity Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — chapter-wise polity MCQs (FRs, DPSP, judiciary…) with explanations |
| GKSeries Indian History Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — IVC → national movement, chapter-wise with answers |
| GKSeries Geography Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — geomorphology/climatology/oceanography chapter MCQs |
| GKSeries Indian Economy Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — planning, banking system, fiscal system chapter MCQs |
| MCQBits Previous Year Papers | `index`  | https://www.mcqbits.com/category/previous-year-question-papers/ | verified 07 Sep 2026 — TS/AP/central previous papers, paginated posts |
| MCQBits APPSC | `index`  | https://www.mcqbits.com/category/appsc/ | verified 07 Sep 2026 — APPSC Group/Grama Sachivalayam practice + PYQs |
| Eenadu Pratibha PYQ PDFs (Groups) | `index` `pdf` | https://pratibha.eenadu.net/previouspapers/paperslist/jobs/2-1001-41 | verified 07 Sep 2026 — TGPSC/APPSC Group papers with key, PDF per paper (pratibhaassets ... .pdf) |

### 🟡 Candidates (13)

| Source | Type | URL | Notes |
|---|---|---|---|
| SRM Tutors GK Bits Telugu | `index` `te` | https://srmtutors.in/50-latest-gk-questions-in-telugu/ | '1000 GK bits in Telugu' PART-01..20 (Q + జవాబు one-liners; MCQ gate may reject) |
| QuizDunia Telugu GK 100-bit sets | `index` `te` | https://www.quizdunia.com/ | Blogger site: 10 x 100-bit + 10 x 50-bit Telugu MCQ sets, monthly Telugu CA MCQs (A./B./C./D. labels; answers may be JS-only) |
| ReadingRoomz APPSC Daily CA (bilingual) | `index`  | https://readingroomz.com/category/daily-current-affairs/ | AP-specific daily CA notes with Telugu+English MCQs (free daily posts) |
| Eenadu Pratibha Telugu Quiz — Reasoning | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDEw | Telugu-native 10-Q quizzes (89 sets); key served by AJAX — enable once answer endpoint mapped |
| Eenadu Pratibha Telugu Quiz — Polity | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDA4 | Telugu పాలిటీ quizzes — AJAX key (content gate) |
| Eenadu Pratibha Telugu Quiz — History | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDAx | Telugu చరిత్ర quizzes — AJAX key (content gate) |
| Eenadu Pratibha Telugu Quiz — Arithmetic | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDEx | Telugu అరిథ్‌మెటిక్‌ quizzes — AJAX key (content gate) |
| Sakshi APPSC Bitbank Hub | `index`  | https://education.sakshi.com/groups/appsc-bitbank | AP-specific bit bank hub (path inferred from TSPSC twin; content gate) |
| Sakshi Bit Bank (English) | `index`  | https://education.sakshi.com/bitbank | legacy bit bank section — may redirect |
| Vyoma Telugu MCQs | `index`  | https://vyoma.net/mcqs/ | 2 lakh Telugu MCQs (APPSC/TSPSC exam-wise) — fetch blocked from crawler on 07 Sep |
| MCQAnswers TS/AP PYQs | `index`  | https://mcqanswers.com/appsc-tspsc-previous-year-papers/ | 3,500 APPSC/TSPSC PYQ MCQs in Telugu — fetch failed on 07 Sep |
| Adda247 Telugu Quiz | `index`  | https://www.adda247.com/te/category/quiz/ | Adda Telugu — quiz category 404 on 07 Sep 2026; re-check |
| Examveda State GK | `index`  | https://www.examveda.com/mcq-question-on-state-gk/ | state-wise GK — TS/AP pages content-gated |

## Police (TS/AP SI & Constable)

### 🟢 Live (18)

| Source | Type | URL | Notes |
|---|---|---|---|
| GKToday General Science | `index`  | https://www.gktoday.in/quizbase/general-science-for-competitive-examinations | verified 06 Sep 2026 — general science MCQs |
| GKToday Biology | `index`  | https://www.gktoday.in/quizbase/general-science-biology-mcqs | verified 06 Sep 2026 — biology MCQs |
| Sakshi TS Police Bitbank - Telangana History | `index` `te` | https://education.sakshi.com/ts-police/bitbank/telangana-history | verified 07 Sep 2026 — 30+ posts x 25 Telugu MCQs (Kakatiya, Qutb Shahi, Asaf Jahi, Telangana movement) |
| Sakshi TS Police Bitbank - Telangana Geography | `index` `te` | https://education.sakshi.com/ts-police/bitbank/telangana-geography | verified 07 Sep 2026 — TS geography Telugu MCQs |
| Sakshi TS Police Bitbank - Polity | `index` `te` | https://education.sakshi.com/ts-police/bitbank/polity | verified 07 Sep 2026 — Indian polity Telugu MCQs |
| Sakshi TS Police Bitbank - Science | `index` `te` | https://education.sakshi.com/ts-police/bitbank/physics | verified 07 Sep 2026 — physics (chemistry/biology siblings via link_re) |
| Sakshi TS Police Bitbank - Indian History & Economy | `index` `te` | https://education.sakshi.com/ts-police/bitbank/indian-history | verified 07 Sep 2026 — Indian history / economy Telugu MCQs |
| FreshersNow Telangana GK Quiz | `index`  | https://www.freshersnow.com/telangana-gk-quiz/ | verified 07 Sep 2026 — 25 TS GK MCQs with answers+explanations (English) |
| FreshersNow Andhra Pradesh GK Quiz | `index`  | https://www.freshersnow.com/andhra-pradesh-gk-quiz/ | verified 07 Sep 2026 — 25 AP GK MCQs (Andhra history/polity) with answers |
| FreshersNow Reasoning Topic Quizzes | `index`  | https://www.freshersnow.com/reasoning-questions-answers/ | verified 07 Sep 2026 — 60+ topic pages (blood relations, syllogism, seating, coding, series, puzzles, non-verbal) x 25 Q with answer+explanation |
| FreshersNow Aptitude Topic Quizzes | `index`  | https://www.freshersnow.com/aptitude-questions-answers-solutions/ | verified 07 Sep 2026 — 40+ arithmetic topic pages (percentage, time-work, trains, mensuration, probability...) x 25 Q with solutions |
| GKSeries Sports GK | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — sports GK MCQs (Olympics, Asian Games, cricket…) |
| AffairsCloud Blood Relation Sets | `index`  | https://affairscloud.com/logical-reasoning-questions/blood-relation/ | verified 07 Sep 2026 — 20+ numbered sets, Answer- N) text |
| AffairsCloud Static GK Q&A | `index`  | https://affairscloud.com/general-knowledge-questions-and-answers/ | verified 07 Sep 2026 — static GK + banking/computer awareness sets |
| MCQBits TSLPRB Police | `index`  | https://www.mcqbits.com/category/tslprb/ | verified 07 Sep 2026 — TS SI/Constable prelims papers + GS sets |
| Eenadu Pratibha PYQ PDFs (Police) | `index` `pdf` | https://pratibha.eenadu.net/previouspapers/paperslist/jobs/2-1001-41-610 | verified 07 Sep 2026 — TS/AP SI & Constable prelims/mains papers with key (2022-2023 + archive to 2005) |
| Eenadu Pratibha Model Papers (Police) | `index` `pdf` | https://pratibha.eenadu.net/modelpaper/paperslist/jobs/2-1002-275-625 | verified 07 Sep 2026 — SI/Constable model papers (Telugu) |
| Examveda Non-Verbal | `index`  | https://www.examveda.com/mcq-question-on-non-verbal-reasoning/ | verified 06 Sep 2026 — non-verbal reasoning topics |

### 🟡 Candidates (9)

| Source | Type | URL | Notes |
|---|---|---|---|
| Eenadu Pratibha TS Police Lessons | `index`  | https://pratibha.eenadu.net/jobs/studymaterial/police-jobs/police-jobs-telangana/telugu-medium/2-1-10-427-724-1425 | Telugu arithmetic/reasoning lessons ending in practice bits |
| LSR Updates Telangana GK (Telugu) | `index` `te` | https://lsrupdates.com/category/telangana-history/ | Telugu 'Question No.N' + 'ఎ) బి) సి) డి)' + 'Answer : సి)' posts (fetch blocked from sandbox) |
| AP Police Exams (Telugu medium) Model Papers | `index`  | https://www.appoliceexams.com/ | AP constable/SI Telugu chapter-wise tests (likely login/JS; gate decides) |
| QuestionPapersOnline AP Police PYQ PDFs | `index` `pdf` | https://www.questionpapersonline.com/ap-police-si-previous-papers/ | AP SI/constable previous paper PDFs (Telugu) — harvested via pdf_re when audited live |
| Eenadu Pratibha Telugu Quiz — Reasoning | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDEw | Telugu-native 10-Q quizzes (89 sets); key served by AJAX — enable once answer endpoint mapped |
| Eenadu Pratibha Telugu Quiz — Arithmetic | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDEx | Telugu అరిథ్‌మెటిక్‌ quizzes — AJAX key (content gate) |
| Sakshi English Bank Bitbank - Reasoning | `index`  | https://education.sakshi.com/en/bank-exams/study-material/reasoning | English reasoning bit bank linked from TG Police page |
| Sakshi English Bank Bitbank - Quant | `index`  | https://education.sakshi.com/en/bank-exams/study-material/quantitative-aptitude | English arithmetic bit bank linked from TG Police page |
| Testmocks Non-Verbal | `index`  | https://www.testmocks.com/practice/non-verbal-reasoning/ | non-verbal practice |

## SSC (CGL/CHSL/MTS/GD)

### 🟢 Live (42)

| Source | Type | URL | Notes |
|---|---|---|---|
| SSCAdda Quiz | `index`  | https://www.sscadda.com/ | verified Sep 2026 — homepage verified; /feed redirects, so article links are deep-crawled and content-gated |
| CareerPower Quiz | `index`  | https://www.careerpower.in/blog/ | verified Sep 2026 — blog listing verified; /blog/feed redirects, article links deep-crawled + content-gated |
| IndiaBIX Aptitude | `index`  | https://www.indiabix.com/aptitude/questions-and-answers/ | verified 06 Sep 2026 — 35+ quant topics (trains, SI/CI, % etc.) |
| IndiaBIX General Knowledge | `index`  | https://www.indiabix.com/general-knowledge/questions-and-answers/ | verified 06 Sep 2026 — static GK sections |
| IndiaBIX Data Interpretation | `index`  | https://www.indiabix.com/data-interpretation/questions-and-answers/ | verified 06 Sep 2026 — DI tables/charts (exported from same verified markup) |
| IndiaBIX Verbal Ability | `index`  | https://www.indiabix.com/verbal-ability/questions-and-answers/ | verified 06 Sep 2026 — English usage questions |
| IndiaBIX Current Affairs | `index`  | https://www.indiabix.com/current-affairs/questions-and-answers/ | verified 06 Sep 2026 — CA Q&A on the verified IndiaBIX platform |
| GKToday Polity | `index`  | https://www.gktoday.in/quizbase/indian-polity-constitution-mcqs | verified 06 Sep 2026 — Indian Polity & Constitution MCQs, 5 pages, Notes explanations |
| GKToday Ancient History | `index`  | https://www.gktoday.in/quizbase/ancient-indian-history-multiple-choice-questions | verified 06 Sep 2026 — SSC/RRB level ancient history MCQs |
| GKToday Medieval History | `index`  | https://www.gktoday.in/quizbase/medieval-indian-history | verified 06 Sep 2026 — medieval history MCQs |
| GKToday Modern History | `index`  | https://www.gktoday.in/quizbase/modern-indian-history-freedom-struggle | verified 06 Sep 2026 — freedom struggle MCQs |
| GKToday Indian Geography | `index`  | https://www.gktoday.in/quizbase/indian-geography-mcqs | verified 06 Sep 2026 — Indian geography MCQs |
| GKToday Indian Economy | `index`  | https://www.gktoday.in/quizbase/indian-economy-mcqs | verified 06 Sep 2026 — Indian economy MCQs |
| GKToday General Science | `index`  | https://www.gktoday.in/quizbase/general-science-for-competitive-examinations | verified 06 Sep 2026 — general science MCQs |
| GKToday Physics | `index`  | https://www.gktoday.in/quizbase/general-science-physics-mcqs | verified 06 Sep 2026 — physics MCQs |
| GKToday Chemistry | `index`  | https://www.gktoday.in/quizbase/general-science-chemistry | verified 06 Sep 2026 — chemistry MCQs |
| GKToday Biology | `index`  | https://www.gktoday.in/quizbase/general-science-biology-mcqs | verified 06 Sep 2026 — biology MCQs |
| GKToday Environment | `index`  | https://www.gktoday.in/quizbase/environment-ecology-biodiversity-mcqs | verified 06 Sep 2026 — environment & ecology MCQs |
| GKToday Art & Culture | `index`  | https://www.gktoday.in/quizbase/indian-culture-general-studies-mcqs | verified 06 Sep 2026 — art & culture MCQs |
| FreshersNow Reasoning Topic Quizzes | `index`  | https://www.freshersnow.com/reasoning-questions-answers/ | verified 07 Sep 2026 — 60+ topic pages (blood relations, syllogism, seating, coding, series, puzzles, non-verbal) x 25 Q with answer+explanation |
| FreshersNow Aptitude Topic Quizzes | `index`  | https://www.freshersnow.com/aptitude-questions-answers-solutions/ | verified 07 Sep 2026 — 40+ arithmetic topic pages (percentage, time-work, trains, mensuration, probability...) x 25 Q with solutions |
| FreshersNow GK Topic Quizzes | `index`  | https://www.freshersnow.com/gk-questions-answers/ | verified 07 Sep 2026 — Indian history/polity/economy/geography/science + state-wise GK quizzes |
| Examsbook Reasoning Articles | `index`  | https://www.examsbook.com/category/reasoning/page/1 | verified 07 Sep 2026 — reasoning quiz articles, 10 Q/page, up to 4 pages each |
| Examsbook Reasoning Questions & Answers | `index`  | https://www.examsbook.com/reasoning-questions-and-answers | verified 07 Sep 2026 — 4 pages x 10 Q (series, coding, direction, puzzles) |
| Target Classes Current Affairs 100 Q | `index`  | https://www.thetargetclasses.com/current-affairs/current-affairs-questions-and-answers/ | verified 07 Sep 2026 — 100 current-affairs MCQs (NDA/CDS/SSC), refreshed monthly |
| GKSeries Indian Polity Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — chapter-wise polity MCQs (FRs, DPSP, judiciary…) with explanations |
| GKSeries Indian History Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — IVC → national movement, chapter-wise with answers |
| GKSeries Geography Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — geomorphology/climatology/oceanography chapter MCQs |
| GKSeries Indian Economy Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — planning, banking system, fiscal system chapter MCQs |
| GKSeries Sports GK | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — sports GK MCQs (Olympics, Asian Games, cricket…) |
| AffairsCloud Reasoning Topic Sets | `index`  | https://affairscloud.com/reasoning-questions/ | verified 07 Sep 2026 — blood relation, syllogism, puzzles, coding sets (EN) |
| AffairsCloud Blood Relation Sets | `index`  | https://affairscloud.com/logical-reasoning-questions/blood-relation/ | verified 07 Sep 2026 — 20+ numbered sets, Answer- N) text |
| AffairsCloud Quant Topic Sets | `index`  | https://affairscloud.com/quantitative-aptitude-questions/ | verified 07 Sep 2026 — 24 topic categories (percentage, SI/CI, time-work…) |
| AffairsCloud Static GK Q&A | `index`  | https://affairscloud.com/general-knowledge-questions-and-answers/ | verified 07 Sep 2026 — static GK + banking/computer awareness sets |
| MCQBits Quantitative Aptitude | `index`  | https://www.mcqbits.com/category/quantitative-aptitude/ | verified 07 Sep 2026 — number system/average/HCF-LCM/P&C sets |
| Examveda Aptitude | `index`  | https://www.examveda.com/mcq-question-on-arithmetic-ability/ | verified 06 Sep 2026 — 35+ arithmetic topics (average, interest, ratio, trains, CI ...) |
| Examveda Non-Verbal | `index`  | https://www.examveda.com/mcq-question-on-non-verbal-reasoning/ | verified 06 Sep 2026 — non-verbal reasoning topics |
| Examveda English | `index`  | https://www.examveda.com/mcq-question-on-competitive-english/ | verified 06 Sep 2026 — synonyms/antonyms/error spotting/idioms |
| Examveda GK | `index`  | https://www.examveda.com/mcq-question-on-general-knowledge/ | verified 06 Sep 2026 — history/geography/polity/economy/science GK sections |
| Examveda DI | `index`  | https://www.examveda.com/mcq-question-on-data-interpretation/ | verified 06 Sep 2026 — table/bar/pie DI sets |
| Testmocks Quant | `index`  | https://www.testmocks.com/practice/quantitative-aptitude/ | verified 06 Sep 2026 — 23 quant topics, 20 Q each with explanations |
| Testmocks English | `index`  | https://www.testmocks.com/practice/verbal-ability/ | verified 06 Sep 2026 — 12 English topics (SSC/IBPS pattern) |

### 🟡 Candidates (56)

| Source | Type | URL | Notes |
|---|---|---|---|
| AffairsCloud Static GK | `rss`  | https://affairscloud.com/category/static-gk/feed/ | static GK for SSC/RRB/UPSC |
| CareerPower Practice Category | `rss`  | https://www.careerpower.in/blog/category/practice-set/feed/ | unverified category feed — auditor checks + content gate |
| Oliveboard SSC Category | `rss`  | https://www.oliveboard.in/blog/category/ssc/feed/ | SSC exam posts |
| PracticeMock SSC Category | `rss`  | https://www.practicemock.com/blog/category/ssc/feed/ | SSC mocks/practice |
| SSCAdda Quiz Category | `rss`  | https://www.sscadda.com/category/quiz/feed/ | unverified category feed — auditor checks + content gate |
| IxamBee Blog | `rss`  | https://www.ixambee.com/blog/feed | banking/SSC/railway exam blog |
| Mahendras Blog | `rss`  | https://www.mahendras.org/blog/feed | banking/SSC practice blog |
| Cracku Blog | `rss`  | https://cracku.in/blog/feed/ | quant/reasoning practice |
| CompetitiveExamsIndia Reasoning Tests | `index`  | https://www.competitiveexamsindia.com/reasoning/ | topic hubs -> 'Practice Test N' pages (quiz plugin renders options as plain lines; content gate decides) |
| CompetitiveExamsIndia Quant Tests | `index`  | https://www.competitiveexamsindia.com/quantitative-aptitude/ | arithmetic topic hubs -> practice tests |
| SSC Study Reasoning (English sets) | `index`  | https://sscstudy.com/reasoning-topic-wise-questions/ | PYQ-based topic tests; options rendered by quiz plugin without labels — needs JS/answer key, content gate decides |
| Careerride Reasoning Practice Tests | `index`  | https://www.careerride.com/subject/logical-reasoning.aspx | placement/competitive practice tests with explanations |
| Careerride Aptitude Practice Tests | `index`  | https://www.careerride.com/subject/aptitude.aspx | arithmetic practice tests (25 Q, explanations) |
| PendulumEdu SSC Quizzes | `index`  | https://pendulumedu.com/quiz/ssc | quiz pages parse but 'Answer : Option D' repeats for every Q — content gate must confirm key |
| Examrace Modern History MCQ Parts | `index`  | https://www.examrace.com/Sample-Objective-Questions/History-Questions/Modern-Indian-History/ | 66 parts of 'Q.' + (a)-(d) MCQs but NO key in HTML — needs answer source |
| Smartkeeda Reasoning Topics | `index`  | https://www.smartkeeda.com/reasoning-aptitude/ | testzone JS quizzes, only prose in HTML (content gate) |
| MCQBits SSC Reasoning | `index`  | https://www.mcqbits.com/category/ssc-reasoning/ | SSC reasoning sets |
| Mockers SSC CGL Mock | `index`  | https://www.mockers.in/exam/ssc-cgl-mock-test | mockers.in — free mock tests + PYQs; JS test player, content gate decides |
| Futurekul SSC CGL | `index`  | https://www.futurekul.com/free-mock-test/ssc-cgl | futurekul free mock tests (Next.js app; content gate) |
| Testmocks SSC Exams | `index`  | https://www.testmocks.com/exams/ssc/ | testmocks exam-wise sample papers |
| Examveda Computer | `index`  | https://www.examveda.com/mcq-question-on-computer-fundamentals/ | computer awareness (IBPS/SBI/SSC) |
| Testmocks DI | `index`  | https://www.testmocks.com/practice/data-interpretation/ | DI charts practice |
| Testmocks Non-Verbal | `index`  | https://www.testmocks.com/practice/non-verbal-reasoning/ | non-verbal practice |
| SSCAdda Reasoning | `index`  | https://www.sscadda.com/category/reasoning/ | SSC reasoning listing |
| SSCAdda Quant | `index`  | https://www.sscadda.com/category/quantitative-aptitude/ | SSC quant listing |
| CareerPower Practice Sets | `index`  | https://www.careerpower.in/blog/category/practice-set/ | practice-set listing deep crawl |
| IndiaBIX Mechanical | `index`  | https://www.indiabix.com/mechanical-engineering/questions-and-answers/ | IndiaBIX mechanical section (RRB JE / SSC JE syllabus) |
| IndiaBIX Electrical | `index`  | https://www.indiabix.com/electrical-engineering/questions-and-answers/ | IndiaBIX electrical section (RRB JE / SSC JE syllabus) |
| IndiaBIX Civil | `index`  | https://www.indiabix.com/civil-engineering/questions-and-answers/ | IndiaBIX civil section (RRB JE / SSC JE syllabus) |
| IndiaBIX Computer Science | `index`  | https://www.indiabix.com/computer-science/questions-and-answers/ | IndiaBIX computer awareness (IBPS/SBI/SSC) |
| SSCAdda CGL Tier 1 | `rss`  | https://www.sscadda.com/ssc-cgl/feed/ | SSC CGL prep feed |
| SSCAdda CHSL Tier 1 | `rss`  | https://www.sscadda.com/ssc-chsl/feed/ | SSC CHSL prep feed |
| SSCAdda MTS Exam | `rss`  | https://www.sscadda.com/ssc-mts/feed/ | SSC MTS prep feed |
| SSCAdda GD Constable | `rss`  | https://www.sscadda.com/ssc-gd-constable/feed/ | SSC GD prep feed |
| SSCAdda CPO Exam | `rss`  | https://www.sscadda.com/ssc-cpo/feed/ | SSC CPO prep feed |
| SSCAdda Selection Post | `rss`  | https://www.sscadda.com/ssc-selection-post/feed/ | SSC Selection Post feed |
| CareerPower SSC CGL | `rss`  | https://www.careerpower.in/blog/ssc-cgl/feed/ | CareerPower SSC CGL feed |
| CareerPower SSC CHSL | `rss`  | https://www.careerpower.in/blog/ssc-chsl/feed/ | CareerPower SSC CHSL feed |
| CareerPower SSC MTS | `rss`  | https://www.careerpower.in/blog/ssc-mts/feed/ | CareerPower SSC MTS feed |
| CareerPower SSC GD | `rss`  | https://www.careerpower.in/blog/ssc-gd/feed/ | CareerPower SSC GD feed |
| Testbook SSC CGL | `rss`  | https://testbook.com/ssc-cgl/feed/ | Testbook SSC CGL feed |
| Testbook SSC CHSL | `rss`  | https://testbook.com/ssc-chsl/feed/ | Testbook SSC CHSL feed |
| Testbook SSC MTS | `rss`  | https://testbook.com/ssc-mts/feed/ | Testbook SSC MTS feed |
| Testbook SSC GD | `rss`  | https://testbook.com/ssc-gd-constable/feed/ | Testbook SSC GD feed |
| BYJU Exam Prep SSC | `rss`  | https://byjusexamprep.com/ssc-exams/feed/ | BYJU Exam Prep SSC feed |
| PracticeMock SSC CGL | `rss`  | https://www.practicemock.com/blog/ssc-cgl/feed/ | PracticeMock SSC CGL feed |
| PracticeMock SSC CHSL | `rss`  | https://www.practicemock.com/blog/ssc-chsl/feed/ | PracticeMock SSC CHSL feed |
| PracticeMock SSC MTS | `rss`  | https://www.practicemock.com/blog/ssc-mts/feed/ | PracticeMock SSC MTS feed |
| Oliveboard SSC CGL | `rss`  | https://www.oliveboard.in/blog/ssc-cgl/feed/ | Oliveboard SSC CGL feed |
| Oliveboard SSC CHSL | `rss`  | https://www.oliveboard.in/blog/ssc-chsl/feed/ | Oliveboard SSC CHSL feed |
| SSCAdda General Awareness | `index`  | https://www.sscadda.com/category/general-awareness/ | SSC GA listing |
| SSCAdda English Language | `index`  | https://www.sscadda.com/category/english-language/ | SSC English listing |
| CareerPower Reasoning | `index`  | https://www.careerpower.in/blog/category/reasoning/ | CareerPower Reasoning listing |
| CareerPower Quant | `index`  | https://www.careerpower.in/blog/category/quantitative-aptitude/ | CareerPower Quant listing |
| IndiaBIX General Science | `index`  | https://www.indiabix.com/general-knowledge/general-science/questions-and-answers/ | IndiaBIX General Science |
| IndiaBIX Indian History | `index`  | https://www.indiabix.com/general-knowledge/indian-history/questions-and-answers/ | IndiaBIX Indian History |

## Banking (IBPS/SBI/RBI)

### 🟢 Live (23)

| Source | Type | URL | Notes |
|---|---|---|---|
| BankersAdda Quiz | `index`  | https://www.bankersadda.com/current-affairs/ | verified 05 Sep 2026 — daily banking CA quiz posts listed; /feed redirects to homepage (no RSS) |
| Oliveboard Quiz | `rss`  | https://www.oliveboard.in/blog/feed/ | verified 04 Sep 2026 — exam blog RSS parses, quiz posts strictly filtered |
| IndiaBIX Aptitude | `index`  | https://www.indiabix.com/aptitude/questions-and-answers/ | verified 06 Sep 2026 — 35+ quant topics (trains, SI/CI, % etc.) |
| IndiaBIX Data Interpretation | `index`  | https://www.indiabix.com/data-interpretation/questions-and-answers/ | verified 06 Sep 2026 — DI tables/charts (exported from same verified markup) |
| IndiaBIX Verbal Ability | `index`  | https://www.indiabix.com/verbal-ability/questions-and-answers/ | verified 06 Sep 2026 — English usage questions |
| IndiaBIX Current Affairs | `index`  | https://www.indiabix.com/current-affairs/questions-and-answers/ | verified 06 Sep 2026 — CA Q&A on the verified IndiaBIX platform |
| GKToday Indian Economy | `index`  | https://www.gktoday.in/quizbase/indian-economy-mcqs | verified 06 Sep 2026 — Indian economy MCQs |
| GKToday CA Banking | `index`  | https://www.gktoday.in/quizbase/business-economy-banking-current-affairs | verified 06 Sep 2026 — economy & banking CA MCQs |
| FreshersNow Reasoning Topic Quizzes | `index`  | https://www.freshersnow.com/reasoning-questions-answers/ | verified 07 Sep 2026 — 60+ topic pages (blood relations, syllogism, seating, coding, series, puzzles, non-verbal) x 25 Q with answer+explanation |
| FreshersNow Aptitude Topic Quizzes | `index`  | https://www.freshersnow.com/aptitude-questions-answers-solutions/ | verified 07 Sep 2026 — 40+ arithmetic topic pages (percentage, time-work, trains, mensuration, probability...) x 25 Q with solutions |
| Examsbook Reasoning Articles | `index`  | https://www.examsbook.com/category/reasoning/page/1 | verified 07 Sep 2026 — reasoning quiz articles, 10 Q/page, up to 4 pages each |
| Examsbook Reasoning Questions & Answers | `index`  | https://www.examsbook.com/reasoning-questions-and-answers | verified 07 Sep 2026 — 4 pages x 10 Q (series, coding, direction, puzzles) |
| GKSeries Indian Economy Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — planning, banking system, fiscal system chapter MCQs |
| AffairsCloud Reasoning Topic Sets | `index`  | https://affairscloud.com/reasoning-questions/ | verified 07 Sep 2026 — blood relation, syllogism, puzzles, coding sets (EN) |
| AffairsCloud Blood Relation Sets | `index`  | https://affairscloud.com/logical-reasoning-questions/blood-relation/ | verified 07 Sep 2026 — 20+ numbered sets, Answer- N) text |
| AffairsCloud Quant Topic Sets | `index`  | https://affairscloud.com/quantitative-aptitude-questions/ | verified 07 Sep 2026 — 24 topic categories (percentage, SI/CI, time-work…) |
| AffairsCloud Static GK Q&A | `index`  | https://affairscloud.com/general-knowledge-questions-and-answers/ | verified 07 Sep 2026 — static GK + banking/computer awareness sets |
| MCQBits Quantitative Aptitude | `index`  | https://www.mcqbits.com/category/quantitative-aptitude/ | verified 07 Sep 2026 — number system/average/HCF-LCM/P&C sets |
| Examveda Aptitude | `index`  | https://www.examveda.com/mcq-question-on-arithmetic-ability/ | verified 06 Sep 2026 — 35+ arithmetic topics (average, interest, ratio, trains, CI ...) |
| Examveda English | `index`  | https://www.examveda.com/mcq-question-on-competitive-english/ | verified 06 Sep 2026 — synonyms/antonyms/error spotting/idioms |
| Examveda DI | `index`  | https://www.examveda.com/mcq-question-on-data-interpretation/ | verified 06 Sep 2026 — table/bar/pie DI sets |
| Testmocks Quant | `index`  | https://www.testmocks.com/practice/quantitative-aptitude/ | verified 06 Sep 2026 — 23 quant topics, 20 Q each with explanations |
| Testmocks English | `index`  | https://www.testmocks.com/practice/verbal-ability/ | verified 06 Sep 2026 — 12 English topics (SSC/IBPS pattern) |

### 🟡 Candidates (28)

| Source | Type | URL | Notes |
|---|---|---|---|
| AffairsCloud Banking Awareness | `rss`  | https://affairscloud.com/category/banking-awareness/feed/ | banking-awareness posts for IBPS/SBI |
| BankersAdda Quiz Category | `rss`  | https://www.bankersadda.com/category/quiz/feed/ | unverified category feed — auditor checks + content gate |
| Oliveboard Quiz Category | `rss`  | https://www.oliveboard.in/blog/category/quiz/feed/ | unverified category feed — auditor checks + content gate |
| Oliveboard Banking Category | `rss`  | https://www.oliveboard.in/blog/category/banking/feed/ | banking exam posts |
| PracticeMock Banking Category | `rss`  | https://www.practicemock.com/blog/category/banking/feed/ | banking mocks/practice |
| BankExamsToday | `rss`  | https://www.bankexamstoday.com/feeds/posts/default?alt=rss | banking awareness + quizzes |
| Bankersdaily | `rss`  | https://bankersdaily.in/feed/ | banking daily quizzes + CA |
| IxamBee Blog | `rss`  | https://www.ixambee.com/blog/feed | banking/SSC/railway exam blog |
| Mahendras Blog | `rss`  | https://www.mahendras.org/blog/feed | banking/SSC practice blog |
| Cracku Blog | `rss`  | https://cracku.in/blog/feed/ | quant/reasoning practice |
| IBPSGuide Quiz | `rss`  | https://www.ibpsguide.com/feed | docs: stale ~180 days; re-verify before use |
| CompetitiveExamsIndia Reasoning Tests | `index`  | https://www.competitiveexamsindia.com/reasoning/ | topic hubs -> 'Practice Test N' pages (quiz plugin renders options as plain lines; content gate decides) |
| CompetitiveExamsIndia Quant Tests | `index`  | https://www.competitiveexamsindia.com/quantitative-aptitude/ | arithmetic topic hubs -> practice tests |
| Careerride Reasoning Practice Tests | `index`  | https://www.careerride.com/subject/logical-reasoning.aspx | placement/competitive practice tests with explanations |
| Careerride Aptitude Practice Tests | `index`  | https://www.careerride.com/subject/aptitude.aspx | arithmetic practice tests (25 Q, explanations) |
| Smartkeeda Reasoning Topics | `index`  | https://www.smartkeeda.com/reasoning-aptitude/ | testzone JS quizzes, only prose in HTML (content gate) |
| Sakshi English Bank Bitbank - Reasoning | `index`  | https://education.sakshi.com/en/bank-exams/study-material/reasoning | English reasoning bit bank linked from TG Police page |
| Sakshi English Bank Bitbank - Quant | `index`  | https://education.sakshi.com/en/bank-exams/study-material/quantitative-aptitude | English arithmetic bit bank linked from TG Police page |
| MCQBits SBI PO Clerk | `index`  | https://www.mcqbits.com/category/sbi-po-clerk/ | banking practice sets |
| Mockers IBPS PO Mock | `index`  | https://www.mockers.in/exam/ibps-po-mock-test | mockers.in banking mocks |
| Examveda Computer | `index`  | https://www.examveda.com/mcq-question-on-computer-fundamentals/ | computer awareness (IBPS/SBI/SSC) |
| Testmocks DI | `index`  | https://www.testmocks.com/practice/data-interpretation/ | DI charts practice |
| BankersAdda Reasoning | `index`  | https://www.bankersadda.com/category/reasoning/ | reasoning practice listing — content-gated deep crawl |
| BankersAdda Quant | `index`  | https://www.bankersadda.com/category/quantitative-aptitude/ | quant practice listing — content-gated deep crawl |
| IndiaBIX Computer Science | `index`  | https://www.indiabix.com/computer-science/questions-and-answers/ | IndiaBIX computer awareness (IBPS/SBI/SSC) |
| BYJU Exam Prep Banking | `rss`  | https://byjusexamprep.com/banking-exams/feed/ | BYJU Exam Prep Banking feed |
| BankersAdda IBPS PO | `rss`  | https://www.bankersadda.com/ibps-po/feed/ | BankersAdda IBPS PO feed |
| BankersAdda SBI PO | `rss`  | https://www.bankersadda.com/sbi-po/feed/ | BankersAdda SBI PO feed |

## Railway (RRB NTPC/Group D/ALP)

### 🟢 Live (29)

| Source | Type | URL | Notes |
|---|---|---|---|
| IndiaBIX Aptitude | `index`  | https://www.indiabix.com/aptitude/questions-and-answers/ | verified 06 Sep 2026 — 35+ quant topics (trains, SI/CI, % etc.) |
| IndiaBIX General Knowledge | `index`  | https://www.indiabix.com/general-knowledge/questions-and-answers/ | verified 06 Sep 2026 — static GK sections |
| GKToday Polity | `index`  | https://www.gktoday.in/quizbase/indian-polity-constitution-mcqs | verified 06 Sep 2026 — Indian Polity & Constitution MCQs, 5 pages, Notes explanations |
| GKToday Ancient History | `index`  | https://www.gktoday.in/quizbase/ancient-indian-history-multiple-choice-questions | verified 06 Sep 2026 — SSC/RRB level ancient history MCQs |
| GKToday Medieval History | `index`  | https://www.gktoday.in/quizbase/medieval-indian-history | verified 06 Sep 2026 — medieval history MCQs |
| GKToday Modern History | `index`  | https://www.gktoday.in/quizbase/modern-indian-history-freedom-struggle | verified 06 Sep 2026 — freedom struggle MCQs |
| GKToday Indian Geography | `index`  | https://www.gktoday.in/quizbase/indian-geography-mcqs | verified 06 Sep 2026 — Indian geography MCQs |
| GKToday General Science | `index`  | https://www.gktoday.in/quizbase/general-science-for-competitive-examinations | verified 06 Sep 2026 — general science MCQs |
| GKToday Physics | `index`  | https://www.gktoday.in/quizbase/general-science-physics-mcqs | verified 06 Sep 2026 — physics MCQs |
| GKToday Chemistry | `index`  | https://www.gktoday.in/quizbase/general-science-chemistry | verified 06 Sep 2026 — chemistry MCQs |
| GKToday Biology | `index`  | https://www.gktoday.in/quizbase/general-science-biology-mcqs | verified 06 Sep 2026 — biology MCQs |
| FreshersNow Reasoning Topic Quizzes | `index`  | https://www.freshersnow.com/reasoning-questions-answers/ | verified 07 Sep 2026 — 60+ topic pages (blood relations, syllogism, seating, coding, series, puzzles, non-verbal) x 25 Q with answer+explanation |
| FreshersNow Aptitude Topic Quizzes | `index`  | https://www.freshersnow.com/aptitude-questions-answers-solutions/ | verified 07 Sep 2026 — 40+ arithmetic topic pages (percentage, time-work, trains, mensuration, probability...) x 25 Q with solutions |
| FreshersNow GK Topic Quizzes | `index`  | https://www.freshersnow.com/gk-questions-answers/ | verified 07 Sep 2026 — Indian history/polity/economy/geography/science + state-wise GK quizzes |
| Examsbook Reasoning Articles | `index`  | https://www.examsbook.com/category/reasoning/page/1 | verified 07 Sep 2026 — reasoning quiz articles, 10 Q/page, up to 4 pages each |
| Examsbook Reasoning Questions & Answers | `index`  | https://www.examsbook.com/reasoning-questions-and-answers | verified 07 Sep 2026 — 4 pages x 10 Q (series, coding, direction, puzzles) |
| GKSeries Indian History Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — IVC → national movement, chapter-wise with answers |
| GKSeries Geography Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — geomorphology/climatology/oceanography chapter MCQs |
| GKSeries Sports GK | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — sports GK MCQs (Olympics, Asian Games, cricket…) |
| AffairsCloud Reasoning Topic Sets | `index`  | https://affairscloud.com/reasoning-questions/ | verified 07 Sep 2026 — blood relation, syllogism, puzzles, coding sets (EN) |
| AffairsCloud Blood Relation Sets | `index`  | https://affairscloud.com/logical-reasoning-questions/blood-relation/ | verified 07 Sep 2026 — 20+ numbered sets, Answer- N) text |
| AffairsCloud Quant Topic Sets | `index`  | https://affairscloud.com/quantitative-aptitude-questions/ | verified 07 Sep 2026 — 24 topic categories (percentage, SI/CI, time-work…) |
| AffairsCloud Static GK Q&A | `index`  | https://affairscloud.com/general-knowledge-questions-and-answers/ | verified 07 Sep 2026 — static GK + banking/computer awareness sets |
| MCQBits RRB NTPC | `index`  | https://www.mcqbits.com/category/rrb-ntpc/ | verified 07 Sep 2026 — RRB NTPC CBT-1/2 + previous papers |
| MCQBits Quantitative Aptitude | `index`  | https://www.mcqbits.com/category/quantitative-aptitude/ | verified 07 Sep 2026 — number system/average/HCF-LCM/P&C sets |
| Examveda Aptitude | `index`  | https://www.examveda.com/mcq-question-on-arithmetic-ability/ | verified 06 Sep 2026 — 35+ arithmetic topics (average, interest, ratio, trains, CI ...) |
| Examveda Non-Verbal | `index`  | https://www.examveda.com/mcq-question-on-non-verbal-reasoning/ | verified 06 Sep 2026 — non-verbal reasoning topics |
| Examveda GK | `index`  | https://www.examveda.com/mcq-question-on-general-knowledge/ | verified 06 Sep 2026 — history/geography/polity/economy/science GK sections |
| Testmocks Quant | `index`  | https://www.testmocks.com/practice/quantitative-aptitude/ | verified 06 Sep 2026 — 23 quant topics, 20 Q each with explanations |

### 🟡 Candidates (17)

| Source | Type | URL | Notes |
|---|---|---|---|
| AffairsCloud Static GK | `rss`  | https://affairscloud.com/category/static-gk/feed/ | static GK for SSC/RRB/UPSC |
| Oliveboard RRB Category | `rss`  | https://www.oliveboard.in/blog/category/rrb/feed/ | RRB exam posts |
| IxamBee Blog | `rss`  | https://www.ixambee.com/blog/feed | banking/SSC/railway exam blog |
| SSC Study Reasoning (English sets) | `index`  | https://sscstudy.com/reasoning-topic-wise-questions/ | PYQ-based topic tests; options rendered by quiz plugin without labels — needs JS/answer key, content gate decides |
| PendulumEdu Railways Quizzes | `index`  | https://pendulumedu.com/quiz/railways | same PendulumEdu key caveat (content gate) |
| Sakshi RRB Bitbank | `index`  | https://education.sakshi.com/rrb-exams | RRB section — bitbank links discovered by content gate |
| Mockers RRB NTPC Mock | `index`  | https://www.mockers.in/exam/rrb-ntpc-mock-test | mockers.in railway mocks |
| Futurekul RRB NTPC | `index`  | https://www.futurekul.com/free-mock-test/rrb-ntpc | futurekul railway mocks |
| Testmocks RRB Exams | `index`  | https://www.testmocks.com/exams/rrb/ | testmocks railway sample papers |
| Testmocks Non-Verbal | `index`  | https://www.testmocks.com/practice/non-verbal-reasoning/ | non-verbal practice |
| IndiaBIX Mechanical | `index`  | https://www.indiabix.com/mechanical-engineering/questions-and-answers/ | IndiaBIX mechanical section (RRB JE / SSC JE syllabus) |
| IndiaBIX Electrical | `index`  | https://www.indiabix.com/electrical-engineering/questions-and-answers/ | IndiaBIX electrical section (RRB JE / SSC JE syllabus) |
| IndiaBIX Civil | `index`  | https://www.indiabix.com/civil-engineering/questions-and-answers/ | IndiaBIX civil section (RRB JE / SSC JE syllabus) |
| BYJU Exam Prep Railway | `rss`  | https://byjusexamprep.com/railway-exams/feed/ | BYJU Exam Prep Railway feed |
| PracticeMock RRB NTPC | `rss`  | https://www.practicemock.com/blog/rrb-ntpc/feed/ | PracticeMock RRB NTPC feed |
| Oliveboard RRB Group D | `rss`  | https://www.oliveboard.in/blog/rrb-group-d/feed/ | Oliveboard RRB Group D feed |
| IndiaBIX General Science | `index`  | https://www.indiabix.com/general-knowledge/general-science/questions-and-answers/ | IndiaBIX General Science |

## Defence (NDA/CDS/Agniveer)

### 🟢 Live (4)

| Source | Type | URL | Notes |
|---|---|---|---|
| GKToday Physics | `index`  | https://www.gktoday.in/quizbase/general-science-physics-mcqs | verified 06 Sep 2026 — physics MCQs |
| GKToday Chemistry | `index`  | https://www.gktoday.in/quizbase/general-science-chemistry | verified 06 Sep 2026 — chemistry MCQs |
| GKToday CA Defence | `index`  | https://www.gktoday.in/quizbase/defence-current-affairs | verified 06 Sep 2026 — defence CA MCQs — DRDO/INS/missiles |
| Target Classes Current Affairs 100 Q | `index`  | https://www.thetargetclasses.com/current-affairs/current-affairs-questions-and-answers/ | verified 07 Sep 2026 — 100 current-affairs MCQs (NDA/CDS/SSC), refreshed monthly |

### 🟡 Candidates (2)

| Source | Type | URL | Notes |
|---|---|---|---|
| SSBCrackExams | `rss`  | https://www.ssbcrackexams.com/feed/ | NDA/CDS/Agniveer exam desk |
| Testmocks NDA CDS | `index`  | https://www.testmocks.com/exams/nda/ | testmocks defence sample papers |

## UPSC / General Studies

### 🟢 Live (13)

| Source | Type | URL | Notes |
|---|---|---|---|
| InsightsIndia Quiz | `rss`  | https://www.insightsonindia.com/feed | verified 06 Sep 2026 — daily UPSC Current Affairs Quiz post |
| IndiaBIX General Knowledge | `index`  | https://www.indiabix.com/general-knowledge/questions-and-answers/ | verified 06 Sep 2026 — static GK sections |
| IndiaBIX Current Affairs | `index`  | https://www.indiabix.com/current-affairs/questions-and-answers/ | verified 06 Sep 2026 — CA Q&A on the verified IndiaBIX platform |
| GKToday Polity | `index`  | https://www.gktoday.in/quizbase/indian-polity-constitution-mcqs | verified 06 Sep 2026 — Indian Polity & Constitution MCQs, 5 pages, Notes explanations |
| GKToday Ancient History | `index`  | https://www.gktoday.in/quizbase/ancient-indian-history-multiple-choice-questions | verified 06 Sep 2026 — SSC/RRB level ancient history MCQs |
| GKToday Medieval History | `index`  | https://www.gktoday.in/quizbase/medieval-indian-history | verified 06 Sep 2026 — medieval history MCQs |
| GKToday Modern History | `index`  | https://www.gktoday.in/quizbase/modern-indian-history-freedom-struggle | verified 06 Sep 2026 — freedom struggle MCQs |
| GKToday Indian Geography | `index`  | https://www.gktoday.in/quizbase/indian-geography-mcqs | verified 06 Sep 2026 — Indian geography MCQs |
| GKToday Indian Economy | `index`  | https://www.gktoday.in/quizbase/indian-economy-mcqs | verified 06 Sep 2026 — Indian economy MCQs |
| GKToday Environment | `index`  | https://www.gktoday.in/quizbase/environment-ecology-biodiversity-mcqs | verified 06 Sep 2026 — environment & ecology MCQs |
| GKToday Art & Culture | `index`  | https://www.gktoday.in/quizbase/indian-culture-general-studies-mcqs | verified 06 Sep 2026 — art & culture MCQs |
| GKSeries Indian Polity Chapters | `index`  | https://www.gkseries.com/general-knowledge/gk-subjects | verified 07 Sep 2026 — chapter-wise polity MCQs (FRs, DPSP, judiciary…) with explanations |
| Examveda GK | `index`  | https://www.examveda.com/mcq-question-on-general-knowledge/ | verified 06 Sep 2026 — history/geography/polity/economy/science GK sections |

### 🟡 Candidates (12)

| Source | Type | URL | Notes |
|---|---|---|---|
| AffairsCloud Static GK | `rss`  | https://affairscloud.com/category/static-gk/feed/ | static GK for SSC/RRB/UPSC |
| InsightsIndia Quizzes Category | `rss`  | https://www.insightsonindia.com/category/quizzes/feed/ | UPSC daily quiz category |
| InsightsIndia Secure | `rss`  | https://www.insightsonindia.com/category/secure-initiative/feed/ | UPSC Mains Secure initiative — CA depth |
| Drishti IAS | `rss`  | https://www.drishtiias.com/feed | UPSC current affairs + quiz depth |
| ClearIAS | `rss`  | https://www.clearias.com/feed/ | UPSC prelims MCQ + CA |
| BYJU IAS Prep | `rss`  | https://byjus.com/free-ias-prep/feed/ | UPSC free IAS prep feed |
| PMF IAS | `rss`  | https://www.pmfias.com/feed/ | geography/environment UPSC depth |
| CivilsDaily | `rss`  | https://www.civilsdaily.com/feed/ | UPSC daily CA |
| IASExpress | `rss`  | https://www.iasexpress.net/feed/ | UPSC notes/CA |
| PRS Blog | `rss`  | https://prsindia.org/theprsblog/feed | legislative research — polity PYQ depth |
| Examrace Modern History MCQ Parts | `index`  | https://www.examrace.com/Sample-Objective-Questions/History-Questions/Modern-Indian-History/ | 66 parts of 'Q.' + (a)-(d) MCQs but NO key in HTML — needs answer source |
| IndiaBIX Indian History | `index`  | https://www.indiabix.com/general-knowledge/indian-history/questions-and-answers/ | IndiaBIX Indian History |

## Current Affairs

### 🟢 Live (2)

| Source | Type | URL | Notes |
|---|---|---|---|
| Sakshi Daily Current Affairs Quiz (Telugu) | `index` `te` | https://education.sakshi.com/current-affairs/daily-current-affairs | verified 07 Sep 2026 — daily 'Current Affairs DD.MM.YY MCQs in Telugu' posts (Top 30 GK quiz) + prose digests; quiz gate keeps only MCQ posts |
| Target Classes Current Affairs 100 Q | `index`  | https://www.thetargetclasses.com/current-affairs/current-affairs-questions-and-answers/ | verified 07 Sep 2026 — 100 current-affairs MCQs (NDA/CDS/SSC), refreshed monthly |

### 🟡 Candidates (1)

| Source | Type | URL | Notes |
|---|---|---|---|
| Eenadu Pratibha Telugu Quiz — Current Affairs | `index` `te` | https://pratibha.eenadu.net/quiz/viewmore/NDA0 | Telugu కరెంట్ అఫైర్స్ quizzes — AJAX key (content gate) |

## All exams (shared reasoning / aptitude / GK)

### 🟢 Live (15)

| Source | Type | URL | Notes |
|---|---|---|---|
| AffairsCloud | `rss`  | https://affairscloud.com/feed | verified 05 Sep 2026 — 30+ fresh CA quiz/current-affairs posts |
| PracticeMock Quiz | `rss`  | https://www.practicemock.com/blog/feed/ | verified 06 Sep 2026 — banking/SSC/UPSC exam blog |
| IndiaBIX Verbal Reasoning | `index`  | https://www.indiabix.com/verbal-reasoning/questions-and-answers/ | verified 06 Sep 2026 |
| IndiaBIX Logical Reasoning | `index`  | https://www.indiabix.com/logical-reasoning/questions-and-answers/ | verified 06 Sep 2026 |
| IndiaBIX Non Verbal Reasoning | `index`  | https://www.indiabix.com/non-verbal-reasoning/questions-and-answers/ | verified 06 Sep 2026 |
| GKToday CA Schemes | `index`  | https://www.gktoday.in/quizbase/government-schemes-current-affairs | verified 06 Sep 2026 — government schemes CA MCQs (topic-wise) |
| GKToday CA SciTech | `index`  | https://www.gktoday.in/quizbase/science-technology-current-affairs | verified 06 Sep 2026 — science & tech CA MCQs |
| GKToday CA India | `index`  | https://www.gktoday.in/quizbase/india-government-politics-current-affairs | verified 06 Sep 2026 — India government & politics CA MCQs |
| GKToday CA Reports | `index`  | https://www.gktoday.in/quizbase/reports-and-indices-current-affairs | verified 06 Sep 2026 — reports & indices CA MCQs |
| GKToday CA Days | `index`  | https://www.gktoday.in/quizbase/important-days-and-events-current-affairs | verified 06 Sep 2026 — important days CA MCQs |
| GKToday CA Awards | `index`  | https://www.gktoday.in/quizbase/awards-honours-persons-in-news-current-affairs | verified 06 Sep 2026 — awards & persons in news CA MCQs |
| GKToday Daily CA Quiz | `index`  | https://www.gktoday.in/gk-current-affairs-quiz-questions-answers/ | verified 06 Sep 2026 — daily CA quiz posts (10 Q each, Notes) |
| Examveda Reasoning | `index`  | https://www.examveda.com/mcq-question-on-competitive-reasoning/ | verified 06 Sep 2026 — 40+ reasoning topics (coding, series, syllogism, blood relation...), 83 Q/topic |
| Testmocks Logical | `index`  | https://www.testmocks.com/practice/logical-reasoning/ | verified 06 Sep 2026 — 18 logical reasoning topics |
| Testmocks Verbal Reasoning | `index`  | https://www.testmocks.com/practice/verbal-reasoning/ | verified 06 Sep 2026 — analogy/coding/blood relation/seating/direction |

### 🟡 Candidates (15)

| Source | Type | URL | Notes |
|---|---|---|---|
| AffairsCloud Quiz Category | `rss`  | https://affairscloud.com/category/current-affairs-quiz/feed/ | category feed — auditor content gate |
| Oliveboard Free Practice | `rss`  | https://www.oliveboard.in/blog/category/free-practice-questions/feed/ | free practice MCQ posts |
| PracticeMock Quiz Category | `rss`  | https://www.practicemock.com/blog/category/quiz/feed/ | unverified category feed — auditor checks + content gate |
| StudyIQ Articles | `rss`  | https://www.studyiq.com/articles/feed/ | exam CA/articles — content gate required |
| PendulumEdu Quiz | `rss`  | https://pendulumedu.com/feed | unverified URL — auditor checks feed + content |
| Smartkeeda Quiz | `rss`  | https://www.smartkeeda.com/feed/ | docs marked 404 in Aug 2026; re-verify before use |
| Jagran Josh Current Affairs Quiz | `rss`  | https://www.jagranjosh.com/rss/current-affairs-quizzes.xml | unverified RSS URL — auditor checks + content gate |
| Jagran Josh Education | `rss`  | https://www.jagranjosh.com/rss/edu.xml | education/exam desk RSS |
| Testbook Daily Quiz | `rss`  | https://testbook.com/feed/ | unverified main feed — auditor checks + content gate |
| Adda247 Current Affairs | `rss`  | https://currentaffairs.adda247.com/feed/ | Adda247 CA desk — content gate |
| The Hindu Education | `rss`  | https://www.thehindu.com/education/feeder/default.rss | education desk — exam-relevant only |
| India Today Education | `rss`  | https://www.indiatoday.in/rss/education | education desk RSS |
| TOI Education | `rss`  | https://timesofindia.indiatimes.com/rssfeeds/913168846.cms | education desk RSS |
| MCQBits Daily Quiz | `index`  | https://www.mcqbits.com/category/daily-quiz/ | daily mixed GK quiz posts |
| TestRanking | `index`  | https://www.testranking.in/ | testranking.in — app-only practice platform (empty SSR page); tracked |

## ⚫ Archive / dead (not used) — 91

Checked and rejected (dead domain, paywall, JS-only, redirect to home, parked domain, news-only). Kept so the auditor never re-adds them.

| Source | Reason |
|---|---|
| GKToday Quiz | dead | dead / HTTP 500 'Feed is temporarily not available' on 06 Sep 2026 — replaced by GKToday quizbase deep-index s |
| Testbook Quizzes | dead | dead / feed serves junk (Test post title / COVID spam) — not exam quiz content |
| Guidely Quiz | dead | dead / 404 Page Not Found (blog feed removed; /feed also 404) |
| RailwayAdda Quiz | dead | dead / host unreachable 06 Sep 2026 (site itself failed) |
| Adda247 Quiz | dead | dead / docs: 403 blocked |
| BankersAdda Old Feed | dead | dead / legacy URL |
| Testbook Quiz Category | dead | dead / category feed guess, no quiz content |
| Smartkeeda Old Root | dead | dead / 404 (Aug 2026) |
| IASbaba Root Feed | dead | dead / TLS (Aug 2026) |
| CivilServicesToday | dead | dead / 500 (Aug 2026) |
| Deccan Chronicle | dead | dead / TLS cert dead (Aug 2026) |
| Deccan Herald | dead | dead / 404 (Aug 2026) |
| TOI Hyderabad City | dead | dead / 404 (Aug 2026) |
| TOI Vijayawada City | dead | dead / 200 but 0 entries (Aug 2026) |
| Firstpost News | dead | dead / 403 (Aug 2026) |
| Livemint Top | dead | dead / HTML only (Aug 2026) |
| The Quint India | dead | dead / 404 (Aug 2026) |
| Frontline Magazine | dead | dead / HTML only (Aug 2026) |
| Telegraph India | dead | dead / 403 (Aug 2026) |
| Sakshi Telugu | tested | tested / sandbox 403, server OK per Aug-2026 audit |
| Samayam Telugu | dead | dead / TLS (Aug 2026) |
| 10MinuteTelugu | dead | dead / TLS (Aug 2026) |
| APJobs | dead | dead / junk/spam — permanently blocked |
| PIB Old | tested | tested / structured RSS may vary; auditor re-checks |
| PRS Legislative | dead | dead / 404 (Aug 2026) |
| NewsOnAir | dead | dead / timeout (Aug 2026) |
| RecruitmentIndia | dead | dead / HTML only (Aug 2026) |
| BBC India | dead | dead / 404 (Aug 2026) — foreign, blocked |
| The Week India | dead | dead / 403 (Aug 2026) — blocked |
| ABP Live | dead | dead / HTML only (Aug 2026) |
| Business Standard Old | dead | dead / HTML only (Aug 2026) |
| Times Now | archive | archive / re-scan |
| India TV | archive | archive / re-scan |
| CNN News18 | archive | archive / re-scan |
| Aaj Tak | archive | archive / re-scan |
| Republic TV | archive | archive / re-scan |
| FreeJobAlert | tested | tested / main jobs feed — used by news_feeds, verified Aug 2026 |
| SarkariYojana | tested | tested / Telugu jobs feed — used by news_feeds, verified Aug 2026 |
| GovtJobs.com | dead | dead / stale 170+ days |
| SarkariNaukri | archive | archive / re-scan |
| Freshersworld | dead | dead / 403 |
| NaukriGazzette | dead | dead / timeout |
| TSJobs.in | dead | dead / 404 |
| RailBiz | dead | dead / timeout |
| IBPS Guide (jobs) | dead | dead / stale |
| Eenadu Telugu | archive | archive / Telugu state news re-scan |
| AndhraJyothy | archive | archive / Telugu state news re-scan |
| NamastheTelangana | archive | archive / TS Telugu re-scan |
| TelanganaToday | archive | archive / TS English re-scan |
| HansIndia | archive | archive / south India re-scan |
| NewIndianExpress | archive | archive / national re-scan |
| ThePrint | archive | archive / policy depth re-scan |
| Scroll.in | archive | archive / longform re-scan |
| Wire.in | archive | archive / policy re-scan |
| Moneycontrol Markets | archive | archive / economy/markets re-scan |
| BusinessStandard RSS | archive | archive / economy re-scan |
| LiveMint Markets | archive | archive / markets re-scan |
| ORF Expert | archive | archive / foreign-policy research |
| IDSA | archive | archive / defence research |
| MyGov | archive | archive / gov portal re-scan |
| India.gov | archive | archive / gov portal re-scan |
| SarkariResult | archive | archive / jobs re-scan |
| SarkariExam | archive | archive / jobs re-scan |
| AllIndiaJobs | archive | archive / jobs re-scan |
| Jobriya | archive | archive / jobs re-scan |
| FreshersLive | archive | archive / jobs re-scan |
| SSBCrack | archive | archive / defence re-scan |
| MajorKalshiClasses | archive | archive / defence exam re-scan |
| Wifistudy | archive | archive / exam prep re-scan |
| Embibe Blog | archive | archive / exam prep re-scan |
| Toppr Bytes | archive | archive / student prep re-scan |
| Vedantu Blog | archive | archive / student prep re-scan |
| EduRev | archive | archive / exam notes re-scan |
| Gradeup Legacy | archive | archive / BYJU Exam Prep legacy |
| Unacademy Content | archive | archive / content re-scan |
| CareerLauncher | archive | archive / CAT/bank re-scan |
| VisionIAS Blog | archive | archive / UPSC coaching re-scan |
| Vajiram | archive | archive / UPSC coaching re-scan |
| ShankarIAS | archive | archive / UPSC coaching re-scan |
| NextIAS | archive | archive / UPSC coaching re-scan |
| ForumIAS | archive | archive / UPSC community re-scan |
| SleepyClasses | archive | archive / UPSC re-scan |
| OnlyIAS | archive | archive / UPSC re-scan |
| ChahalAcademy | archive | archive / UPSC re-scan |
| PlutusIAS | archive | archive / UPSC re-scan |
| UPSCPathshala | archive | archive / UPSC re-scan |
| KhanGlobalStudies | archive | archive / UPSC re-scan |
| ISRO Updates | archive | archive / space GK re-scan |
| RBI Press Releases | archive | archive / banking GK re-scan (HTML page, not RSS) |
| SSC Portal | archive | archive / SSC portal legacy re-scan |
| Qmaths SSC | archive | archive / SSC math prep re-scan |

## How new sources get in

1. Add in `scripts/rebuild_registry.py` (`_index` = verified live, `_cand_index` = unverified), run `--check` and rebuild.
2. `scripts/audit_sources.py` (04:45 daily) content-gates every source: live ones that stop returning MCQs pause after 3 failures; candidates that return MCQs auto-enable.
3. Every question passes the language gate (Telugu kept; English/Hindi → `translate_mcq` with number/script/duplicate checks, else parked) and the exam-blueprint gate before reaching a channel.
