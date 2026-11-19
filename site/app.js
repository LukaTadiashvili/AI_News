/* AI News — static app. Data comes from data/*.json, written by the pipeline. */
"use strict";

const TZ = "Asia/Tbilisi";
const MONTHS = ["იანვარი", "თებერვალი", "მარტი", "აპრილი", "მაისი", "ივნისი", "ივლისი", "აგვისტო", "სექტემბერი", "ოქტომბერი", "ნოემბერი", "დეკემბერი"];
const DAYS = ["კვირა", "ორშაბათი", "სამშაბათი", "ოთხშაბათი", "ხუთშაბათი", "პარასკევი", "შაბათი"];
const TOPICS = {
  analytics: "ანალიტიკა", automation: "ავტომატიზაცია", video: "ვიდეო", retail: "რითეილი",
  sales: "გაყიდვები", marketing: "მარკეტინგი", support: "მომსახურება", visuals: "პრეზენტაცია",
  nocode: "კოდის გარეშე", agents: "აგენტები", business: "ბიზნესი",
};
const CAT = { models: "მოდელები", tools: "ინსტრუმენტები", community: "საზოგადოება" };

const S = { items: [], byId: {}, weekly: [], board: [], glossary: {}, meta: {}, filter: {}, loadedAt: 0 };
const $ = (sel) => document.querySelector(sel);
const view = $("#view");

// ---------------------------------------------------------------- storage (per device)
const store = {
  get(k, d) { try { const v = localStorage.getItem("ainews:" + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("ainews:" + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
let readSet = new Set(store.get("read", []));
let savedList = store.get("saved", []);
const prevVisit = (() => {
  let p = null;
  try { p = sessionStorage.getItem("ainews:prev"); } catch { /* ignore */ }
  if (p === null) {
    p = store.get("lastVisit", 0);
    try { sessionStorage.setItem("ainews:prev", String(p)); } catch { /* ignore */ }
  }
  store.set("lastVisit", Date.now());
  return Number(p) || 0;
})();

function markRead(id) {
  if (readSet.has(id)) return;
  readSet.add(id);
  store.set("read", [...readSet].slice(-800));
}
function toggleSave(id) {
  savedList = savedList.includes(id) ? savedList.filter((x) => x !== id) : [id, ...savedList];
  store.set("saved", savedList);
  return savedList.includes(id);
}

// ---------------------------------------------------------------- helpers
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : "#"; }
// `code` spans from the model, after escaping
function rich(s) { return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>"); }

function tbParts(d) {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, weekday: "short" });
  const o = Object.fromEntries(f.formatToParts(d).map((p) => [p.type, p.value]));
  return { y: +o.year, m: +o.month, d: +o.day, hh: o.hour === "24" ? "00" : o.hour, mm: o.minute, key: `${o.year}-${o.month}-${o.day}` };
}
function dayKey(iso) { return tbParts(new Date(iso)).key; }
function dayLabel(key) {
  const today = tbParts(new Date()).key;
  const yest = tbParts(new Date(Date.now() - 864e5)).key;
  if (key === today) return "დღეს";
  if (key === yest) return "გუშინ";
  const [y, m, d] = key.split("-").map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay();
  return `${DAYS[wd]}, ${d} ${MONTHS[m - 1]}`;
}
function timeLabel(iso) {
  const d = new Date(iso);
  const mins = Math.round((Date.now() - d) / 60000);
  if (mins < 60) return `${Math.max(1, mins)} წთ წინ`;
  if (mins < 24 * 60) return `${Math.round(mins / 60)} სთ წინ`;
  const p = tbParts(d);
  return `${p.d} ${MONTHS[p.m - 1].slice(0, 3)}, ${p.hh}:${p.mm}`;
}
function readTime(sec) { sec = Number(sec) || 40; return sec < 60 ? `${sec} წმ` : `${Math.round(sec / 60)} წთ`; }
function groupByDay(items, field = "added") {
  const g = new Map();
  for (const it of items) {
    const k = dayKey(it[field] || it.added);
    if (!g.has(k)) g.set(k, []);
    g.get(k).push(it);
  }
  return g;
}

// ---------------------------------------------------------------- data
async function getJSON(path, fallback) {
  try {
    const r = await fetch(path + "?t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch { return fallback; }
}
async function load() {
  const [items, weekly, board, glossary, meta] = await Promise.all([
    getJSON("data/items.json", []), getJSON("data/weekly.json", []), getJSON("data/leaderboard.json", []),
    getJSON("data/glossary.json", {}), getJSON("data/meta.json", {}),
  ]);
  S.items = Array.isArray(items) ? items : [];
  S.byId = Object.fromEntries(S.items.map((i) => [i.id, i]));
  S.weekly = Array.isArray(weekly) ? weekly : [];
  S.board = Array.isArray(board) ? board : [];
  S.glossary = glossary && typeof glossary === "object" ? glossary : {};
  S.meta = meta || {};
  S.loadedAt = Date.now();
}

// ---------------------------------------------------------------- cards
function chips(it) {
  let h = "";
  if (it.big) h += '<span class="chip big">🔴 მთავარი</span>';
  if (it.section === "community") h += `<span class="chip community">${esc(TOPICS[it.topic] || "საზოგადოება")}</span>`;
  else h += `<span class="chip ${it.category === "tools" ? "tools" : "models"}">${CAT[it.category] || "მოდელები"}</span>`;
  return h;
}
function card(it) {
  const cls = ["card", it.big ? "big" : "", readSet.has(it.id) ? "read" : ""].join(" ");
  if (it.section === "community") {
    const score = it.score ? `▲ ${it.score >= 1000 ? (it.score / 1000).toFixed(1) + "K" : it.score}` : timeLabel(it.added);
    return `<a class="${cls}" href="#item-${esc(it.id)}">
      <div class="meta">${chips(it)}<span>${esc(it.source)}</span><span class="t">${esc(score)}</span></div>
      <h3>${esc(it.title_ka)}</h3>
      ${it.built_ka ? `<p class="built"><b>რა ააწყო:</b> ${esc(it.built_ka)}</p>` : ""}
      ${it.tools?.length ? `<div class="toolrow">${it.tools.map((t) => `<span class="tool">${esc(t)}</span>`).join("")}</div>` : ""}
      ${it.quote_ka ? `<p class="quote">💬 ${esc(it.quote_ka)}</p>` : ""}
      ${it.use_ka ? `<div class="use"><b>💼 შენთვის:</b> ${esc(it.use_ka)}</div>` : ""}
    </a>`;
  }
  return `<a class="${cls}" href="#item-${esc(it.id)}">
    <div class="meta">${chips(it)}<span>${esc(it.product || it.company)}</span><span class="t">${esc(timeLabel(it.added))}</span></div>
    <h3>${esc(it.title_ka)}</h3>
    ${it.bullets?.length ? `<ul class="bul">${it.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}
    ${it.why_ka ? `<div class="why"><b>რატომ მნიშვნელოვანი:</b> ${esc(it.why_ka)}</div>` : ""}
    ${it.use_ka ? `<div class="use"><b>💼 შენთვის:</b> ${esc(it.use_ka)}</div>` : ""}
    <div class="foot"><span>კითხვა ${readTime(it.read_seconds)}</span><span>${esc(it.domain)}</span></div>
  </a>`;
}
function feedByDay(items, empty) {
  if (!items.length) return empty;
  let h = "";
  for (const [k, list] of groupByDay(items)) {
    h += `<div class="day">${esc(dayLabel(k))}</div>` + list.map(card).join("");
  }
  return h;
}
function emptyState(title, text) { return `<div class="empty"><strong>${esc(title)}</strong>${esc(text)}</div>`; }
const NO_DATA = () => emptyState("სიახლეები ჯერ არ არის", S.meta.updated
  ? "ამ განყოფილებაში ჯერ არაფერია. სიახლეები დღეში 3-ჯერ მოწმდება: 09:00, 13:00 და 20:00."
  : "პირველი განახლება მალე მოვა. სიახლეები დღეში 3-ჯერ მოწმდება: 09:00, 13:00 და 20:00.");

// ---------------------------------------------------------------- views
const news = () => S.items.filter((i) => i.section === "news");
const comm = () => S.items.filter((i) => i.section === "community");
const byImportance = (a, b) => (b.importance || 0) - (a.importance || 0) || (b.added > a.added ? 1 : -1);

function missed() {
  if (!prevVisit) return [];
  return S.items.filter((i) => new Date(i.added).getTime() > prevVisit && !readSet.has(i.id));
}

function vToday() {
  const today = tbParts(new Date()).key;
  const todayNews = news().filter((i) => dayKey(i.added) === today).sort(byImportance);
  const todayComm = comm().filter((i) => dayKey(i.added) === today).sort(byImportance).slice(0, 3);
  const secs = todayNews.reduce((s, i) => s + (Number(i.read_seconds) || 40), 0);
  let h = "";
  const m = missed();
  if (m.length >= 3 && Date.now() - prevVisit > 20 * 3600e3) {
    h += `<a class="catchup" href="#catchup"><span>⏪</span><span>გამოგრჩა <b>${m.length}</b> სიახლე</span><span>დამეწიე →</span></a>`;
  }
  h += `<div class="digest"><span class="n">${todayNews.length}</span><p><strong>დღის მთავარი</strong><br>${
    todayNews.length ? `${todayNews.length} სიახლე · კითხვას ${Math.max(1, Math.round(secs / 60))} წუთი სჭირდება` : "დღეს ჯერ დიდი სიახლე არ ყოფილა"}</p></div>`;
  h += todayNews.map(card).join("");
  if (todayComm.length) {
    h += `<div class="day">👥 დღის იდეები საზოგადოებიდან</div>` + todayComm.map(card).join("");
  }
  const earlier = news().filter((i) => dayKey(i.added) !== today).slice(0, 15);
  if (earlier.length) h += feedByDay(earlier, "");
  if (!S.items.length) h += NO_DATA();
  return h;
}

function vCategory(cat) {
  let list = news().filter((i) => i.category === cat);
  let h = "";
  if (cat === "tools") {
    const products = [...new Set(list.map((i) => i.product).filter(Boolean))];
    if (products.length > 1) {
      const f = S.filter.tools || "";
      h += `<div class="chips">${["", ...products].map((p) => `<button class="fchip${p === f ? " on" : ""}" data-filter="tools" data-val="${esc(p)}" type="button">${esc(p || "ყველა")}</button>`).join("")}</div>`;
      if (f) list = list.filter((i) => i.product === f);
    }
  }
  return h + feedByDay(list, NO_DATA());
}

function vCommunity() {
  let list = comm();
  const present = Object.keys(TOPICS).filter((t) => list.some((i) => i.topic === t));
  const f = S.filter.community || "";
  let h = `<p class="lead">რას აწყობენ ადამიანები AI-ით: Reddit, Hacker News, Product Hunt, GitHub. ეს არაოფიციალური, ადამიანების გამოცდილებაა.</p>`;
  if (present.length) {
    h += `<div class="chips">${["", ...present].map((t) => `<button class="fchip${t === f ? " on" : ""}" data-filter="community" data-val="${t}" type="button">${esc(TOPICS[t] || "ყველა")}</button>`).join("")}</div>`;
  }
  if (f) list = list.filter((i) => i.topic === f);
  return h + feedByDay(list, NO_DATA());
}

function vSaved() {
  const list = savedList.map((id) => S.byId[id]).filter(Boolean);
  return `<h2 class="section-title">შენახული</h2>` + (list.length ? list.map(card).join("")
    : emptyState("ჯერ არაფერი შეგინახავს", "სიახლის გახსნისას დააჭირე „🔖 შენახვა“ და აქ გამოჩნდება."));
}

function vCatchup() {
  const m = missed().sort(byImportance);
  let h = `<button class="back" type="button" data-back>← უკან</button><h2 class="section-title">⏪ დამეწიე</h2>`;
  if (!m.length) return h + emptyState("ყველაფერი წაკითხული გაქვს", "ბოლო ვიზიტის შემდეგ ახალი არაფერი გამოგრჩენია.");
  h += `<p class="lead">ბოლო ვიზიტის შემდეგ ${m.length} სიახლე. ყველაზე მნიშვნელოვანი ზემოთაა.</p>`;
  for (const [k, list] of groupByDay(m.sort((a, b) => (b.added > a.added ? 1 : -1)))) {
    h += `<div class="day">${esc(dayLabel(k))}</div>` + list.sort(byImportance).map((i) =>
      `<a class="row" href="#item-${esc(i.id)}"><strong>${i.big ? "🔴 " : ""}${esc(i.title_ka)}</strong><small>${esc(i.why_ka || i.built_ka || "")}</small></a>`).join("");
  }
  return h;
}

function vVersions() {
  const tools = news().filter((i) => i.category === "tools" && i.product);
  let h = `<button class="back" type="button" data-back>← უკან</button><h2 class="section-title">🧭 ვერსიების ისტორია</h2>`;
  if (!tools.length) return h + emptyState("ჯერ ცარიელია", "Claude Code-ის, Codex-ის, Cursor-ის და სხვა ინსტრუმენტების ახალი ვერსიები აქ დაგროვდება.");
  const groups = new Map();
  for (const i of tools) { if (!groups.has(i.product)) groups.set(i.product, []); groups.get(i.product).push(i); }
  for (const [p, list] of groups) {
    h += `<div class="day">${esc(p)}</div><div class="timeline">` + list.map((i) => {
      const pp = tbParts(new Date(i.added));
      return `<div class="tl"><a href="#item-${esc(i.id)}"><span class="v">${esc(i.version || i.title_ka)}</span><span class="d">${pp.d} ${MONTHS[pp.m - 1].slice(0, 3)}</span>
        ${i.bullets?.length ? `<ul class="bul">${i.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : `<small>${esc(i.title_ka)}</small>`}</a></div>`;
    }).join("") + "</div>";
  }
  return h;
}

function vLeaderboard() {
  let h = `<button class="back" type="button" data-back>← უკან</button><h2 class="section-title">🏆 მოდელების რეიტინგი</h2>
    <p class="lead">ახალი მოდელები, ახლიდან ძველისკენ. ცხრილი ავტომატურად ახლდება, როცა ახალი მოდელი გამოდის.</p>`;
  if (!S.board.length) return h + emptyState("ჯერ ცარიელია", "პირველი ახალი მოდელის გამოსვლისას აქ გამოჩნდება.");
  h += `<div class="table-wrap"><table><thead><tr><th>მოდელი</th><th>კონტექსტი</th><th>ფასი (შემ. / გამ.)</th><th>რაში ჯობია</th><th>სად</th></tr></thead><tbody>`;
  h += S.board.map((r) => `<tr><td>${S.byId[r.item] ? `<a href="#item-${esc(r.item)}">${esc(r.name)}</a>` : `<b>${esc(r.name)}</b>`}<br><small>${esc(r.company)} · ${esc(r.released)}</small></td>
    <td class="mono">${esc(r.context || "—")}</td><td class="mono">${esc(r.price_in || "—")}${r.price_out ? " / " + esc(r.price_out) : ""}</td>
    <td>${esc(r.best_for_ka || "—")}</td><td>${esc(r.access_ka || "—")}</td></tr>`).join("");
  return h + "</tbody></table></div>";
}

function vWeekly(weekId) {
  let h = `<button class="back" type="button" data-back>← უკან</button><h2 class="section-title">🗓 კვირის შეჯამება</h2>`;
  const weeks = weekId ? S.weekly.filter((w) => w.week === weekId) : S.weekly;
  if (!weeks.length) return h + emptyState("ჯერ ცარიელია", "პირველი შეჯამება კვირას, 20:00-ზე მოვა.");
  return h + weeks.map((w) => `<section class="week"><div class="lbl">${esc(w.date)} · ${esc(w.count || "")} სიახლე</div>
    <h3>${esc(w.title_ka)}</h3><p class="lead" style="margin:0">${esc(w.intro_ka)}</p>
    <ol>${w.top.map((t) => { const it = S.byId[t.id]; return it ? `<li><a href="#item-${esc(t.id)}">${esc(it.title_ka)}</a><small>${esc(t.line_ka)}</small></li>` : ""; }).join("")}</ol></section>`).join("");
}

function vGlossary() {
  const words = Object.keys(S.glossary).sort((a, b) => a.localeCompare(b));
  let h = `<button class="back" type="button" data-back>← უკან</button><h2 class="section-title">📖 ტერმინების ლექსიკონი</h2>`;
  if (!words.length) return h + emptyState("ჯერ ცარიელია", "ყოველი სიახლე ერთ ტერმინს ხსნის. აქ ყველა დაგროვდება.");
  return h + `<div class="gloss">${words.map((w) => `<div><b>${esc(w)}</b><span>${esc(S.glossary[w])}</span></div>`).join("")}</div>`;
}

function vAbout() {
  const upd = S.meta.updated ? `${dayLabel(dayKey(S.meta.updated))}, ${tbParts(new Date(S.meta.updated)).hh}:${tbParts(new Date(S.meta.updated)).mm}` : "ჯერ არ განახლებულა";
  return `<button class="back" type="button" data-back>← უკან</button><h2 class="section-title">🔔 შეტყობინებები და წყაროები</h2>
  <div class="info"><h3>შეტყობინებები (ntfy)</h3><ul>
    <li>🔄 <b>განახლება</b>: დღეში 3-ჯერ, 09:00, 13:00 და 20:00-ზე.</li>
    <li>🔴 <b>მთავარი სიახლე</b>: დიდ გამოშვებაზე ცალკე შეტყობინება, უახლოეს განახლებაზე.</li>
    <li>📰 <b>დღის შეჯამება</b>: ყოველდღე 13:00-ზე.</li>
    <li>🗓 <b>კვირის შეჯამება</b>: კვირას 20:00-ზე.</li>
    <li>🌙 <b>ჩუმი საათები</b>: 00:00–09:00. ღამის სიახლე დილის 9-ზე მოვა.</li></ul></div>
  <div class="info"><h3>ოფიციალური წყაროები</h3><p>OpenAI, Anthropic, Claude, Google AI, DeepMind, Meta AI, xAI, Mistral, Claude Code, Codex, Gemini CLI, Cursor, Power BI და Power Automate ბლოგები, TechCrunch და The Verge (მხოლოდ დადასტურებული გამოშვებები).</p></div>
  <div class="info"><h3>საზოგადოება</h3><p>Reddit (ანალიტიკის, ავტომატიზაციის, ვიდეოს, რითეილის, გაყიდვების, მარკეტინგის და AI საზოგადოებები), Hacker News, Product Hunt, GitHub Trending.</p></div>
  <div class="info"><h3>ბოლო განახლება</h3><p>${esc(upd)} · სულ ${S.items.length} სიახლე</p></div>`;
}

// ---------------------------------------------------------------- detail
function glossify(html, used) {
  // underline known terms once per page; tap shows the definition
  const words = Object.keys(S.glossary).filter((w) => w.length > 2).sort((a, b) => b.length - a.length);
  for (const w of words) {
    if (used.has(w)) continue;
    const ew = esc(w).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // Georgian words take endings (ტოკენი -> ტოკენის), so allow a short suffix
    const stem = /[ა-ჿ]$/.test(w) && w.length > 4 ? ew.slice(0, -1) : ew;
    const re = new RegExp(`(^|[^\\p{L}\\p{N}>])(${stem}[\\u10D0-\\u10FF]{0,4})(?=[^\\p{L}\\p{N}]|$)(?![^<]*>)`, "iu");
    if (re.test(html)) {
      html = html.replace(re, (m, pre, word) => `${pre}<button type="button" class="gl" data-term="${esc(w)}">${word}</button>`);
      used.add(w);
    }
  }
  return html;
}

function vItem(id) {
  const it = S.byId[id];
  if (!it) return `<button class="back" type="button" data-back>← უკან</button>` + emptyState("სიახლე ვერ მოიძებნა", "შესაძლოა ძველია და უკვე წაიშალა.");
  markRead(id);
  const used = new Set();
  const g = (s) => glossify(rich(s), used);
  const saved = savedList.includes(id);
  const sec = (label, body) => body ? `<div><div class="lbl">${label}</div>${body}</div>` : "";
  let h = `<article class="detail"><button class="back" type="button" data-back>← უკან</button>
    <div class="meta">${chips(it)}<span>${esc(it.product || it.company || it.source)}</span><span class="t">${esc(timeLabel(it.added))}</span></div>
    <h1>${esc(it.title_ka)}</h1>
    ${it.tldr_ka ? `<div class="tldr"><div class="lbl">მოკლედ</div>${g(it.tldr_ka)}</div>` : ""}`;
  if (it.section === "community") {
    h += sec("რა ააწყო", it.built_ka ? `<p>${g(it.built_ka)}</p>` : "");
    h += it.tools?.length ? `<div class="toolrow">${it.tools.map((t) => `<span class="tool">${esc(t)}</span>`).join("")}</div>` : "";
    h += it.quote_ka ? `<p class="quote">💬 ${esc(it.quote_ka)}</p>` : "";
    h += sec("როგორ მუშაობს", (it.details_ka || []).map((p) => `<p>${g(p)}</p>`).join(""));
    h += sec("სცადე შენც", it.steps_ka?.length ? `<ol class="steps">${it.steps_ka.map((s) => `<li>${g(s)}</li>`).join("")}</ol>` : "");
  } else {
    h += sec("რა არის ახალი", it.whats_new?.length ? `<ul class="news-list">${it.whats_new.map((n) =>
      `<li><span>${esc(n.icon || "•")}</span><span><span class="k">${esc(n.label || "")}</span> ${g(n.text || "")}</span></li>`).join("")}</ul>` : "");
    h += sec("დეტალურად", (it.details_ka || []).map((p) => `<p>${g(p)}</p>`).join(""));
    h += sec("ციფრებში", it.numbers?.length ? `<div class="nums">${it.numbers.map((n) => `<div class="num"><span>${esc(n.label)}</span><strong>${esc(n.value)}</strong></div>`).join("")}</div>` : "");
    h += it.todo_ka ? `<div class="todo"><div class="lbl">რა უნდა გააკეთო</div>${rich(it.todo_ka)}</div>` : "";
  }
  h += it.why_ka ? `<div class="why"><b>რატომ მნიშვნელოვანი:</b> ${g(it.why_ka)}</div>` : "";
  h += it.use_ka ? `<div class="use"><b>💼 შენთვის:</b> ${g(it.use_ka)}</div>` : "";
  h += it.term?.word ? `<div class="termbox">📖 <b>${esc(it.term.word)}</b>: ${esc(it.term.def_ka)}</div>` : "";
  h += it.also?.length ? `<div class="also">იგივე ამბავი: ${it.also.map((a) => `<a href="${esc(safeUrl(a.url))}" target="_blank" rel="noopener">${esc(a.source)}</a>`).join(", ")}</div>` : "";
  h += `<div class="actions">
      <a class="btn" href="${esc(safeUrl(it.url))}" target="_blank" rel="noopener">ორიგინალის წაკითხვა · ${esc(it.domain)} ↗</a>
      ${it.discussion ? `<a class="btn ghost" href="${esc(safeUrl(it.discussion))}" target="_blank" rel="noopener">განხილვა ↗</a>` : ""}
      <button class="btn ghost" type="button" data-save="${esc(id)}">${saved ? "✓ შენახულია" : "🔖 შენახვა"}</button>
    </div></article>`;
  return h;
}

// ---------------------------------------------------------------- router
const ROUTES = {
  today: vToday, models: () => vCategory("models"), tools: () => vCategory("tools"), community: vCommunity,
  saved: vSaved, catchup: vCatchup, versions: vVersions, leaderboard: vLeaderboard, weekly: () => vWeekly(),
  glossary: vGlossary, about: vAbout,
};
let lastTab = "today";
const scrollPos = {};

function render() {
  const route = (location.hash || "#today").slice(1);
  let html, tab = null;
  if (route.startsWith("item-")) html = vItem(route.slice(5));
  else if (route.startsWith("week-")) html = vWeekly(route.slice(5));
  else if (ROUTES[route]) { html = ROUTES[route](); if (["today", "models", "tools", "community", "saved"].includes(route)) tab = route; }
  else { html = vToday(); tab = "today"; }
  if (tab) lastTab = tab;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === (tab || "")));
  view.innerHTML = html;
  window.scrollTo(0, tab ? scrollPos[route] || 0 : 0);
  closeSheet();
  hideTerm();
}

let currentRoute = location.hash;
window.addEventListener("hashchange", () => {
  if (currentRoute) scrollPos[(currentRoute || "#today").slice(1)] = window.scrollY;
  currentRoute = location.hash;
  render();
});

// ---------------------------------------------------------------- interactions
let navDepth = 0;
window.addEventListener("hashchange", () => { navDepth++; });

view.addEventListener("click", (e) => {
  const back = e.target.closest("[data-back]");
  if (back) {
    if (navDepth > 0 && history.length > 1) history.back();
    else location.hash = lastTab;
    return;
  }
  const fc = e.target.closest(".fchip");
  if (fc) { S.filter[fc.dataset.filter] = fc.dataset.val; render(); return; }
  const sv = e.target.closest("[data-save]");
  if (sv) { const on = toggleSave(sv.dataset.save); sv.textContent = on ? "✓ შენახულია" : "🔖 შენახვა"; toast(on ? "შენახულია" : "წაიშალა შენახულიდან"); return; }
  const gl = e.target.closest(".gl");
  if (gl) { showTerm(gl.dataset.term); e.stopPropagation(); }
});

const pop = $("#term-pop");
function showTerm(w) { pop.innerHTML = `<b>📖 ${esc(w)}</b>${esc(S.glossary[w] || "")}`; pop.hidden = false; }
function hideTerm() { pop.hidden = true; }
document.addEventListener("click", (e) => { if (!e.target.closest(".gl") && !e.target.closest("#term-pop")) hideTerm(); });

const sheet = $("#sheet"), backdrop = $("#sheet-backdrop"), menuBtn = $("#menu-btn");
function openSheet() { sheet.hidden = false; backdrop.hidden = false; menuBtn.setAttribute("aria-expanded", "true"); }
function closeSheet() { sheet.hidden = true; backdrop.hidden = true; menuBtn.setAttribute("aria-expanded", "false"); }
menuBtn.addEventListener("click", () => (sheet.hidden ? openSheet() : closeSheet()));
backdrop.addEventListener("click", closeSheet);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeSheet(); hideTerm(); } });

let toastTimer;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 1800);
}

async function refresh(manual) {
  const btn = $("#refresh");
  btn.classList.add("spin");
  const before = S.items.length ? S.items[0].id : null;
  await load();
  btn.classList.remove("spin");
  render();
  if (manual) toast(S.items.length && S.items[0].id !== before ? "ახალი სიახლეებია" : "განახლებულია");
}
$("#refresh").addEventListener("click", () => refresh(true));
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - S.loadedAt > 10 * 60e3) refresh(false);
});

function setDate() {
  const p = tbParts(new Date());
  const wd = new Date(Date.UTC(p.y, p.m - 1, p.d, 12)).getUTCDay();
  $("#today-date").textContent = `${DAYS[wd]}, ${p.d} ${MONTHS[p.m - 1]}`;
}

(async function start() {
  setDate();
  await load();
  render();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
})();
