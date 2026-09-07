const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();
tg?.setHeaderColor?.("#0a0e1a");

const params = new URLSearchParams(window.location.search);
const mode = params.get("mode") || "admin";
const botId = params.get("bot_id");
const initData = tg?.initData || "";

const API_BASE = window.location.origin;
const app = document.getElementById("app");

const COLORS = { users: "#22c55e", messages: "#3b82f6", requests: "#f59e0b", errors: "#ef4444" };

let currentTab = "overview";
let botInfo = null;

async function main() {
  if (mode === "admin" && botId) {
    botInfo = await fetchJSON(`${API_BASE}/api/bots/${botId}`);
    await renderShell();
  } else if (mode === "user" && botId) {
    await renderUserBotScreen(botId);
  } else {
    await renderPlatformDashboard();
  }
}

async function renderShell() {
  const typeEmoji = {
    kino: "🎬", pul: "💰", openbudget: "📦", nakrutka: "🚀", vipkanal: "🔐",
    aloqa: "📞", taxi: "🚕", anketa: "📝", kafe_pos: "🍽", konkurs: "🏆",
  }[botInfo.type] || "🤖";

  app.innerHTML = `
    <div class="header">
      <div class="avatar">${typeEmoji}</div>
      <div>
        <div class="title">${botInfo.display_name}</div>
        <div class="subtitle">@${botInfo.username}</div>
        <div class="badges">
          <span class="badge">${botInfo.type}</span>
          <span class="badge" id="tariff-badge">${botInfo.tariff}</span>
        </div>
      </div>
    </div>

    <div class="nav-tabs">
      <div class="nav-tab active" data-tab="overview">📊 Umumiy</div>
      <div class="nav-tab" data-tab="users">👥 Userlar</div>
      <div class="nav-tab" data-tab="broadcast">📢 Xabar</div>
      <div class="nav-tab" data-tab="settings">⚙️ Sozlash</div>
      <div class="nav-tab" data-tab="subscription">💎 Obuna</div>
    </div>

    <div id="tab-content"></div>
  `;

  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  await switchTab("overview");
}

async function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll(".nav-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
  const content = document.getElementById("tab-content");
  content.innerHTML = `<div class="empty-state">⏳ Yuklanmoqda...</div>`;

  if (tab === "overview") await renderOverviewTab(content);
  else if (tab === "users") await renderUsersTab(content);
  else if (tab === "broadcast") await renderBroadcastTab(content);
  else if (tab === "settings") await renderSettingsTab(content);
  else if (tab === "subscription") await renderSubscriptionTab(content);
}

async function renderOverviewTab(content) {
  const stats = await fetchJSON(`${API_BASE}/api/bots/${botId}/stats?range=today`);
  const totals = sumSeries(stats.series);

  content.innerHTML = `
    <div class="range-tabs">
      <div class="range-tab active" data-range="today">Bugun</div>
      <div class="range-tab" data-range="week">Hafta</div>
      <div class="range-tab" data-range="month">Oy</div>
    </div>
    <div class="stat-grid">
      ${statCard("👥", totals.new_users, "Yangi userlar", COLORS.users)}
      ${statCard("💬", totals.messages, "Jami xabarlar", COLORS.messages)}
      ${statCard("⚡", totals.requests, "So'rovlar", COLORS.requests)}
      ${statCard("❌", totals.errors, "Xatoliklar", COLORS.errors)}
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
  `;

  drawChart(stats.series);

  content.querySelectorAll(".range-tab").forEach((tab) => {
    tab.addEventListener("click", async () => {
      content.querySelectorAll(".range-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const s = await fetchJSON(`${API_BASE}/api/bots/${botId}/stats?range=${tab.dataset.range}`);
      drawChart(s.series);
    });
  });
}

function sumSeries(series) {
  return series.reduce(
    (acc, d) => ({
      new_users: acc.new_users + d.new_users,
      messages: acc.messages + d.messages,
      requests: acc.requests + d.requests,
      errors: acc.errors + d.errors,
    }),
    { new_users: 0, messages: 0, requests: 0, errors: 0 },
  );
}

function statCard(icon, value, label, color) {
  return `
    <div class="stat-card" style="--accent-color:${color}">
      <div class="icon">${icon}</div>
      <div class="value">${value}</div>
      <div class="label">${label}</div>
    </div>`;
}

function drawChart(series) {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!series.length) {
    ctx.fillStyle = "#8890a6";
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
    ctx.lineWidth = 2.5;
    series.forEach((d, i) => {
      const x = i * stepX;
      const y = canvas.height - (d[key] / maxVal) * (canvas.height - 10) - 5;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
}

async function renderUsersTab(content) {
  const data = await fetchJSON(`${API_BASE}/api/bots/${botId}/users?init_data=${encodeURIComponent(initData)}`);

  content.innerHTML = `
    <div class="stat-grid">
      ${statCard("👥", data.total, "Jami foydalanuvchi", COLORS.users)}
      ${statCard("⛔️", data.blocked_count, "Bloklangan", COLORS.errors)}
    </div>
    <div class="panel">
      <h3>👥 Foydalanuvchilar ro'yxati</h3>
      <div id="user-list">
        ${data.users.length === 0
          ? `<div class="empty-state">Hali hech kim botga yozmagan.</div>`
          : data.users.map((u) => `
            <div class="row-item">
              <span class="user-id">${u.id}</span>
              <button class="pill-btn ${u.blocked ? "unblock" : "block"}" data-id="${u.id}" data-blocked="${u.blocked}">
                ${u.blocked ? "Blokdan chiqarish" : "Bloklash"}
              </button>
            </div>`).join("")}
      </div>
    </div>
  `;

  content.querySelectorAll(".pill-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const userId = parseInt(btn.dataset.id, 10);
      const isBlocked = btn.dataset.blocked === "true";
      const endpoint = isBlocked ? "unblock" : "block";
      await postJSON(`${API_BASE}/api/bots/${botId}/${endpoint}`, { init_data: initData, user_id: userId });
      showToast(isBlocked ? "✅ Blokdan chiqarildi" : "⛔️ Bloklandi");
      await renderUsersTab(content);
    });
  });
}

async function renderBroadcastTab(content) {
  content.innerHTML = `
    <div class="panel">
      <h3>📢 Ommaviy xabar yuborish</h3>
      <div class="form-group">
        <label>Xabar matni</label>
        <textarea id="broadcast-text" placeholder="Barcha foydalanuvchilarga yuboriladigan xabar..."></textarea>
      </div>
      <button class="action-btn" id="send-broadcast">🚀 Yuborish</button>
    </div>
  `;

  document.getElementById("send-broadcast").addEventListener("click", async () => {
    const text = document.getElementById("broadcast-text").value.trim();
    if (!text) return showToast("⚠️ Xabar matnini kiriting");
    const btn = document.getElementById("send-broadcast");
    btn.textContent = "⏳ Yuborilmoqda...";
    const result = await postJSON(`${API_BASE}/api/bots/${botId}/broadcast`, { init_data: initData, text });
    btn.textContent = "🚀 Yuborish";
    showToast(`✅ ${result.sent}/${result.total} foydalanuvchiga yuborildi`);
  });
}

async function renderSettingsTab(content) {
  const data = await fetchJSON(`${API_BASE}/api/bots/${botId}/settings?init_data=${encodeURIComponent(initData)}`);
  const settings = data.settings;
  const type = botInfo.type;

  const universalFields = [
    { key: "required_channel", label: "Majburiy obuna kanali (masalan @vezto_channel)", type: "text" },
    { key: "ad_text", label: "Reklama matni (muhim amaldan keyin ko'rsatiladi)", type: "text" },
  ];

  const fieldsByType = {
    anketa: [{ key: "questions", label: "Savollar (har biri yangi qatorda)", type: "textarea", isList: true }],
    taxi: [{ key: "driver_group_id", label: "Haydovchilar guruhi ID", type: "text" }],
    vipkanal: [
      { key: "channel_id", label: "Kanal ID", type: "text" },
      { key: "price", label: "Obuna narxi (so'm)", type: "text" },
    ],
    openbudget: [{ key: "candidates", label: "Nomzodlar (har biri yangi qatorda)", type: "textarea", isList: true }],
    konkurs: [{ key: "prize_text", label: "Sovrinlar matni", type: "text" }],
    pul: [{ key: "bonus_per_invite", label: "Har bir taklif uchun bonus (so'm)", type: "text" }],
    kafe_pos: [{ key: "kitchen_group_id", label: "Oshxona guruhi ID", type: "text" }],
    kino: [
      { key: "subscription_price", label: "Obuna narxi (so'm)", type: "text" },
      { key: "subscription_days", label: "Obuna muddati (kun)", type: "text" },
      { key: "trial_days", label: "Bepul sinov (kun)", type: "text" },
      { key: "payment_card_number", label: "To'lov uchun karta raqami", type: "text" },
      { key: "post_channel", label: "Avtopost kanali (masalan @mychannel)", type: "text" },
    ],
  };

  const fields = [...universalFields, ...(fieldsByType[type] || [])];

  content.innerHTML = `
    <div class="panel">
      <h3>⚙️ ${botInfo.display_name} sozlamalari</h3>
      ${fields.map((f) => `
        <div class="form-group">
          <label>${f.label}</label>
          ${f.type === "textarea"
            ? `<textarea id="field-${f.key}">${f.isList ? (settings[f.key] || []).join("\n") : (settings[f.key] || "")}</textarea>`
            : `<input id="field-${f.key}" value="${settings[f.key] ?? ""}" />`}
        </div>
      `).join("")}
      <button class="action-btn" id="save-settings">💾 Saqlash</button>
    </div>
    <div class="panel">
      <h3>👮 Boshqaruv buyruqlari</h3>
      <p style="color:var(--hint); font-size:13px;">Bularni to'g'ridan-to'g'ri botga yozing:</p>
      <div class="row-item"><span>/addadmin &lt;id&gt;</span><span style="color:var(--hint)">admin qo'shish</span></div>
      <div class="row-item"><span>/balance+ &lt;id&gt; &lt;summa&gt;</span><span style="color:var(--hint)">balans qo'shish</span></div>
      <div class="row-item"><span>/balance- &lt;id&gt; &lt;summa&gt;</span><span style="color:var(--hint)">balans ayirish</span></div>
      <div class="row-item"><span>/adminlar</span><span style="color:var(--hint)">ro'yxat</span></div>
    </div>
  `;

  document.getElementById("save-settings").addEventListener("click", async () => {
    const payload = {};
    fields.forEach((f) => {
      const el = document.getElementById(`field-${f.key}`);
      payload[f.key] = f.isList
        ? el.value.split("\n").map((l) => l.trim()).filter(Boolean)
        : el.value.trim();
    });
    await postJSON(`${API_BASE}/api/bots/${botId}/settings`, { init_data: initData, settings: payload });
    showToast("✅ Sozlamalar saqlandi");
  });

  if (type === "kino") {
    await renderKinoLibrary(content);
  }
}

async function renderKinoLibrary(content) {
  const data = await fetchJSON(`${API_BASE}/api/bots/${botId}/kino/movies?init_data=${encodeURIComponent(initData)}`);
  const libraryPanel = document.createElement("div");
  libraryPanel.className = "panel";
  libraryPanel.innerHTML = `
    <h3>🎬 Kino kutubxonasi (${data.movies.length})</h3>
    ${data.movies.length === 0
      ? `<div class="empty-state">Hali kino qo'shilmagan.</div>`
      : data.movies.map((m) => `
        <div class="row-item">
          <span class="user-id">🔑 ${m.code}</span>
          <button class="pill-btn block" data-code="${m.code}">🗑 O'chirish</button>
        </div>`).join("")}
  `;
  content.appendChild(libraryPanel);

  libraryPanel.querySelectorAll(".pill-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await postJSON(`${API_BASE}/api/bots/${botId}/kino/delete-movie`, { init_data: initData, code: btn.dataset.code });
      showToast("🗑 O'chirildi");
      await renderSettingsTab(content);
    });
  });
}

async function renderSubscriptionTab(content) {
  const sub = await fetchJSON(`${API_BASE}/api/bots/${botId}/subscription?init_data=${encodeURIComponent(initData)}`);
  const expiryText = sub.expires_at
    ? new Date(sub.expires_at).toLocaleDateString("uz-UZ")
    : "Cheklanmagan";

  content.innerHTML = `
    <div class="panel">
      <h3>💎 Joriy obuna</h3>
      <div class="row-item">
        <span>Tarif</span>
        <span class="badge ${sub.is_expired ? "expired" : "active"}">${sub.current_tariff}</span>
      </div>
      <div class="row-item">
        <span>Tugash sanasi</span>
        <span>${expiryText}</span>
      </div>
      ${sub.is_expired ? `<div class="empty-state" style="color:#fca5a5">⏳ Obuna muddati tugagan — bot to'xtatilgan!</div>` : ""}
    </div>
    <div class="panel">
      <h3>🚀 Tarifni yangilash</h3>
      ${sub.options.map((t, i) => `
        <div class="tariff-card ${i === 1 ? "recommended" : ""}" data-key="${t.key}">
          <div>
            <div class="tariff-title">${t.title}</div>
            <div class="tariff-sub">${t.duration_days} kun • ${t.daily_limit.toLocaleString()} so'rov/kun</div>
          </div>
          <div class="tariff-price">${t.price.toLocaleString()} so'm</div>
        </div>
      `).join("")}
    </div>
  `;

  content.querySelectorAll(".tariff-card").forEach((card) => {
    card.addEventListener("click", async () => {
      try {
        await postJSON(`${API_BASE}/api/bots/${botId}/subscription/renew`, {
          init_data: initData, tariff_key: card.dataset.key,
        });
        showToast("✅ Tarif yangilandi!");
        await renderSubscriptionTab(content);
        const badge = document.getElementById("tariff-badge");
        if (badge) badge.textContent = card.dataset.key;
      } catch (e) {
        showToast("⚠️ Balans yetarli emas yoki xatolik yuz berdi");
      }
    });
  });
}

async function renderUserBotScreen(id) {
  const info = await fetchJSON(`${API_BASE}/api/bots/${id}`);
  const renderers = { taxi: renderTaxiForm, anketa: renderAnketaForm };
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
    tg?.sendData(JSON.stringify({
      action: "taxi_order",
      from: document.getElementById("from").value,
      to: document.getElementById("to").value,
      phone: document.getElementById("phone").value,
    }));
    tg?.close();
  });
}

function renderAnketaForm(info) {
  app.innerHTML = `
    <div class="header"><div class="avatar">📝</div><div class="title">${info.display_name}</div></div>
    <div class="panel"><p>Ushbu anketada ${info.questions?.length || 0} ta savol bor. Javob berish uchun botga qayting va /start bosing.</p></div>`;
}

function renderGenericPlaceholder(info) {
  app.innerHTML = `
    <div class="header"><div class="avatar">🤖</div><div class="title">${info.display_name}</div></div>
    <div class="panel"><p>Bu bot turi uchun Mini App interfeysi hali qo'shilmagan.</p></div>`;
}

// ==================== PLATFORM DASHBOARD (butun tizim) ====================

let platformMe = null;
let platformCatalog = null;
let currentPlatformTab = "home";
let selectedBotType = null;

async function renderPlatformDashboard() {
  try {
    platformMe = await fetchJSON(`${API_BASE}/api/me?init_data=${encodeURIComponent(initData)}`);
  } catch (e) {
    app.innerHTML = `<div class="panel"><div class="empty-state">⚠️ Botni Telegram ichidan oching (Vezto botiga /start yozing).</div></div>`;
    return;
  }

  app.innerHTML = `
    <div class="header">
      <div class="avatar">🛡</div>
      <div>
        <div class="title">Vezto</div>
        <div class="subtitle">Telegram botlar platformasi</div>
      </div>
    </div>
    <div class="nav-tabs" style="flex-wrap:wrap;">
      <div class="nav-tab active" data-ptab="home">🏠 Bosh</div>
      <div class="nav-tab" data-ptab="create">➕ Yaratish</div>
      <div class="nav-tab" data-ptab="mybots">🤖 Botlarim</div>
      <div class="nav-tab" data-ptab="referral">🗣 Referal</div>
      <div class="nav-tab" data-ptab="profile">👤 Kabinet</div>
      <div class="nav-tab" data-ptab="help">❓ Yordam</div>
    </div>
    <div id="platform-tab-content"></div>
  `;

  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchPlatformTab(tab.dataset.ptab));
  });

  await switchPlatformTab("home");
}

async function switchPlatformTab(tab) {
  currentPlatformTab = tab;
  document.querySelectorAll(".nav-tab").forEach((t) => t.classList.toggle("active", t.dataset.ptab === tab));
  const content = document.getElementById("platform-tab-content");
  content.innerHTML = `<div class="empty-state">⏳ Yuklanmoqda...</div>`;

  if (tab === "home") renderHomeTab(content);
  else if (tab === "create") await renderCreateBotTab(content);
  else if (tab === "mybots") renderMyBotsTab(content);
  else if (tab === "referral") renderReferralTab(content);
  else if (tab === "profile") renderProfileTab(content);
  else if (tab === "help") renderHelpTab(content);
}

function renderHomeTab(content) {
  const activeBots = platformMe.bots.filter((b) => b.status === "active").length;
  content.innerHTML = `
    <div class="stat-grid">
      ${statCard("💼", platformMe.balance.toLocaleString() + " so'm", "Balansingiz", COLORS.users)}
      ${statCard("🤖", platformMe.bots.length, "Jami botlar", COLORS.messages)}
      ${statCard("🟢", activeBots, "Faol botlar", "#22c55e")}
      ${statCard("👥", platformMe.referral_count, "Takliflaringiz", COLORS.requests)}
    </div>
    <div class="panel">
      <h3>🚀 Tez havolalar</h3>
      <button class="action-btn" id="quick-create">➕ Yangi bot yaratish</button>
      <button class="action-btn secondary" id="quick-mybots" style="margin-top:10px">🤖 Botlarimni ko'rish</button>
    </div>
  `;
  document.getElementById("quick-create").addEventListener("click", () => switchPlatformTab("create"));
  document.getElementById("quick-mybots").addEventListener("click", () => switchPlatformTab("mybots"));
}

async function renderCreateBotTab(content) {
  if (!platformCatalog) {
    platformCatalog = (await fetchJSON(`${API_BASE}/api/catalog`)).types;
  }

  if (!selectedBotType) {
    content.innerHTML = `
      <div class="panel">
        <h3>➕ Bot turini tanlang</h3>
        ${platformCatalog.map((t) => `
          <div class="tariff-card" data-key="${t.key}">
            <div>
              <div class="tariff-title">${t.emoji} ${t.title}</div>
              <div class="tariff-sub">${t.description.slice(0, 50)}...</div>
            </div>
            <div class="tariff-price">${t.price.toLocaleString()} so'm</div>
          </div>
        `).join("")}
      </div>
    `;
    content.querySelectorAll(".tariff-card").forEach((card) => {
      card.addEventListener("click", () => {
        selectedBotType = platformCatalog.find((t) => t.key === card.dataset.key);
        renderCreateBotTab(content);
      });
    });
    return;
  }

  content.innerHTML = `
    <div class="panel">
      <h3>${selectedBotType.emoji} ${selectedBotType.title}</h3>
      <p style="color:var(--hint); font-size:13.5px;">${selectedBotType.description}</p>
      <div class="row-item"><span>Narxi</span><span class="tariff-price">${selectedBotType.price.toLocaleString()} so'm</span></div>
      <div class="row-item"><span>Balansingiz</span><span>${platformMe.balance.toLocaleString()} so'm</span></div>
    </div>
    <div class="panel">
      <div class="form-group">
        <label>🔑 @BotFather'dan olingan token</label>
        <input id="bot-token-input" placeholder="123456789:AA..." />
      </div>
      <button class="action-btn" id="submit-create">✅ Yaratish — ${selectedBotType.price.toLocaleString()} so'm</button>
      <button class="action-btn secondary" id="back-to-catalog" style="margin-top:8px">◀ Orqaga</button>
    </div>
  `;

  document.getElementById("back-to-catalog").addEventListener("click", () => {
    selectedBotType = null;
    renderCreateBotTab(content);
  });

  document.getElementById("submit-create").addEventListener("click", async () => {
    const token = document.getElementById("bot-token-input").value.trim();
    if (!token) return showToast("⚠️ Tokenni kiriting");
    const btn = document.getElementById("submit-create");
    btn.textContent = "⏳ Yaratilmoqda...";
    try {
      const result = await postJSON(`${API_BASE}/api/create-bot`, {
        init_data: initData, bot_type: selectedBotType.key, token,
      });
      showToast(`✅ @${result.bot_username} yaratildi!`);
      selectedBotType = null;
      platformMe = await fetchJSON(`${API_BASE}/api/me?init_data=${encodeURIComponent(initData)}`);
      await switchPlatformTab("mybots");
    } catch (e) {
      btn.textContent = `✅ Yaratish — ${selectedBotType.price.toLocaleString()} so'm`;
      showToast("❌ Xatolik: token noto'g'ri yoki balans yetarli emas");
    }
  });
}

function renderMyBotsTab(content) {
  if (platformMe.bots.length === 0) {
    content.innerHTML = `<div class="panel"><div class="empty-state">Hali botlaringiz yo'q. "➕ Yaratish" bo'limidan birinchi botingizni yarating!</div></div>`;
    return;
  }

  const typeEmoji = {
    kino: "🎬", pul: "💰", openbudget: "📦", nakrutka: "🚀", vipkanal: "🔐",
    aloqa: "📞", taxi: "🚕", anketa: "📝", kafe_pos: "🍽", konkurs: "🏆",
  };

  content.innerHTML = `
    <div class="panel">
      <h3>🤖 Botlaringiz</h3>
      ${platformMe.bots.map((b) => `
        <div class="tariff-card" data-bot-id="${b.id}">
          <div>
            <div class="tariff-title">${typeEmoji[b.type] || "🤖"} @${b.username}</div>
            <div class="tariff-sub">${b.tariff} • ${b.status}</div>
          </div>
          <div>▶</div>
        </div>
      `).join("")}
    </div>
  `;

  content.querySelectorAll(".tariff-card").forEach((card) => {
    card.addEventListener("click", () => {
      const id = card.dataset.botId;
      window.location.href = `${window.location.pathname}?mode=admin&bot_id=${id}`;
    });
  });
}

function renderReferralTab(content) {
  const link = platformMe.referral_link || "—";
  content.innerHTML = `
    <div class="panel">
      <h3>🎁 Do'stlaringizni taklif qiling</h3>
      <p style="color:var(--hint); font-size:13.5px;">Har bir taklif qilingan do'stingiz uchun 500 so'm bonus olasiz.</p>
      <div class="stat-grid">
        ${statCard("👥", platformMe.referral_count, "Takliflaringiz", COLORS.users)}
        ${statCard("💰", (platformMe.referral_count * 500).toLocaleString(), "Ishlagan bonus (so'm)", COLORS.requests)}
      </div>
      <div class="form-group">
        <label>Sizning havolangiz</label>
        <input id="ref-link" value="${link}" readonly />
      </div>
      <button class="action-btn" id="copy-ref">📋 Havolani nusxalash</button>
    </div>
  `;
  document.getElementById("copy-ref").addEventListener("click", () => {
    navigator.clipboard?.writeText(link);
    showToast("✅ Nusxalandi!");
  });
}

function renderProfileTab(content) {
  content.innerHTML = `
    <div class="panel">
      <h3>👤 Shaxsiy kabinet</h3>
      <div class="row-item"><span>Telegram ID</span><span class="user-id">${platformMe.telegram_id}</span></div>
      <div class="row-item"><span>Balans</span><span>${platformMe.balance.toLocaleString()} so'm</span></div>
      <div class="row-item"><span>Botlar soni</span><span>${platformMe.bots.length} ta</span></div>
      <div class="row-item"><span>Takliflar</span><span>${platformMe.referral_count} ta</span></div>
    </div>
    <div class="panel">
      <h3>💳 Hisobni to'ldirish</h3>
      <p style="color:var(--hint); font-size:13.5px;">Balansni to'ldirish uchun Vezto botiga qayting va "💳 Hisob to'ldirish" tugmasini bosing — u yerda karta raqami va chek yuborish tartibi ko'rsatilgan.</p>
    </div>
  `;
}

function renderHelpTab(content) {
  content.innerHTML = `
    <div class="panel">
      <h3>❓ Tez-tez so'raladigan savollar</h3>
      <div class="row-item"><span>🤖 Bot qanday yaratiladi?</span></div>
      <p style="color:var(--hint); font-size:13px; margin-top:-8px;">@BotFather orqali token oling, "➕ Yaratish" bo'limida turini tanlang va tokenni kiriting.</p>
      <div class="row-item"><span>💳 To'lov qanday amalga oshiriladi?</span></div>
      <p style="color:var(--hint); font-size:13px; margin-top:-8px;">Karta orqali to'lab, chek yuborasiz — admin tasdiqlagach mablag' tushadi.</p>
      <div class="row-item"><span>⏳ Sinov muddati qancha?</span></div>
      <p style="color:var(--hint); font-size:13px; margin-top:-8px;">Har bir yangi bot 3 kun bepul ishlaydi, keyin tarif tanlash kerak.</p>
    </div>
    <div class="panel">
      <h3>📞 Yordam kerakmi?</h3>
      <p style="color:var(--hint); font-size:13.5px;">Vezto botiga qayting va "📩 Murojaat" bo'limidan admin bilan bog'laning.</p>
    </div>
  `;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

function showToast(text) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

main();
