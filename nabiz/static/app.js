// Nabız paneli — bağımlılıksız, düz JavaScript.
const $ = (s) => document.querySelector(s);
const token = () => localStorage.getItem("nabizToken") || "";
let selected = null;

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    const t = prompt("Bu işlem için NABIZ_TOKEN gerekli:");
    if (t) { localStorage.setItem("nabizToken", t); return api(path, opts); }
  }
  if (res.status === 204) return null;
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (v) => (v == null ? "–" : `%${v.toFixed(v === 100 ? 0 : 2)}`);
const ago = (t) => { const s = Math.round(Date.now() / 1000 - t); return s < 60 ? `${s} sn önce` : s < 3600 ? `${Math.round(s / 60)} dk önce` : `${Math.round(s / 3600)} sa önce`; };

function sslBadge(c) {
  if (!c || c.ssl_days == null) return '<span class="ssl na">SSL –</span>';
  const cls = c.ssl_days < 0 ? "bad" : c.ssl_days < 14 ? "warn" : "";
  return `<span class="ssl ${cls}">SSL ${c.ssl_days} gün</span>`;
}

function bars(history) {
  const cells = history.slice(-60).map((h) => `<i class="${h.up ? "u" : "d"}" title="${new Date(h.t * 1000).toLocaleString("tr-TR")}${h.ms ? ` · ${h.ms} ms` : ""}"></i>`);
  while (cells.length < 60) cells.unshift("<i></i>");
  return `<div class="bars">${cells.join("")}</div>`;
}

function render(monitors) {
  if (!monitors.length) {
    $("#list").innerHTML = '<div class="empty">Henüz izlenen site yok. <b>+ Site ekle</b> ile başlayın.</div>';
    return;
  }
  $("#list").innerHTML = monitors.map((m) => `
    <div class="row" data-id="${m.id}">
      <span class="dot ${m.status}" title="${m.status}"></span>
      <div class="name"><b>${esc(m.name)}</b><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.url)}</a></div>
      ${bars(m.history)}
      <div class="num ms"><b>${m.avg_response_ms != null ? Math.round(m.avg_response_ms) + " ms" : "–"}</b><small>ort. 24 sa</small></div>
      ${sslBadge(m.last_check)}
      <div class="num"><b>${pct(m.uptime_24h)}</b><small>uptime</small></div>
    </div>`).join("");
  document.querySelectorAll(".row").forEach((r) => r.addEventListener("click", () => select(+r.dataset.id)));
}

function chart(checks) {
  const svg = $("#chart"), W = 1000, H = 180, P = 24;
  const pts = checks.filter((c) => c.response_ms != null);
  if (pts.length < 2) { svg.innerHTML = `<text x="${W / 2}" y="${H / 2}" text-anchor="middle">Grafik için yeterli veri yok</text>`; return; }
  const t0 = checks[0].checked_at, t1 = checks[checks.length - 1].checked_at || t0 + 1;
  const max = Math.max(...pts.map((c) => c.response_ms)) * 1.15;
  const x = (t) => P + ((t - t0) / (t1 - t0 || 1)) * (W - 2 * P);
  const y = (v) => H - P - (v / max) * (H - 2 * P);
  const line = pts.map((c, i) => `${i ? "L" : "M"}${x(c.checked_at).toFixed(1)},${y(c.response_ms).toFixed(1)}`).join("");
  const area = `${line}L${x(pts.at(-1).checked_at)},${H - P}L${x(pts[0].checked_at)},${H - P}Z`;
  const downs = checks.filter((c) => !c.up).map((c) => `<circle cx="${x(c.checked_at)}" cy="${H - P}" r="4"><title>${esc(c.error)}</title></circle>`).join("");
  svg.innerHTML = `<line x1="${P}" x2="${W - P}" y1="${H - P}" y2="${H - P}"/><line x1="${P}" x2="${W - P}" y1="${y(max / 1.15 / 2)}" y2="${y(max / 1.15 / 2)}" stroke-dasharray="4 4"/>
    <text x="${P}" y="14">${Math.round(max / 1.15)} ms</text><path class="a" d="${area}"/><path class="l" d="${line}"/>${downs}`;
}

async function select(id) {
  selected = id;
  const [m, checks] = await Promise.all([api(`/api/monitors/${id}`), api(`/api/monitors/${id}/checks?hours=24`)]);
  $("#detail").classList.add("on");
  $("#dName").textContent = m.name;
  $("#dPause").textContent = m.paused ? "Devam ettir" : "Duraklat";
  const lc = m.last_check;
  $("#dMeta").innerHTML = `${esc(m.url)} · her ${m.interval_sec} sn · 7 gün ${pct(m.uptime_7d)} · 30 gün ${pct(m.uptime_30d)}${lc ? ` · son kontrol ${ago(lc.checked_at)}` : ""}`;
  $("#dErr").textContent = lc && !lc.up ? `Son hata: ${lc.error}` : "";
  chart(checks);
}

async function refresh() {
  try {
    const [list, sum] = await Promise.all([api("/api/monitors"), api("/api/summary")]);
    render(list);
    $("#tTotal").textContent = sum.total; $("#tUp").textContent = sum.up;
    $("#tDown").textContent = sum.down; $("#tSsl").textContent = sum.ssl_warnings;
    if (selected && list.some((m) => m.id === selected)) select(selected);
  } catch (e) { console.error(e); }
}

$("#addBtn").onclick = () => { $("#fErr").textContent = ""; $("#dlg").showModal(); };
$("#form").addEventListener("submit", async (e) => {
  if (e.submitter?.value !== "ok") return;
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  data.interval_sec = +data.interval_sec || 60;
  try { await api("/api/monitors", { method: "POST", body: JSON.stringify(data) }); $("#dlg").close(); e.target.reset(); refresh(); }
  catch (err) { $("#fErr").textContent = err.message; }
});
$("#dPause").onclick = async () => {
  const m = await api(`/api/monitors/${selected}`);
  await api(`/api/monitors/${selected}`, { method: "PATCH", body: JSON.stringify({ paused: !m.paused }) }); refresh();
};
$("#dDelete").onclick = async () => {
  if (!confirm("Bu site ve tüm geçmişi silinsin mi?")) return;
  await api(`/api/monitors/${selected}`, { method: "DELETE" });
  selected = null; $("#detail").classList.remove("on"); refresh();
};

// ?m=<id> ile doğrudan bir sitenin ayrıntısını açan bağlantı verilebilir.
const deepLink = +new URLSearchParams(location.search).get("m");
refresh().then(() => deepLink && select(deepLink));
setInterval(refresh, 15000);
