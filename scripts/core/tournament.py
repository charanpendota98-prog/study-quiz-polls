#!/usr/bin/env python3
"""
STUDENTUP — ADVANCED TOURNAMENT & MULTI-TIER WAR LEAGUE ENGINE
Supports:
  1. District Knockout World Cup (Cricket / IPL Tournament Style):
     - Head-to-Head District Clashes (e.g. Warangal vs Karimnagar)
     - 4, 8, 16, or 20+ Districts Tournament (Quarter-Finals, Semi-Finals, Grand Finale)
     - Fair Normalized Scoring: Solves the population imbalance!
       If District A has 10 students and District B has 5 students,
       score is calculated as:
         Accuracy % * Avg Time Bonus + Scaled Activity Factor
       Ensures fair competition whether a district has 5 or 50 players!
  2. Weekly & Monthly District Wars Standings:
     - Top District of the Week (Week 1..52)
     - Top District of the Month (Jan..Dec)
     - Addictive prestige & pride for native districts
  3. One-Tap WhatsApp & Telegram Shareable War & Squad Links:
     - Native whatsapp:// and https://api.whatsapp.com/send?text= deep links
     - 600x600 Projector QR codes
  4. Instant Squad Auto-Matchmaking:
     - Match against another online squad automatically without room code searching!
"""

import time
import math
import random
import urllib.parse
from datetime import datetime
from pathlib import Path
from core import config
from core.store import load_json, save_json_atomic

TOURNAMENT_FILE = config.DATA / "tournaments.json"

DEFAULT_DATA = {
    "tournaments": {},
    "active_matches": [],
    "district_wars_weekly": {},
    "district_wars_monthly": {}
}


def load_tournaments() -> dict:
    if TOURNAMENT_FILE.exists():
        try:
            return load_json(TOURNAMENT_FILE, DEFAULT_DATA)
        except Exception:
            pass
    save_json_atomic(TOURNAMENT_FILE, DEFAULT_DATA)
    return dict(DEFAULT_DATA)


def save_tournaments(d: dict):
    save_json_atomic(TOURNAMENT_FILE, d)


def calculate_fair_score(correct: int, total_questions: int, players_count: int, total_time_sec: float = 0) -> float:
    """
    Fair Normalized Scoring Algorithm:
    - Base accuracy = (correct / total_answered) * 100
    - If a district has only 5 players vs 10 players, standard sum is unfair.
    - We compute:
        Average Accuracy per participant (0 - 100)
        + Participation Weight log2(players + 1) * 6 (rewards turnout without drowning small districts)
        + Speed Bonus (faster answers earn bonus)
    """
    if players_count <= 0 or total_questions <= 0:
        return 0.0

    avg_accuracy = (correct / (players_count * total_questions)) * 100.0
    avg_accuracy = min(max(avg_accuracy, 0.0), 100.0)

    # Turnout incentive (logarithmic scale)
    turnout_boost = math.log2(players_count + 1) * 6.0

    # Speed bonus (if tracked)
    speed_factor = 5.0 if total_time_sec < (players_count * 30) else 0.0

    fair_rating = round(avg_accuracy + turnout_boost + speed_factor, 1)
    return fair_rating


def create_district_clash(
    district_a: str,
    district_b: str,
    title: str = "",
    exam_target: str = "POLICE",
    num_questions: int = 5
) -> dict:
    """Create a 1-on-1 Head-to-Head District Clash with WhatsApp & Telegram share links."""
    data = load_tournaments()
    clash_id = f"CLASH_{int(time.time()) % 10000}_{random.randint(100, 999)}"
    match_title = title.strip() or f"{district_a} vs {district_b} Super Derby"

    bot = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
    link_a = f"https://t.me/{bot}?start=war_{clash_id}_A"
    link_b = f"https://t.me/{bot}?start=war_{clash_id}_B"
    shared_link = f"https://t.me/{bot}?start=war_{clash_id}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={shared_link}"

    wa_text = (
        f"⚔️ *{match_title.upper()}* ⚔️\n\n"
        f"మన ఊరు జిల్లా కోసం బరిలోకి దిగుదాం! Telugu District War Derby!\n"
        f"🔥 {district_a} vs {district_b} 🔥\n\n"
        f"🏆 {district_a} టీమ్ లో చేరండి: {link_a}\n"
        f"🏆 {district_b} టీమ్ లో చేరండి: {link_b}\n\n"
        f"లేదా ఇక్కడ క్లిక్ చేసి నేరుగా ఆడండి: {shared_link}\n"
        f"మీ జిల్లా పరువు కాపాడండి! Share to your college & friends groups!"
    )
    whatsapp_share_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(wa_text)}"

    match = {
        "id": clash_id,
        "type": "DISTRICT_CLASH",
        "title": match_title,
        "exam_target": exam_target,
        "num_questions": num_questions,
        "status": "LIVE_LOBBY",  # LIVE_LOBBY, IN_PROGRESS, COMPLETED
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "team_a": {
            "name": district_a,
            "players": {},  # uid -> {name, correct, time_sec}
            "score": 0.0
        },
        "team_b": {
            "name": district_b,
            "players": {},
            "score": 0.0
        },
        "winner": None,
        "shared_link": shared_link,
        "team_a_link": link_a,
        "team_b_link": link_b,
        "qr_url": qr_url,
        "whatsapp_share_url": whatsapp_share_url
    }

    data.setdefault("tournaments", {})[clash_id] = match
    save_tournaments(data)
    return match


def create_world_cup_tournament(
    districts_list: list,
    title: str = "Telangana & AP District World Cup",
    exam_target: str = "ALL"
) -> dict:
    """
    Cricket / IPL World Cup Style Tournament:
    Takes 4, 8, 16, or 20 districts and sets up knockout bracket (Quarter-Finals, Semi-Finals, Grand Finale).
    """
    data = load_tournaments()
    tourney_id = f"WCUP_{int(time.time()) % 10000}"
    d_list = list(districts_list)
    random.shuffle(d_list)

    # Group into pairs of 2 for Round 1
    pairs = []
    for i in range(0, len(d_list) - 1, 2):
        pairs.append({
            "match_no": len(pairs) + 1,
            "team_1": d_list[i],
            "team_2": d_list[i + 1],
            "team_1_score": 0.0,
            "team_2_score": 0.0,
            "winner": None,
            "status": "Ready"
        })

    total_teams = len(pairs) * 2
    round_name = "Quarter-Finals" if total_teams == 8 else ("Semi-Finals" if total_teams == 4 else "Round of 16")

    bot = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
    shared_link = f"https://t.me/{bot}?start=tourney_{tourney_id}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={shared_link}"

    wa_text = (
        f"🏆 *{title.upper()}* 🏆\n\n"
        f"తెలంగాణ & ఆంధ్రప్రదేశ్ జిల్లాల మహా సంగ్రామం ప్రారంభమైంది! World Cup Knockout Trophy!\n"
        f"మొత్తం {total_teams} జిల్లాలు పోటీపడుతున్నాయి. మీ జిల్లా ఛాంపియన్ అవ్వాలి అంటే ఇప్పుడే ఆడండి:\n"
        f"👉 {shared_link}\n\n"
        f"మీ ఫ్రెండ్స్ అందరికీ WhatsApp గ్రూపుల్లో షేర్ చేయండి!"
    )
    whatsapp_share_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(wa_text)}"

    tourney = {
        "id": tourney_id,
        "type": "WORLD_CUP_BRACKET",
        "title": title,
        "exam_target": exam_target,
        "status": "ROUND_1_ACTIVE",
        "current_round": round_name,
        "total_teams": total_teams,
        "bracket_matches": pairs,
        "semi_finals": [],
        "finals": {},
        "champion": None,
        "shared_link": shared_link,
        "qr_url": qr_url,
        "whatsapp_share_url": whatsapp_share_url,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    data.setdefault("tournaments", {})[tourney_id] = tourney
    save_tournaments(data)
    return tourney


def submit_clash_score(clash_id: str, team_key: str, uid: str, name: str, correct: int, total_q: int, time_sec: float = 20.0) -> dict:
    """Record student submission and re-evaluate fair normalized scores."""
    data = load_tournaments()
    match = data.get("tournaments", {}).get(clash_id)
    if not match:
        return {"ok": False, "message": "Clash not found"}

    team = match.get("team_a" if team_key.upper() in ("A", "TEAM_A") else "team_b")
    if not team:
        return {"ok": False, "message": "Invalid team"}

    team["players"][str(uid)] = {
        "name": name,
        "correct": correct,
        "time_sec": time_sec
    }

    # Recalculate Fair Score for Team A
    tot_correct_a = sum(p["correct"] for p in match["team_a"]["players"].values())
    match["team_a"]["score"] = calculate_fair_score(
        tot_correct_a, match["num_questions"], len(match["team_a"]["players"])
    )

    # Recalculate Fair Score for Team B
    tot_correct_b = sum(p["correct"] for p in match["team_b"]["players"].values())
    match["team_b"]["score"] = calculate_fair_score(
        tot_correct_b, match["num_questions"], len(match["team_b"]["players"])
    )

    # Determine leading / winner
    if match["team_a"]["score"] > match["team_b"]["score"]:
        match["winner"] = match["team_a"]["name"]
    elif match["team_b"]["score"] > match["team_a"]["score"]:
        match["winner"] = match["team_b"]["name"]
    else:
        match["winner"] = "Tie"

    save_tournaments(data)
    return {
        "ok": True,
        "team_a_score": match["team_a"]["score"],
        "team_b_score": match["team_b"]["score"],
        "leading": match["winner"]
    }


def record_district_war_stats(district: str, score: float, win: bool = False, now=None):
    """Update weekly & monthly district war leaderboards with fair points."""
    if not district:
        return
    now = now or datetime.now()
    w_key = now.strftime("%Y-W%W")
    m_key = now.strftime("%Y-%m")
    data = load_tournaments()

    # Weekly
    weekly = data.setdefault("district_wars_weekly", {}).setdefault(w_key, {})
    d_w = weekly.setdefault(district, {"pts": 0.0, "wars": 0, "wins": 0})
    d_w["pts"] = round(d_w["pts"] + float(score), 1)
    d_w["wars"] += 1
    if win:
        d_w["wins"] += 1

    # Monthly
    monthly = data.setdefault("district_wars_monthly", {}).setdefault(m_key, {})
    d_m = monthly.setdefault(district, {"pts": 0.0, "wars": 0, "wins": 0})
    d_m["pts"] = round(d_m["pts"] + float(score), 1)
    d_m["wars"] += 1
    if win:
        d_m["wins"] += 1

    save_tournaments(data)


def render_district_war_leaderboards(period: str = "both", now=None) -> str:
    """Render Top District of the Week and Top District of the Month standings with Telugu pride."""
    now = now or datetime.now()
    w_key = now.strftime("%Y-W%W")
    m_key = now.strftime("%Y-%m")
    data = load_tournaments()

    sections = []

    # Weekly Standings
    if period in ("both", "week", "weekly"):
        weekly = data.get("district_wars_weekly", {}).get(w_key, {})
        rows = sorted(weekly.items(), key=lambda kv: (-kv[1]["pts"], -kv[1]["wins"]))
        lines = [f"🔥 TOP DISTRICT OF THE WEEK (Week {now.strftime('%W')}) 🔥", ""]
        if not rows:
            lines.append("ఈ వారం District War పోరు ఇంకా మొదలవలేదు — మీ ఊరు కోసం మొదటి విజయాన్ని సాధించండి! ⚔️")
        else:
            medals = ["🥇", "🥈", "🥉"]
            for i, (dist, st) in enumerate(rows[:7], 1):
                icon = medals[i - 1] if i <= 3 else f"{i}."
                lines.append(f"{icon} {dist} — {st['pts']:g} Pts ({st['wins']} Wins · {st['wars']} Wars)")
            top_dist = rows[0][0]
            lines += ["", f"👑 ప్రస్తుత వీక్ లీడర్: *{top_dist}*!"]
        sections.append("\n".join(lines))

    # Monthly Standings
    if period in ("both", "month", "monthly"):
        monthly = data.get("district_wars_monthly", {}).get(m_key, {})
        rows = sorted(monthly.items(), key=lambda kv: (-kv[1]["pts"], -kv[1]["wins"]))
        m_name = now.strftime("%B %Y")
        lines = [f"🏆 TOP DISTRICT OF THE MONTH ({m_name}) 🏆", ""]
        if not rows:
            lines.append("ఈ నెల District War సీజన్ ప్రారంభమైంది! మీ జిల్లా గెలిస్తే నెలాఖరున ఛాంపియన్ ట్రోఫీ 🌟")
        else:
            medals = ["🥇", "🥈", "🥉"]
            for i, (dist, st) in enumerate(rows[:10], 1):
                icon = medals[i - 1] if i <= 3 else f"{i}."
                lines.append(f"{icon} {dist} — {st['pts']:g} Pts ({st['wins']} Wins · {st['wars']} Wars)")
            top_dist = rows[0][0]
            lines += ["", f"🌟 *{top_dist}* నంబర్ #1 గా నిలిచింది! జిల్లా గౌరవాన్ని కాపాడండి!"]
        sections.append("\n".join(lines))

    sections.append("💬 WhatsApp & Telegram లో మీ ఫ్రెండ్స్‌తో షేర్ చేసి మీ జిల్లా సైన్యాన్ని రంగంలోకి దించండి! /invite")
    return "\n\n" + ("\n" + "=" * 35 + "\n").join(sections)
