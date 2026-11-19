# -*- coding: utf-8 -*-
"""Собрать офлайн-страницу для телефона из заметок в notes/."""
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTES = HERE / "notes"
OUT = HERE / "index.html"

ORDER = [
    ("00", "00_Как_открыть.md", "Состав", False),
    ("01", "01_Микроэкономика.md", "Микро", True),
    ("02", "02_ИТЭ.md", "ИТЭ", True),
    ("03", "03_Макроэкономика.md", "Макро", True),
    ("04", "04_Статистика.md", "Статистика", True),
    ("05", "05_Бизнес_планы.md", "Планы", True),
]


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def md_blocks(src: str):
    """Разбить markdown на (heading_level, title, html_body). level 1 — страница."""
    lines = src.replace("\r\n", "\n").split("\n")
    sections = []
    title = None
    level = 1
    buf = []
    i = 0

    def flush():
        nonlocal buf, title, level
        if title is None and not buf:
            return
        sections.append((level, title, "\n".join(buf)))
        buf = []

    def push(block: str):
        buf.append(block)

    while i < len(lines):
        line = lines[i]
        if line.startswith("# "):
            flush()
            title = line[2:].strip()
            level = 1
            i += 1
            continue
        if line.startswith("## "):
            flush()
            title = line[3:].strip()
            level = 2
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*-+", lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            header = [c.strip() for c in rows[0].strip("|").split("|")]
            body_rows = rows[2:]
            thead = "".join(f"<th>{inline(c)}</th>" for c in header)
            tbody = []
            for r in body_rows:
                cells = [c.strip() for c in r.strip("|").split("|")]
                tbody.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            push("<div class='tw'><table><thead><tr>" + thead + "</tr></thead><tbody>" + "".join(tbody) + "</tbody></table></div>")
            continue
        if line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                raw = lines[i][2:].strip()
                items.append((raw, f"<li>{inline(raw)}</li>"))
                i += 1
            push("<ul>" + "".join(h for _, h in items) + "</ul>")
            continue
        if re.match(r"^\d+\. ", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                raw = re.sub(r"^\d+\. ", "", lines[i]).strip()
                items.append(f"<li>{inline(raw)}</li>")
                i += 1
            push("<ol>" + "".join(items) + "</ol>")
            continue
        if not line.strip():
            i += 1
            continue
        para = [line.strip()]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not lines[i].startswith(("#", "|", "- "))
            and not re.match(r"^\d+\. ", lines[i])
        ):
            para.append(lines[i].strip())
            i += 1
        raw = " ".join(para)
        push(f"<p>{inline(raw)}</p>")
    flush()
    return sections


def plain_chunks(body_html: str):
    """Тексты абзацев и пунктов списка, без таблиц."""
    chunks = []
    for m in re.finditer(r"<p>(.*?)</p>", body_html, flags=re.S):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = html.unescape(text).strip()
        if text:
            chunks.append(text)
    for m in re.finditer(r"<li>(.*?)</li>", body_html, flags=re.S):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = html.unescape(text).strip()
        if text:
            chunks.append(text)
    return chunks


def is_defense(title: str) -> bool:
    t = (title or "").lower()
    return t.startswith("запомнить") or "числа защиты" in t or t.startswith("формулы")


def main():
    articles = []
    cards = []
    formulas = []
    for sid, name, label, drill in ORDER:
        src = (NOTES / name).read_text(encoding="utf-8")
        sections = md_blocks(src)
        parts = []
        page_title = ""
        intro = ""
        for level, title, body in sections:
            if level == 1:
                page_title = title or label
                intro = body
                continue
            defense = is_defense(title or "")
            cls = "sec defense" if defense else "sec"
            opened = " open" if defense else ""
            parts.append(
                f"<details class='{cls}'{opened}>"
                f"<summary>{inline(title or '')}</summary>"
                f"<div class='sec-body'>{body}</div></details>"
            )
            if drill:
                for text in plain_chunks(body):
                    if len(text) < 8 or len(text) > 520:
                        continue
                    priority = defense or ("=" in text)
                    if not priority and len(text) < 40:
                        continue
                    if not priority and len(text) > 280:
                        continue
                    cards.append(
                        {
                            "id": f"{sid}-{len(cards)}",
                            "subject": sid,
                            "label": label,
                            "heading": title or page_title,
                            "text": text,
                            "priority": priority,
                            "defense": defense,
                        }
                    )
                    if "=" in text and len(text) <= 220:
                        formulas.append({"subject": sid, "label": label, "text": text})
        articles.append(
            f"<article id='s{sid}' data-subject='{sid}'>"
            f"<h1>{inline(page_title)}</h1>"
            + (f"<div class='intro'>{intro}</div>" if intro else "")
            + "\n".join(parts)
            + "</article>"
        )

    # Уникальные формулы, порядок сохраняем.
    seen = set()
    formula_rows = []
    for item in formulas:
        key = (item["subject"], item["text"])
        if key in seen:
            continue
        seen.add(key)
        formula_rows.append(item)

    data = {"cards": cards, "formulas": formula_rows}
    page = PAGE.replace("__ARTICLES__", "\n".join(articles)).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    )
    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT} {OUT.stat().st_size} bytes, cards {len(cards)}, formulas {len(formula_rows)}")


PAGE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#f3efe6">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Учёба">
<title>Учёба. Конспект к защите</title>
<style>
:root {
  --bg: #f3efe6;
  --ink: #1c1915;
  --muted: #6d6458;
  --card: #fffdf8;
  --line: #e3d9c8;
  --accent: #0f5c4c;
  --accent-ink: #f4fbf7;
  --warn: #8a3d12;
  --chip: #efe6d6;
  --shadow: 0 10px 30px rgba(60, 42, 16, 0.08);
  color-scheme: light;
}
:root[data-theme="dark"] {
  --bg: #141311;
  --ink: #f4efe6;
  --muted: #b3a898;
  --card: #221f1b;
  --line: #3a342c;
  --accent: #8fd0b8;
  --accent-ink: #10241c;
  --warn: #f0b089;
  --chip: #2c2823;
  --shadow: none;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font: 17px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--ink);
  padding-bottom: calc(72px + env(safe-area-inset-bottom));
}
header {
  position: sticky; top: 0; z-index: 5;
  background: color-mix(in srgb, var(--bg) 92%, transparent);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--line);
  padding: 10px 14px 8px;
}
.top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
h1.brand { font-size: 1.05rem; margin: 0; letter-spacing: -0.02em; }
.iconbtn, button, .chip {
  font: inherit; color: inherit; background: var(--card);
  border: 1px solid var(--line); border-radius: 999px;
}
.iconbtn { padding: 6px 10px; }
.search {
  width: 100%; margin-top: 8px; padding: 10px 12px; border-radius: 12px;
  border: 1px solid var(--line); background: var(--card); color: inherit; font: inherit;
}
.chips { display: flex; gap: 8px; overflow-x: auto; padding: 8px 0 2px; scrollbar-width: none; }
.chips::-webkit-scrollbar { display: none; }
.chip { padding: 7px 12px; white-space: nowrap; }
.chip[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink); border-color: transparent; }
main { max-width: 42rem; margin: 0 auto; padding: 12px 14px 24px; }
.panel { display: none; }
.panel.active { display: block; }
.lead { color: var(--muted); margin: 0 0 12px; }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 18px;
  padding: 16px; box-shadow: var(--shadow); margin: 12px 0;
}
.kicker { color: var(--muted); font-size: 0.82rem; margin: 0 0 8px; }
.prompt { font-size: 1.12rem; margin: 0; }
.full { margin: 12px 0 0; }
.row { display: flex; gap: 8px; margin-top: 14px; }
#shift-card .row {
  position: sticky;
  bottom: calc(62px + env(safe-area-inset-bottom));
  background: var(--card);
  margin: 12px -16px -16px;
  padding: 10px 16px 14px;
  border-top: 1px solid var(--line);
  border-radius: 0 0 18px 18px;
}
.row button, .primary {
  flex: 1; padding: 12px 10px; border-radius: 12px; font-weight: 650;
}
.primary { width: 100%; background: var(--accent); color: var(--accent-ink); border: 0; padding: 14px; border-radius: 14px; font: inherit; font-weight: 700; }
.ghost { background: transparent; }
article { display: none; }
article.active { display: block; }
article h1 { font-size: 1.35rem; line-height: 1.25; margin: 8px 0 12px; }
details { background: var(--card); border: 1px solid var(--line); border-radius: 14px; margin: 8px 0; padding: 0 12px 2px; }
details.defense { border-color: var(--accent); }
summary { cursor: pointer; font-weight: 680; padding: 12px 0; }
.sec-body p { margin: 0.55rem 0; }
ul, ol { margin: 0.35rem 0 0.7rem; padding-left: 1.15rem; }
li { margin: 0.28rem 0; }
code { font-family: ui-monospace, Consolas, monospace; font-size: 0.92em; background: var(--chip); padding: 0 0.25em; border-radius: 4px; }
.tw { overflow-x: auto; margin: 0.5rem 0 0.8rem; }
table { border-collapse: collapse; width: max-content; min-width: 100%; font-size: 15px; }
td, th { border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: var(--chip); }
.formula { padding: 10px 0; border-bottom: 1px solid var(--line); }
.formula:last-child { border-bottom: 0; }
nav.dock {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 6;
  display: flex; gap: 6px; justify-content: space-around;
  padding: 8px 10px calc(8px + env(safe-area-inset-bottom));
  background: color-mix(in srgb, var(--bg) 94%, transparent);
  border-top: 1px solid var(--line);
  backdrop-filter: blur(10px);
}
nav.dock button { flex: 1; padding: 10px 6px; border-radius: 12px; }
nav.dock button[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink); border-color: transparent; }
.stat { display: flex; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 0.92rem; }
.hide, [hidden] { display: none !important; }
</style>
</head>
<body>
<header>
  <div class="top">
    <h1 class="brand">Учёба к защите</h1>
    <button class="iconbtn" id="theme" type="button">Тема</button>
  </div>
  <div class="chips" id="subjects" hidden></div>
  <input class="search" id="search" type="search" placeholder="Поиск по конспекту" hidden enterkeyhint="search">
</header>
<main>
  <section class="panel active" id="view-shift">
    <p class="lead">Один заход на смене: 6 карточек. Сначала то, что помечено для защиты. Числа на лицевой стороне закрыты.</p>
    <div class="card" id="shift-home">
      <p class="stat"><span id="due-label">Карточки</span><span id="known-label"></span></p>
      <div class="chips" id="shift-subjects"></div>
      <button class="primary" id="start" type="button">Начать смену</button>
    </div>
    <div class="card hide" id="shift-card">
      <p class="kicker" id="card-kicker"></p>
      <p class="prompt" id="card-front"></p>
      <p class="full hide" id="card-back"></p>
      <div class="row">
        <button type="button" id="reveal">Показать</button>
        <button type="button" id="again" class="hide">Снова</button>
        <button type="button" id="know" class="hide">Знаю</button>
      </div>
    </div>
    <div class="card hide" id="shift-done">
      <p class="prompt" id="done-text"></p>
      <button class="primary" id="again-session" type="button">Ещё шесть</button>
    </div>
  </section>
  <section class="panel" id="view-notes">
    __ARTICLES__
  </section>
  <section class="panel" id="view-formulas">
    <p class="lead">Строки с равенством из конспектов. Удобно открыть перед защитой.</p>
    <div id="formula-list"></div>
  </section>
</main>
<nav class="dock">
  <button type="button" data-view="shift" aria-pressed="true">Смена</button>
  <button type="button" data-view="notes">Конспект</button>
  <button type="button" data-view="formulas">Формулы</button>
</nav>
<script>
const DATA = __DATA__;
const SUBJECTS = [
  ["01", "Микро"],
  ["02", "ИТЭ"],
  ["03", "Макро"],
  ["04", "Статистика"],
  ["05", "Планы"],
  ["00", "Состав"]
];
const KEY = "ucheba-phone-v1";
const state = Object.assign({ known: {}, again: {}, theme: "" }, JSON.parse(localStorage.getItem(KEY) || "{}"));
function save() { localStorage.setItem(KEY, JSON.stringify(state)); }
function blank(text) {
  return text.replace(/\d+(?:[.,]\d+)?/g, "…");
}
const byId = Object.fromEntries(DATA.cards.map(c => [c.id, c]));

const subjectsEl = document.getElementById("subjects");
const shiftSubjects = document.getElementById("shift-subjects");
let noteSubject = "01";
let shiftSubject = "all";

function chip(parent, id, label, pressed, onpress) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "chip";
  b.textContent = label;
  b.setAttribute("aria-pressed", pressed ? "true" : "false");
  b.onclick = () => onpress(id);
  parent.appendChild(b);
  return b;
}
function paintChips(parent, current, onpress, withAll) {
  parent.innerHTML = "";
  const list = withAll ? SUBJECTS.filter(([id]) => id !== "00") : SUBJECTS;
  if (withAll) chip(parent, "all", "Все", current === "all", onpress);
  list.forEach(([id, label]) => chip(parent, id, label, current === id, onpress));
}
function showNotes(id) {
  noteSubject = id;
  document.querySelectorAll("article").forEach(a => a.classList.toggle("active", a.dataset.subject === id));
  paintChips(subjectsEl, id, showNotes, false);
  applySearch();
}
function setShiftSubject(id) {
  shiftSubject = id;
  paintChips(shiftSubjects, id, setShiftSubject, true);
  updateStats();
}

document.querySelectorAll("nav.dock button").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll("nav.dock button").forEach(b => b.setAttribute("aria-pressed", "false"));
    btn.setAttribute("aria-pressed", "true");
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    document.getElementById("view-" + btn.dataset.view).classList.add("active");
    const notes = btn.dataset.view === "notes";
    subjectsEl.hidden = !notes;
    document.getElementById("search").hidden = !notes;
  };
});

function pool() {
  return DATA.cards.filter(c => shiftSubject === "all" || c.subject === shiftSubject);
}
function updateStats() {
  const cards = pool();
  const known = cards.filter(c => state.known[c.id]).length;
  const again = cards.filter(c => state.again[c.id] && !state.known[c.id]).length;
  document.getElementById("due-label").textContent = cards.length + " карточек";
  document.getElementById("known-label").textContent = "знаю " + known + (again ? " · снова " + again : "");
}
function pickQueue() {
  const cards = pool();
  const again = cards.filter(c => state.again[c.id] && !state.known[c.id]);
  const defense = cards.filter(c => c.defense && !state.known[c.id] && !state.again[c.id]);
  const freshP = cards.filter(c => c.priority && !c.defense && !state.known[c.id] && !state.again[c.id]);
  const fresh = cards.filter(c => !c.priority && !state.known[c.id] && !state.again[c.id]);
  const rest = cards.filter(c => state.known[c.id]);
  const order = again.concat(defense, freshP, fresh, rest);
  return order.slice(0, 6);
}

let queue = [];
let step = 0;
function showCard() {
  const card = queue[step];
  document.getElementById("card-kicker").textContent = card.label + " · " + card.heading + " · " + (step + 1) + "/" + queue.length;
  document.getElementById("card-front").textContent = blank(card.text);
  const back = document.getElementById("card-back");
  back.textContent = card.text;
  back.classList.add("hide");
  document.getElementById("reveal").classList.remove("hide");
  document.getElementById("again").classList.add("hide");
  document.getElementById("know").classList.add("hide");
}
function startSession() {
  queue = pickQueue();
  step = 0;
  document.getElementById("shift-home").classList.add("hide");
  document.getElementById("shift-done").classList.add("hide");
  document.querySelector("#view-shift .lead").classList.add("hide");
  document.getElementById("shift-card").classList.remove("hide");
  if (!queue.length) {
    finish(0, 0);
    return;
  }
  showCard();
}
function finish(knownNow, total) {
  document.getElementById("shift-card").classList.add("hide");
  document.querySelector("#view-shift .lead").classList.remove("hide");
  document.getElementById("shift-done").classList.remove("hide");
  document.getElementById("done-text").textContent = total
    ? ("Смена закрыта. Отмечено «знаю»: " + knownNow + " из " + total + ".")
    : "В этом предмете карточек нет.";
  updateStats();
}
document.getElementById("start").onclick = startSession;
document.getElementById("again-session").onclick = () => {
  document.getElementById("shift-done").classList.add("hide");
  document.getElementById("shift-home").classList.remove("hide");
  startSession();
};
document.getElementById("reveal").onclick = () => {
  document.getElementById("card-back").classList.remove("hide");
  document.getElementById("reveal").classList.add("hide");
  document.getElementById("again").classList.remove("hide");
  document.getElementById("know").classList.remove("hide");
};
function grade(know) {
  const id = queue[step].id;
  if (know) { state.known[id] = true; delete state.again[id]; }
  else { delete state.known[id]; state.again[id] = true; }
  save();
  step += 1;
  if (step >= queue.length) {
    const knownNow = queue.filter(id => state.known[id]).length;
    finish(knownNow, queue.length);
  } else showCard();
}
document.getElementById("again").onclick = () => grade(false);
document.getElementById("know").onclick = () => grade(true);

function applySearch() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const article = document.querySelector("article.active");
  if (!article) return;
  article.querySelectorAll("details").forEach(d => {
    const text = d.textContent.toLowerCase();
    const hit = !q || text.includes(q);
    d.classList.toggle("hide", !hit);
    if (q && hit) d.open = true;
  });
}
document.getElementById("search").addEventListener("input", applySearch);

const formulaList = document.getElementById("formula-list");
SUBJECTS.forEach(([id, label]) => {
  const rows = DATA.formulas.filter(f => f.subject === id);
  if (!rows.length) return;
  const box = document.createElement("div");
  box.className = "card";
  const h = document.createElement("p");
  h.className = "kicker";
  h.textContent = label;
  box.appendChild(h);
  rows.forEach(f => {
    const p = document.createElement("p");
    p.className = "formula";
    p.textContent = f.text;
    box.appendChild(p);
  });
  formulaList.appendChild(box);
});

function applyTheme() {
  if (state.theme) document.documentElement.dataset.theme = state.theme;
  else document.documentElement.removeAttribute("data-theme");
}
document.getElementById("theme").onclick = () => {
  state.theme = document.documentElement.dataset.theme === "dark" ? "" : "dark";
  applyTheme();
  save();
};
applyTheme();
paintChips(shiftSubjects, "all", setShiftSubject, true);
showNotes("01");
updateStats();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
