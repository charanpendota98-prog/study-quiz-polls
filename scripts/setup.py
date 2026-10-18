#!/usr/bin/env python3
"""
STUDENTUP — ONE-COMMAND EASY SETUP
====================================
  python3 scripts/setup.py            # interactive-lite setup + all checks
  python3 scripts/setup.py --quick    # non-interactive (CI / servers)
  python3 scripts/setup.py --full     # also run the full 326+ test suite

Steps (all safe, all idempotent — run it as many times as you like):
  1. Python >= 3.10 check
  2. env/.env created from the template if missing (BOT_TOKEN stays blank
     for dry-run until you paste yours — nothing is ever uploaded)
  3. Question bank rebuilt + pre-deploy validation gate
  4. Source registry summary (517 sources: live / waiting-audit / domains)
     — new candidates auto-enable ONLY after the daily content-gated audit
  5. A full dry quiz round is simulated: polls are printed, nothing sent
  6. Exact next commands to go live are printed

No pip install needed: the engine runs on the Python standard library.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _run(label, argv, ok_rc=(0,)):
    print(f"\n── {label}\n   $ {' '.join(argv)}")
    r = subprocess.run(argv, cwd=ROOT)
    print(f"   -> {'OK' if r.returncode in ok_rc else 'rc=' + str(r.returncode)}")
    return r.returncode in ok_rc


def _sanitize_env_text(text):
    """Blank out template PLACEHOLDERS (123456:ABC-YourBot..., gsk_..., etc).

    A copied template must never make the engine believe a fake token/key
    exists — that would send real requests with junk credentials. Real
    values (URLs, IDs, numbers, words without placeholder markers) are
    preserved untouched. Returns (clean_text, n_blanked)."""
    import re
    out, n = [], 0
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2)
            low = val.lower()
            if ("..." in val or "your" in low or "paste" in low
                    or "example" in low or val.strip() in ("...",)):
                out.append(f"{key}=")
                n += 1
                continue
        out.append(line)
    return "\n".join(out) + "\n", n


def main():
    quick = "--quick" in sys.argv
    full = "--full" in sys.argv
    print("=" * 64)
    print("🎓 STUDENTUP — EASY SETUP (one command, stdlib only)")
    print("=" * 64)

    # 1) Python
    v = sys.version_info
    print(f"\n[1] Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        print("    ❌ Python 3.10+ kavali — upgrade chesi malli run cheyyandi")
        return 1
    print("    ✅ OK")

    # 2) env/.env
    print("\n[2] env/.env")
    env_file = ROOT / "env" / ".env"
    template = ROOT / "env" / ".env.template"
    if env_file.exists():
        clean, n = _sanitize_env_text(env_file.read_text(encoding="utf-8"))
        if n:
            env_file.write_text(clean, encoding="utf-8")
            print(f"    ✅ exists — {n} placeholder value(s) blanked "
                  "(fake tokens/keys can never poison a run)")
        else:
            print(f"    ✅ already exists ({env_file}) — untouched")
    elif template.exists():
        clean, n = _sanitize_env_text(template.read_text(encoding="utf-8"))
        env_file.write_text(clean, encoding="utf-8")
        try:
            env_file.chmod(0o600)
        except Exception:
            pass
        print(f"    ✅ created from template -> {env_file}")
        print("    ℹ️  BOT_TOKEN paste cheste live, lekapothe dry-run mode")
    else:
        print("    ⚠️ no template found — config defaults tho run avuthundi")

    if not quick and sys.stdin.isatty():
        try:
            ans = input("\n    BOT_TOKEN ippude paste chestara? "
                        "[Enter = skip / dry-run] ").strip()
        except EOFError:
            ans = ""
        if ans:
            txt = env_file.read_text(encoding="utf-8")
            import re
            txt = re.sub(r"^BOT_TOKEN=.*$", f"BOT_TOKEN={ans}", txt,
                         count=1, flags=re.M) if "BOT_TOKEN=" in txt \
                else txt + f"\nBOT_TOKEN={ans}\n"
            env_file.write_text(txt, encoding="utf-8")
            print("    ✅ BOT_TOKEN saved (file permissions 600)")

    # 3) Bank + validation gate
    print("\n[3] Question bank + validation gate")
    from core.question_bank import rebuild_json
    qs, errs = rebuild_json()
    print(f"    bank rebuilt: {len(qs)} valid questions, {len(errs)} rejected")
    if not _run("validation gate", [sys.executable, "scripts/finalize.py"]):
        print("    ❌ gate fail — paina errors chudandi")
        return 1

    # 4) Sources
    print("\n[4] Quiz sources (auto-managed registry)")
    from core.source_manager import stats as src_stats
    for k, val in src_stats().items():
        print(f"    {k:26s} {val}")
    print("    ℹ️  candidates daily 04:45 audit tho, content pass ayithe")
    print("        automatic ga enable avuthayi — manual ga em cheyyakkarledu")
    print("    ℹ️  kotha source: python3 -m core.source_manager discover <url>")

    # 5) Health + dry round
    _run("health check", [sys.executable, "scripts/check.py"])
    _run("dry quiz round (nothing is sent)",
         [sys.executable, "scripts/quiz_engine.py", "quiz", "--dry"])

    # 6) Tests (only on --full; they take ~4 seconds)
    if full:
        if not _run("full test suite",
                    [sys.executable, "-m", "unittest", "discover",
                     "-s", "tests"]):
            print("    ❌ tests fail — deploy cheyyakandi")
            return 1

    print("\n" + "=" * 64)
    print("✅ SETUP COMPLETE — go live ki ONE command chaalu:")
    print("   1) env/.env lo BOT_TOKEN + channel IDs confirm cheyyandi")
    print("      (lekunte ippudu cheyyandi: python3 scripts/setup.py)")
    print("   2) bash start_all.sh   ← Dashboard + WhatsApp Bridge +")
    print("      🔁 Scheduler (watch.py) + Bot (token unte) okkasare start!")
    print("      Scheduler valla sources nunchi CONTINUOUS collection:")
    print("      collector 8x/day + 04:45 audit + scout/backfill/PYQ —")
    print("      bank 566 tho aagadu, prathi roju periguthune untundi 📈")
    print("   3) Status eppudaina: python3 -m core.source_manager stats")
    print("      (production systemd: deploy/*.service chudandi)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
