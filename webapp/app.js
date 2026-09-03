const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const params = new URLSearchParams(window.location.search);
const mode = params.get("mode") || "admin";
const botId = params.get("bot_id");

const API_BASE = window.location.origin;
const app = document.getElementById("app");

const COLORS = { users: "#22c55e", messages: "#3b82f6", requests: "#eab308", errors: "#ef4444" };

async function main() {
  if (mode === "admin" && botId) {
    await renderAdminDashboard(botId);
  } else if (mode === "user" && botId) {
    await renderUserBotScreen(botId);
  } else {
    await renderMyBotsOverview();
  }
}

// ---------------- ADMIN DASHBOARD (bitta botni boshqarish) ----------------

async function renderAdminDashboard(id) {
  const [info, stats] = await Promise.all([
    fetchJSON(`${API_BASE}/api/bots/${id}`),
    fetchJSON(`${API_BASE}/api/bots/${id}/stats?range=today`),
  ]);

  const totals = stats.series.reduce(
    (acc, d) => ({
      new_users: acc.new_users + d.new_users,
      messages: acc.messages + d.messages,
      requests: acc.requests + d.requests,
      errors: acc.errors + d.errors,
      undelivered: acc.undelivered + d.undelivered,
    }),
    { new_users: 0, messages: 0, requests: 0, errors: 0, undelivered: 0 },
  );

  app.innerHTML = `
    <div class="header">
      <div class="avatar">🎬</div>
      <div>
        <div class="title">${info.display_name}</div>
        <div class="subtitle">@${info.username}</div>
        <div class="badges">
          <span class="badge">${info.type}</span>
          <span class="badge">${info.tariff}</span>
        </div>
      </div>
    </div>

    <div class="tabs">
      <div class="tab active" data-range="today">Bugun</div>
      <div class="tab" data-range="week">Hafta</div>
      <div class="tab" data-range="month">Oy</div>
    </div>

    <div class="stat-grid">
      ${statCard("👥", totals.new_users, "Yangi userlar", COLORS.users)}
      ${statCard("💬", totals.messages, "Jami xabarlar", COLORS.messages)}
      ${statCard("⚡", totals.requests, "Jami so'rovlar", COLORS.messages)}
      ${statCard("❌", totals.errors, "Xatoliklar", COLORS.errors)}
      ${statCard("🚫", totals.undelivered, "Yetkazilmagan", COLORS.requests)}
      ${statCard("⏱", "100%", "Webhook uptime", "#a855f7")}
    </div>

    <div class="panel">
      <h3>📈 Faollik grafigi</h3>
      <div class="chart-legend">
        <span><i class="dot" style="background:${COLORS.users}"></i>Userlar</span>
        <span><i class="dot" style="background:${COLORS.messages}"></i>Xabar</span>
        <span><i class="dot" style="background:${COLORS.requests}"></i>So'rov</span>
        <span><i class="dot" style="background:${COLORS.errors}"></i>Xato</span>
      </div>
      <canvas id="chart" width="320" height="140"></canvas>
    </div>

    <div class="panel">
      <h3>Xato turlari</h3>
      <div id="error-breakdown"></div>
    </div>
  `;

  drawChart(stats.series);

  const errBox = document.getElementById("error-breakdown");
  errBox.innerHTML = totals.errors === 0
    ? `<div class="row-item">✅ Xatoliklar aniqlanmadi</div>`
    : `<div class="row-item">Jami: ${totals.errors} ta xato</div>`;

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", async () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const s = await fetchJSON(`${API_BASE}/api/bots/${id}/stats?range=${tab.dataset.range}`);
      drawChart(s.series);
    });
  });
}

function statCard(icon, value, label, color) {
  return `
    <div class="stat-card" style="border-color:${color}">
      <div class="icon">${icon}</div>
      <div class="value">${value}</div>
      <div class="label">${label}</div>
      <div class="bar"><div style="background:${color}"></div></div>
    </div>`;
}

function drawChart(series) {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!series.length) {
    ctx.fillStyle = "#8a93a6";
    ctx.font = "13px sans-serif";
    ctx.fillText("Ma'lumot yo'q", 110, 70);
    return;
  }

  const keys = ["new_users", "messages", "requests", "errors"];
  const colorMap = [COLORS.users, COLORS.messages, COLORS.requests, COLORS.errors];
  const maxVal = Math.max(1, ...series.flatMap((d) => keys.map((k) => d[k])));
  const stepX = canvas.width / Math.max(1, series.length - 1);

  keys.forEach((key, ki) => {
    ctx.beginPath();
    ctx.strokeStyle = colorMap[ki];
    ctx.lineWidth = 2;
    series.forEach((d, i) => {
      const x = i * stepX;
      const y = canvas.height - (d[key] / maxVal) * (canvas.height - 10) - 5;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
}

// ---------------- USER-FACING BOT SCREEN (bot turiga qarab) ----------------

async function renderUserBotScreen(id) {
  const info = await fetchJSON(`${API_BASE}/api/bots/${id}`);

  const renderers = {
    taxi: renderTaxiForm,
    anketa: renderAnketaForm,
    kafe_pos: renderKafePos,
  };

  const renderer = renderers[info.type] || renderGenericPlaceholder;
  renderer(info);
}

function renderTaxiForm(info) {
  app.innerHTML = `
    <div class="header"><div class="avatar">🚕</div><div class="title">${info.display_name}</div></div>
    <div class="panel">
      <div class="form-group"><label>Qayerdan</label><input id="from" placeholder="Manzil" /></div>
      <div class="form-group"><label>Qayerga</label><input id="to" placeholder="Manzil" /></div>
      <div class="form-group"><label>Telefon</label><input id="phone" placeholder="+998..." /></div>
      <button class="action-btn" id="submit">Buyurtma berish</button>
    </div>`;

  document.getElementById("submit").addEventListener("click", () => {
    const payload = {
      action: "taxi_order",
      from: document.getElementById("from").value,
      to: document.getElementById("to").value,
      phone: document.getElementById("phone").value,
    };
    tg?.sendData(JSON.stringify(payload));
    tg?.close();
  });
}

function renderAnketaForm(info) {
  app.innerHTML = `
    <div class="header"><div class="avatar">📝</div><div class="title">${info.display_name}</div></div>
    <div class="panel">
      <p>Ushbu anketada ${info.questions?.length || 0} ta savol bor.
      Javob berish uchun botga qayting va /start bosing — Mini App orqali
      to'liq forma rejimi keyingi versiyada qo'shiladi.</p>
    </div>`;
}

function renderKafePos(info) {
  app.innerHTML = `
    <div class="header"><div class="avatar">🍽</div><div class="title">${info.display_name}</div></div>
    <div class="panel"><p>Kafe POS xodimlar paneli — buyurtmalar ro'yxati shu yerda chiqadi.</p></div>`;
}

function renderGenericPlaceholder(info) {
  app.innerHTML = `
    <div class="header"><div class="avatar">🤖</div><div class="title">${info.display_name}</div></div>
    <div class="panel"><p>Bu bot turi (${info.type}) uchun Mini App interfeysi hali qo'shilmagan.</p></div>`;
}

// ---------------- Botlar ro'yxati (parametrsiz ochilganda) ----------------

async function renderMyBotsOverview() {
  const initData = tg?.initData || "";
  try {
    const me = await fetchJSON(`${API_BASE}/api/me?init_data=${encodeURIComponent(initData)}`);
    app.innerHTML = `
      <div class="panel">
        <h3>💼 Balans: ${me.balance.toLocaleString()} so'm</h3>
        ${me.bots.map((b) => `<div class="row-item"><span>@${b.username}</span><span>${b.status}</span></div>`).join("")}
      </div>`;
  } catch (e) {
    app.innerHTML = `<div class="panel"><p>⚠️ Ma'lumotlarni yuklab bo'lmadi. Botni Telegram ichidan oching.</p></div>`;
  }
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

main();
