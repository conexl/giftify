const el = (id) => document.getElementById(id);
const state = {
  userId: 1,
  catalog: {},
  rules: [],
  gifts: [],
  bot: { paused: true },
  confirmAction: null,
  selectedGift: null,
  lastFocused: null,
  isLoading: false,
  activeTab: "rules",
  wizardStep: 1,
  selectedModel: "",
  modelSearchQuery: "",
  devMode: false
};

const ID_LIKE_RE = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)$/i;
const AUTO_REFRESH_MS = 3000;
let lastRenderState = "";

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#090d16" : "#f8fafc");
  const button = el("themeToggle");
  if (button) {
    const dark = theme === "dark";
    button.setAttribute("aria-pressed", String(dark));
    button.setAttribute("title", dark ? "Светлая тема" : "Тёмная тема");
    button.setAttribute("aria-label", dark ? "Светлая тема" : "Тёмная тема");
  }
}
function initializeTheme() { applyTheme(localStorage.getItem("giftify-theme") || "dark"); }

function renderAccessDenied(message) {
  document.body.innerHTML = `
    <div style="background:#090d16;color:#f8fafc;font-family:'Plus Jakarta Sans',system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;box-sizing:border-box;text-align:center;">
      <div style="background:#111827;border:1px solid rgba(255,255,255,0.12);border-radius:24px;padding:48px 32px;max-width:440px;width:100%;box-shadow:0 25px 50px -12px rgba(0,0,0,0.5);">
        <h1 style="font-size:24px;font-weight:800;margin:0 0 12px 0;color:#f43f5e;letter-spacing:-0.02em;">Доступ ограничен</h1>
        <p style="font-size:14px;color:#94a3b8;line-height:1.6;margin:0 0 28px 0;">${escapeHtml(message || "Приложение доступно только через Telegram Mini App для авторизованных пользователей.")}</p>
        <div style="display:inline-block;background:#1f2937;color:#818cf8;padding:8px 16px;border-radius:10px;font-size:13px;font-weight:700;font-family:'JetBrains Mono',monospace;">giftify.xorx.dev</div>
      </div>
    </div>
  `;
}

function telegramInitData() {
  const telegram = window.Telegram?.WebApp;
  telegram?.ready?.();
  telegram?.expand?.();
  return telegram?.initData || "";
}

function telegramUserId() {
  const telegram = window.Telegram?.WebApp;
  telegram?.ready?.();
  telegram?.expand?.();
  const id = Number(telegram?.initDataUnsafe?.user?.id);
  return Number.isFinite(id) ? id : 1;
}

async function requestJson(url, options = {}) {
  const initData = telegramInitData();
  const headers = {
    "Content-Type": "application/json",
    ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
    ...(options.headers || {})
  };
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401 || response.status === 403) {
    const error = await response.json().catch(() => ({}));
    renderAccessDenied(error.detail || "Доступ к приложению ограничен.");
    throw new Error(error.detail || "Доступ к приложению ограничен.");
  }
  if (!response.ok) throw new Error("Не удалось выполнить запрос. Повторите попытку.");
  return response.json();
}

function escapeHtml(value) { return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;"); }
function formatTon(value) { return `${Number(value || 0).toLocaleString("ru-RU", { maximumFractionDigits: 3 })} TON`; }
function relativeTime(value) { const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 1000)); if (!Number.isFinite(seconds) || seconds < 60) return "только что"; if (seconds < 3600) return `${Math.floor(seconds / 60)} мин. назад`; if (seconds < 86400) return `${Math.floor(seconds / 3600)} ч. назад`; return `${Math.floor(seconds / 86400)} дн. назад`; }
function rarity(value) { return Number(value || 0) > 0 ? `${Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}%` : "—"; }
function safeUrl(value) { return /^https?:\/\//.test(String(value || "")) ? String(value) : ""; }
function formatImageUrl(url) {
  if (!url || typeof url !== "string") return "";
  let text = url.trim();
  if (text.startsWith("http://") || text.startsWith("https://")) {
    return text;
  }
  if (text.startsWith("//")) {
    return "https:" + text;
  }
  return `https://cdn.tgmrkt.io/${text.replace(/^\/+/, "")}`;
}

function getCollectionPhotoUrl(colObj) {
  const primaryUrl = typeof colObj === "object" && colObj?.photo_url ? colObj.photo_url : "";
  if (primaryUrl) return formatImageUrl(primaryUrl);
  return "";
}

function getModelPhotoUrl(item) {
  if (item?.photo_url) return formatImageUrl(item.photo_url);
  return "";
}
function displayText(value, fallback = "—") { const text = String(value || "").trim(); return text && !ID_LIKE_RE.test(text) ? text : fallback; }

async function loadAll({ silent = false } = {}) {
  if (state.isLoading) return;
  state.isLoading = true;
  const [catalog, rules, gifts, bot] = await Promise.allSettled([
    requestJson("/api/v1/catalog"),
    requestJson(`/api/v1/rules?user_id=${state.userId}`),
    requestJson("/api/v1/saved-gifts"),
    requestJson("/api/v1/bot-status")
  ]);
  state.isLoading = false;

  if (catalog.status === "fulfilled") state.catalog = catalog.value;
  if (rules.status === "fulfilled") state.rules = rules.value.rules;
  if (gifts.status === "fulfilled") state.gifts = gifts.value.gifts || [];
  if (bot.status === "fulfilled") state.bot = bot.value;

  const currentStateKey = JSON.stringify({
    c: state.catalog,
    r: state.rules,
    g: state.gifts,
    b: state.bot,
    tab: state.activeTab,
    query: el("giftSearchInput")?.value || "",
    market: el("giftMarketFilter")?.value || "",
  });

  if (currentStateKey !== lastRenderState) {
    lastRenderState = currentStateKey;
    render();
  }

  if (!silent && [catalog, rules, gifts, bot].some((r) => r.status === "rejected")) {
    showToast("Часть данных временно недоступна.", true);
  }
}

/* TAB SWITCHING (2 MAIN PAGES: rules & gifts) */
function switchTab(tab) {
  state.activeTab = tab;
  
  el("tabRulesBtn").classList.toggle("active", tab === "rules");
  el("tabRulesBtn").setAttribute("aria-selected", String(tab === "rules"));
  el("pageRules").hidden = tab !== "rules";

  el("tabGiftsBtn").classList.toggle("active", tab === "gifts");
  el("tabGiftsBtn").setAttribute("aria-selected", String(tab === "gifts"));
  el("pageGifts").hidden = tab !== "gifts";

  el("pageAddRule").hidden = true;

  render();
}

function openAddRulePage() {
  resetWizard();
  state.activeTab = "addRule";
  el("tabRulesBtn").classList.remove("active");
  el("tabRulesBtn").setAttribute("aria-selected", "false");
  el("tabGiftsBtn").classList.remove("active");
  el("tabGiftsBtn").setAttribute("aria-selected", "false");

  el("pageRules").hidden = true;
  el("pageGifts").hidden = true;
  el("pageAddRule").hidden = false;

  renderCollectionSelection();
}

const openRuleModal = openAddRulePage;

function createOptionPicker(kind) {
  const input = el(`${kind}Input`);
  const menu = el(`${kind}Menu`);
  if (!input || !menu) return { setValues() {} };
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {}
  });
  return { setValues() {} };
}

function resetWizard() {
  state.wizardStep = 1;
  state.selectedModel = "";
  state.modelSearchQuery = "";
  el("ruleForm")?.reset();
  if (el("modelSearchInput")) el("modelSearchInput").value = "";
  setWizardStep(1);
}

function setWizardStep(step) {
  state.wizardStep = step;
  
  // Update Progress Bar UI: Step 1 -> 0%, Step 2 -> 50%, Step 3 -> 100%
  const progressFill = el("wizardProgressFill");
  if (progressFill) {
    const percentage = step === 1 ? 0 : step === 2 ? 50 : 100;
    progressFill.style.width = `${percentage}%`;
  }

  const progressBar = document.querySelector(".wizardProgressBar");
  if (progressBar) {
    progressBar.setAttribute("aria-valuenow", String(step));
  }

  document.querySelectorAll(".wizardStepLabel").forEach((item) => {
    const s = Number(item.dataset.step);
    item.classList.toggle("active", s === step);
    item.classList.toggle("completed", s < step);
  });

  // Toggle Stages
  el("wizardStage1").hidden = step !== 1;
  el("wizardStage2").hidden = step !== 2;
  el("wizardStage3").hidden = step !== 3;

  if (step === 1) {
    renderCollectionSelection();
  } else if (step === 2) {
    loadAndRenderModels();
  } else if (step === 3) {
    loadAndRenderBackdrops();
  }
  updateRuleSummary();
}

/* COLLECTION SELECTION WITH PREVIEWS */
function renderCollectionSelection() {
  const container = el("collectionGrid");
  if (!container) return;

  const collections = state.catalog.collections || [];
  const currentVal = el("collectionInput")?.value || "";
  const filterQuery = currentVal.trim().toLowerCase();

  // Filter collections by user input in real time
  const filteredCollections = collections.filter(colObj => {
    const name = typeof colObj === "string" ? colObj : (colObj?.name || "");
    return !filterQuery || name.toLowerCase().includes(filterQuery);
  });

  if (!filteredCollections.length) {
    container.innerHTML = '<div class="emptyModels">Коллекции не найдены</div>';
    return;
  }

  container.replaceChildren(
    ...filteredCollections.map((colObj) => {
      const name = typeof colObj === "string" ? colObj : colObj.name;
      const photoUrl = getCollectionPhotoUrl(colObj);
      const isSelected = name === currentVal;

      const card = document.createElement("button");
      card.type = "button";
      card.className = `collectionCard ${isSelected ? "selected" : ""}`;

      const imageHtml = photoUrl
        ? `<img src="${escapeHtml(photoUrl)}" alt="${escapeHtml(name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none';if(this.nextElementSibling)this.nextElementSibling.style.display='flex';" /><div class="collectionPlaceholder" style="display:none;">${escapeHtml(name.slice(0, 2).toUpperCase())}</div>`
        : `<div class="collectionPlaceholder">${escapeHtml(name.slice(0, 2).toUpperCase())}</div>`;

      card.innerHTML = `
        <div class="collectionThumb">${imageHtml}</div>
        <span class="collectionName">${escapeHtml(name)}</span>
      `;

      card.addEventListener("click", () => {
        el("collectionInput").value = name;
        renderCollectionSelection();
        updateRuleSummary();
        setWizardStep(2);
      });

      return card;
    })
  );
}

const TELEGRAM_BACKDROP_COLORS = {
  'Amber': ['#dab345', '#b1802a'],
  'Aquamarine': ['#60b195', '#46abb4'],
  'Azure Blue': ['#5db1cb', '#448bab'],
  'Battleship Grey': ['#8c8c85', '#6c6c66'],
  'Black': ['#363738', '#0e0f0f'],
  'Burgundy': ['#a35e66', '#6d414a'],
  'Burnt Sienna': ['#d66f3c', '#b54b2d'],
  'Camo Green': ['#75944d', '#547341'],
  'Cappuccino': ['#b1907e', '#7c6356'],
  'Caramel': ['#d09932', '#b77431'],
  'Carmine': ['#e0574a', '#a8383b'],
  'Carrot Juice': ['#db9867', '#c76f4f'],
  'Celtic Blue': ['#45b8ed', '#3886d9'],
  'Chestnut': ['#be6f54', '#994838'],
  'Chocolate': ['#a46e58', '#74443b'],
  'Cobalt Blue': ['#6088cf', '#5162b8'],
  'Copper': ['#d08656', '#9d6531'],
  'Coral Red': ['#da896b', '#c4654f'],
  'Cyberpunk': ['#858ff3', '#865fd3'],
  'Dark Green': ['#516341', '#2b452f'],
  'Dark Lilac': ['#b17da5', '#8c577a'],
  'Deep Cyan': ['#31b5aa', '#189599'],
  'Desert Sand': ['#b39f82', '#7e735b'],
  'Electric Indigo': ['#a980f3', '#5b62d8'],
  'Electric Purple': ['#ca70c6', '#9662d4'],
  'Emerald': ['#78c585', '#42a171'],
  'English Violet': ['#b186bb', '#875a91'],
  'Fandango': ['#e28ab6', '#a4588b'],
  'Feldgrau': ['#899288', '#5e6b63'],
  'Fire Engine': ['#f05f4f', '#c43949'],
  'French Blue': ['#5c9bc4', '#37739a'],
  'French Violet': ['#c260e6', '#914ed9'],
  'Grape': ['#9d74c1', '#794da0'],
  'Gunmetal': ['#4c5d63', '#2f3b42'],
  'Gunship Green': ['#558a65', '#3d6657'],
  'Hunter Green': ['#8fae78', '#4b825b'],
  'Indigo Dye': ['#537991', '#416479'],
  'Ivory White': ['#bab6b1', '#a19d97'],
  'Jade Green': ['#55c49c', '#3b9977'],
  'Khaki Green': ['#adb070', '#6b7d54'],
  'Lavender': ['#b789e4', '#8a5abc'],
  'Lemongrass': ['#aeb85a', '#559345'],
  'Light Olive': ['#c2af64', '#887e45'],
  'Malachite': ['#95b457', '#3d9755'],
  'Marine Blue': ['#4e689c', '#3b4b7a'],
  'Mexican Pink': ['#e36692', '#c9497c'],
  'Midnight Blue': ['#5c6985', '#354057'],
  'Mint Green': ['#7ecb82', '#459e5a'],
  'Moonstone': ['#7eb1b4', '#588390'],
  'Mustard': ['#d4980d', '#c47712'],
  'Mystic Pearl': ['#d08b6d', '#b05770'],
  'Navy Blue': ['#6c9edd', '#5c6ec9'],
  'Neon Blue': ['#7596f9', '#6862e4'],
  'Old Gold': ['#b58d38', '#946925'],
  'Onyx Black': ['#4d5254', '#313638'],
  'Orange': ['#d19a3a', '#c06f47'],
  'Pacific Cyan': ['#5abea6', '#3d95ba'],
  'Pacific Green': ['#6fc793', '#3b9c84'],
  'Persimmon': ['#e7a75a', '#c5675f'],
  'Pine Green': ['#6ba97c', '#3e7970'],
  'Pistachio': ['#97b07c', '#5c814c'],
  'Platinum': ['#b2aea7', '#88847e'],
  'Pure Gold': ['#ccab41', '#987b32'],
  'Purple': ['#ae6cae', '#844784'],
  'Ranger Green': ['#5f7849', '#3c4f3b'],
  'Raspberry': ['#e07b85', '#b65980'],
  'Rifle Green': ['#64695c', '#4b5241'],
  'Roman Silver': ['#a3a8b5', '#7c808a'],
  'Rosewood': ['#b77a77', '#814c52'],
  'Sapphire': ['#58a3c8', '#5379c2'],
  'Satin Gold': ['#bf9b47', '#8d7739'],
  'Seal Brown': ['#664d45', '#47362e'],
  'Shamrock Green': ['#8ab163', '#559345'],
  'Silver Blue': ['#80a4b8', '#607c91'],
  'Sky Blue': ['#58b4c8', '#538bc2'],
  'Steel Grey': ['#97a2ac', '#63727c'],
  'Strawberry': ['#dd8e6f', '#b75a60'],
  'Tactical Pine': ['#44826b', '#2f6369'],
  'Tomato': ['#e6793e', '#d44e3f'],
  'Turquoise': ['#5ec0b8', '#3d928e']
};

/* BACKDROP / COLOR SELECTION WITH COLOR PREVIEWS */
async function loadAndRenderBackdrops() {
  const collection = el("collectionInput")?.value?.trim() || "";
  const menu = el("backdropMenu");
  if (!menu) return;

  let backdrops = state.catalog.backdrops_by_collection?.[collection];
  if (!Array.isArray(backdrops) || backdrops.length === 0 || (backdrops[0] && typeof backdrops[0] === "string")) {
    if (collection) {
      try {
        const data = await requestJson(`/api/v1/catalog/backdrops?collection=${encodeURIComponent(collection)}`);
        backdrops = data.backdrops || [];
        state.catalog.backdrops_by_collection = { ...(state.catalog.backdrops_by_collection || {}), [collection]: backdrops };
      } catch (_) {
        backdrops = [];
      }
    } else {
      backdrops = [];
    }
  }

  renderBackdropMenu(backdrops);
}

function renderBackdropMenu(backdrops) {
  const menu = el("backdropMenu");
  const input = el("backdropInput");
  if (!menu || !input) return;

  const query = input.value.trim().toLowerCase();

  const items = [
    { name: "", title: "Любой фон", isAny: true },
    ...(backdrops || []).map(b => {
      const name = typeof b === "string" ? b : b.name;
      let center = typeof b === "object" ? b.center_color : null;
      let edge = typeof b === "object" ? b.edge_color : null;
      if (!center && TELEGRAM_BACKDROP_COLORS[name]) {
        center = TELEGRAM_BACKDROP_COLORS[name][0];
        edge = TELEGRAM_BACKDROP_COLORS[name][1];
      }
      return { name, title: name, center_color: center, edge_color: edge };
    })
  ];

  const filtered = items.filter(item => item.isAny || item.title.toLowerCase().includes(query));

  if (!filtered.length) {
    menu.innerHTML = '<div style="padding:10px 16px;font-size:13px;color:var(--ink-muted);">Ничего не найдено</div>';
    return;
  }

  menu.replaceChildren(
    ...filtered.map((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pickerOption colorOption";
      btn.setAttribute("role", "option");
      const isSelected = item.isAny ? !input.value : input.value === item.name;
      btn.setAttribute("aria-selected", String(isSelected));

      let swatchHtml = "";
      if (item.isAny) {
        swatchHtml = `<span class="colorSwatch" style="background:var(--surface-soft);border:1px solid var(--border-strong);display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--ink-muted);">✕</span>`;
      } else if (item.center_color && item.edge_color) {
        swatchHtml = `<span class="colorSwatch" style="background:radial-gradient(circle at center, ${escapeHtml(item.center_color)} 0%, ${escapeHtml(item.edge_color)} 100%);"></span>`;
      } else if (item.center_color) {
        swatchHtml = `<span class="colorSwatch" style="background:${escapeHtml(item.center_color)};"></span>`;
      } else {
        swatchHtml = `<span class="colorSwatch" style="background:var(--surface-soft);border:1px solid var(--border-strong);"></span>`;
      }

      btn.innerHTML = `
        <span class="colorName">${escapeHtml(item.title)}</span>
        ${swatchHtml}
      `;

      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        input.value = item.isAny ? "" : item.name;
        menu.hidden = true;
        updateRuleSummary();
      });

      return btn;
    })
  );
}

/* MODEL SELECTION WITH SEARCH & GRID */
async function loadAndRenderModels() {
  const collection = el("collectionInput")?.value?.trim() || "";
  const grid = el("modelGrid");
  if (!grid) return;

  grid.innerHTML = '<div class="loadingModels">Загрузка моделей...</div>';

  let models = state.catalog.models_by_collection?.[collection];
  if (!Array.isArray(models) || models.length === 0) {
    try {
      const data = await requestJson(`/api/v1/catalog/models?collection=${encodeURIComponent(collection)}`);
      models = data.models || [];
      state.catalog.models_by_collection = { ...(state.catalog.models_by_collection || {}), [collection]: models };
    } catch (_) {
      models = [];
    }
  }

  renderModelGrid(models);
}

function renderModelGrid(models) {
  const grid = el("modelGrid");
  const label = el("selectedModelLabel");
  if (!grid) return;

  const query = state.modelSearchQuery.trim().toLowerCase();
  const currentSelected = state.selectedModel;

  if (label) {
    label.textContent = currentSelected ? currentSelected : "Любая модель (без ограничений)";
  }

  // Model items array: first element is "Any model" option
  const allItems = [
    { name: "", title: "Любая модель", photo_url: null, isAny: true },
    ...(models || []).map(m => typeof m === "string" ? { name: m, title: m, photo_url: null } : { name: m.name, title: m.name, photo_url: m.photo_url })
  ];

  const filtered = allItems.filter(item => item.isAny || item.title.toLowerCase().includes(query));

  if (!filtered.length) {
    grid.innerHTML = '<div class="emptyModels">nothing found</div>';
    return;
  }

  grid.replaceChildren(
    ...filtered.map((item) => {
      const card = document.createElement("button");
      card.type = "button";
      const isSelected = item.isAny ? !currentSelected : currentSelected === item.name;
      card.className = `modelCard ${isSelected ? "selected" : ""}`;

      let mediaHtml = "";
      if (item.isAny) {
        mediaHtml = `<div class="modelPlaceholderAny">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
            <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
            <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
            <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
          </svg>
        </div>`;
      } else {
        const photoUrl = getModelPhotoUrl(item);
        if (photoUrl) {
          mediaHtml = `<img src="${escapeHtml(photoUrl)}" alt="${escapeHtml(item.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none';if(this.nextElementSibling)this.nextElementSibling.style.display='flex';" /><div class="modelPlaceholder" style="display:none;">${escapeHtml(item.title.slice(0, 2).toUpperCase())}</div>`;
        } else {
          mediaHtml = `<div class="modelPlaceholder">${escapeHtml(item.title.slice(0, 2).toUpperCase())}</div>`;
        }
      }

      card.innerHTML = `
        <div class="modelThumb">${mediaHtml}</div>
        <span class="modelTitle">${escapeHtml(item.title)}</span>
      `;

      card.addEventListener("click", () => {
        state.selectedModel = item.isAny ? "" : item.name;
        renderModelGrid(models);
        updateRuleSummary();
        setWizardStep(3);
      });

      return card;
    })
  );
}

/* RENDER FUNCTIONS */
function renderBotControl() {
  const badge = el("botStatusBadge");
  const button = el("botToggleButton");
  if (!badge || !button) return;

  const paused = state.bot.paused;
  badge.textContent = paused ? "На паузе" : "Автопокупка активна";
  badge.className = `statusBadge ${paused ? "paused" : "active"}`;
  button.textContent = paused ? "Запустить автопокупку" : "Приостановить";
  button.className = paused ? "secondaryButton botToggleBtn" : "secondaryButton botToggleBtn active";
}

function renderRules() {
  const rules = state.rules || [];
  const container = el("rulesList");
  if (!container) return;

  el("ruleListCountBadge").textContent = String(rules.length);

  if (!rules.length) {
    container.innerHTML = `
      <div class="empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
        <h3>У вас пока нет правил автопокупки</h3>
        <p>Создайте правило, чтобы бот автоматически отслеживал и выкупал подходящие подарки.</p>
        <button class="primaryGradientBtn openAddRuleBtn" type="button" style="margin-top:8px;">Добавить первое правило</button>
      </div>
    `;
    container.querySelector(".openAddRuleBtn")?.addEventListener("click", openAddRulePage);
    return;
  }

  container.replaceChildren(
    ...rules.map((rule) => {
      const card = document.createElement("article");
      card.className = "ruleCard";
      const modelText = rule.model ? rule.model : "Любая модель";
      const backdropText = rule.backdrop ? ` · ${rule.backdrop}` : "";
      const marketText = rule.market ? rule.market.toUpperCase() : "Все маркетплейсы";

      card.innerHTML = `
        <div class="ruleCardHeader">
          <div>
            <div class="ruleCardTitle">${escapeHtml(rule.collection)}</div>
            <div class="ruleCardSub">${escapeHtml(modelText)}${escapeHtml(backdropText)}</div>
          </div>
          <span class="ruleCardBadge">${escapeHtml(marketText)}</span>
        </div>
        <dl class="ruleCardBody">
          <div class="ruleCardStat">
            <dt>Макс. цена</dt>
            <dd>${formatTon(rule.max_price_ton)}</dd>
          </div>
          <div class="ruleCardStat">
            <dt>Расход / Лимит</dt>
            <dd>${formatTon(rule.spent_ton)}${rule.max_spend_ton ? ` / ${formatTon(rule.max_spend_ton)}` : ""}</dd>
          </div>
        </dl>
        <div class="ruleCardFooter">
          <label class="toggleSwitch">
            <input type="checkbox" class="toggleRuleButton" data-rule-id="${rule.id}" ${rule.enabled ? "checked" : ""} />
            <span>${rule.enabled ? "Включено" : "Выключено"}</span>
          </label>
          <button class="dangerButton deleteRuleButton" data-rule-id="${rule.id}" type="button">Удалить</button>
        </div>
      `;
      return card;
    })
  );
}

function filteredGifts() {
  const query = (el("giftSearchInput")?.value || "").trim().toLowerCase();
  const market = el("giftMarketFilter")?.value || "";
  return (state.gifts || []).filter((gift) => {
    const textMatch = !query || [gift.title, gift.collection, gift.model, gift.backdrop, gift.symbol].some((f) => String(f || "").toLowerCase().includes(query));
    const marketMatch = !market || gift.market === market;
    return textMatch && marketMatch;
  });
}

function renderGifts() {
  const gifts = filteredGifts();
  const grid = el("savedGiftsList");
  if (!grid) return;

  el("savedGiftCountBadge").textContent = String(gifts.length);
  const archiveAllBtn = el("archiveAllGiftsButton");
  if (archiveAllBtn) archiveAllBtn.disabled = !state.gifts.length;

  if (!gifts.length) {
    grid.innerHTML = `
      <div class="empty giftsEmpty">
        <h3>${state.gifts.length ? "По фильтрам ничего не найдено" : "Купленных подарков пока нет"}</h3>
        <p>${state.gifts.length ? "Попробуйте изменить поисковый запрос." : "Как только бот выкупит подарок по вашему правилу, он появится здесь."}</p>
      </div>
    `;
    return;
  }

  grid.replaceChildren(
    ...gifts.map((gift) => {
      const title = displayText(gift.title, displayText(gift.collection, "Подарок"));
      const collection = displayText(gift.collection, "Подарок");
      const card = document.createElement("article");
      card.className = "giftCard";
      const image = gift.photo_url
        ? `<img src="${escapeHtml(formatImageUrl(gift.photo_url))}" alt="${escapeHtml(title)}" width="480" height="400" loading="lazy" referrerpolicy="no-referrer">`
        : `<span>${escapeHtml(collection.slice(0, 2).toUpperCase())}</span>`;

      card.innerHTML = `
        <div class="giftImage">${image}<small>${escapeHtml(gift.market)}</small></div>
        <div class="giftBody">
          <h3>${escapeHtml(title)}</h3>
          <p>${escapeHtml(displayText(gift.model, "Без модели"))} · ${escapeHtml(displayText(gift.backdrop, "Без фона"))}</p>
          <strong>${formatTon(gift.price_ton)}</strong>
          <p class="muted">Правило: ${escapeHtml(displayText(gift.rule_collection, collection))} · ${relativeTime(gift.saved_at)}</p>
          <button class="detailsButton" data-gift-id="${gift.id}" type="button">Подробнее</button>
        </div>
      `;
      return card;
    })
  );
}

function render() {
  renderBotControl();
  renderRules();
  renderGifts();
  renderCollectionSelection();
  updateRuleSummary();
}

function updateRuleSummary() {
  const collection = el("collectionInput")?.value || "выбранной коллекции";
  const model = state.selectedModel ? ` (${state.selectedModel})` : "";
  const price = Number(el("maxPriceInput")?.value);
  const spend = Number(el("maxSpendInput")?.value);
  const summaryEl = el("ruleSummary");
  if (!summaryEl) return;

  summaryEl.textContent = price > 0
    ? `Выкупить лот «${collection}»${model} по цене до ${formatTon(price)}${spend > 0 ? ` · общий лимит ${formatTon(spend)}` : ""}.`
    : "Выберите подарок на шаге 1 и укажите максимальную цену.";
}

function showToast(message, error = false) {
  const toast = el("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast ${error ? "error" : ""}`;
  toast.hidden = false;
  setTimeout(() => { toast.hidden = true; }, 3200);
}

function openConfirm(action, title, text, label) {
  state.confirmAction = action;
  state.lastFocused = document.activeElement;
  el("confirmTitle").textContent = title;
  el("confirmText").textContent = text;
  el("confirmActionButton").textContent = label;
  el("confirmModal").hidden = false;
  setTimeout(() => el("confirmActionButton")?.focus(), 0);
}

function closeConfirm() {
  el("confirmModal").hidden = true;
  state.confirmAction = null;
  state.lastFocused?.focus?.();
}

function openGiftDetails(giftId) {
  const gift = state.gifts.find((i) => String(i.id) === String(giftId));
  if (!gift) return;
  state.selectedGift = gift;
  state.lastFocused = document.activeElement;
  const title = displayText(gift.title, displayText(gift.collection, "Подарок"));
  const collection = displayText(gift.collection, "Подарок");
  const image = gift.photo_url ? `<img class="detailsImage" src="${escapeHtml(formatImageUrl(gift.photo_url))}" alt="${escapeHtml(title)}" width="640" height="400" referrerpolicy="no-referrer">` : "";
  const links = [[gift.tg_link, "Открыть в Telegram"], [gift.market_link, "Открыть на маркетплейсе"]]
    .filter(([url]) => safeUrl(url))
    .map(([url, label]) => `<a class="secondaryButton detailLink" href="${escapeHtml(safeUrl(url))}" target="_blank" rel="noreferrer">${label}</a>`)
    .join("");

  el("giftDetailsContent").innerHTML = `
    ${image}
    <div class="detailsTitle"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(collection)} · №${gift.gift_number || "—"}</p></div>
    <dl class="properties">
      <div><dt>Цена выкупа</dt><dd>${formatTon(gift.price_ton)}</dd></div>
      <div><dt>Floor price</dt><dd>${gift.floor_gift_ton ? formatTon(gift.floor_gift_ton) : "Нет данных"}</dd></div>
      <div><dt>Модель</dt><dd>${escapeHtml(displayText(gift.model))}</dd></div>
      <div><dt>Редкость модели</dt><dd>${rarity(gift.model_rarity)}</dd></div>
      <div><dt>Фон</dt><dd>${escapeHtml(displayText(gift.backdrop))}</dd></div>
      <div><dt>Редкость фона</dt><dd>${rarity(gift.backdrop_rarity)}</dd></div>
      <div><dt>Символ</dt><dd>${escapeHtml(displayText(gift.symbol))}</dd></div>
      <div><dt>Редкость символа</dt><dd>${rarity(gift.symbol_rarity)}</dd></div>
      <div><dt>Правило</dt><dd>${escapeHtml(displayText(gift.rule_collection, collection))}</dd></div>
      <div><dt>Сохранено</dt><dd>${relativeTime(gift.saved_at)}</dd></div>
    </dl>
    <div class="detailLinks">${links || '<span class="muted">Ссылка на лот недоступна.</span>'}</div>
  `;
  el("giftDetailsModal").hidden = false;
  setTimeout(() => el("closeGiftDetailsButton")?.focus(), 0);
}

function closeGiftDetails() {
  el("giftDetailsModal").hidden = true;
  state.selectedGift = null;
  state.lastFocused?.focus?.();
}

async function createRule(event) {
  event.preventDefault();
  const collection = el("collectionInput").value.trim();
  const maxPrice = Number(el("maxPriceInput").value);
  const knownCollections = (state.catalog.collections || []).map(c => typeof c === "string" ? c : c.name);
  const knownCollection = knownCollections.includes(collection);

  el("collectionError").textContent = !collection ? "Выберите коллекцию." : !knownCollection ? "Выберите вариант из списка." : "";
  el("priceError").textContent = maxPrice > 0 ? "" : "Укажите цену больше нуля.";

  if (!knownCollection) {
    setWizardStep(1);
    return;
  }
  if (!(maxPrice > 0)) {
    setWizardStep(3);
    return;
  }

  const button = el("saveRuleButton");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Сохранение...";

  try {
    await requestJson("/api/v1/rules", {
      method: "POST",
      body: JSON.stringify({
        user_id: state.userId,
        collection,
        model: state.selectedModel || null,
        backdrop: el("backdropInput")?.value || null,
        market: el("marketInput")?.value || null,
        max_price_ton: maxPrice,
        max_spend_ton: el("maxSpendInput")?.value ? Number(el("maxSpendInput").value) : null,
        enabled: true
      })
    });
    resetWizard();
    switchTab("rules");
    showToast("Правило сохранено. Запустите автопокупку, когда будете готовы.");
    await loadAll({ silent: true });
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

async function toggleBot() {
  if (state.bot.paused) {
    try {
      await requestJson("/api/v1/bot-status/pause", { method: "PUT", body: JSON.stringify({ paused: false }) });
      showToast("Автопокупка включена.");
      await loadAll({ silent: true });
    } catch (error) { showToast(error.message, true); }
    return;
  }
  openConfirm(async () => {
    await requestJson("/api/v1/bot-status/pause", { method: "PUT", body: JSON.stringify({ paused: true }) });
    showToast("Автопокупка приостановлена.");
    await loadAll({ silent: true });
  }, "Приостановить автопокупку?", "Новые покупки не будут совершаться до следующего запуска.", "Приостановить");
}

async function toggleRule(ruleId, enabled) {
  try {
    await requestJson(`/api/v1/rules/${ruleId}/enabled?user_id=${state.userId}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
    await loadAll({ silent: true });
  } catch (error) { showToast(error.message, true); }
}

function deleteRule(ruleId) {
  openConfirm(async () => {
    await requestJson(`/api/v1/rules/${ruleId}?user_id=${state.userId}`, { method: "DELETE" });
    showToast("Правило удалено.");
    await loadAll({ silent: true });
  }, "Удалить правило?", "Сохранённые совпадения останутся в истории.", "Удалить");
}

function archiveAllGifts() {
  const giftsToArchive = filteredGifts();
  if (!giftsToArchive.length) return;
  openConfirm(async () => {
    state.gifts = [];
    renderGifts();
    try {
      await requestJson("/api/v1/saved-gifts/archive-all", { method: "POST" });
      showToast("Все купленные подарки перенесены в архив.");
    } catch (error) { showToast(error.message, true); }
    finally { await loadAll({ silent: true }); }
  }, "Архивировать купленные подарки?", "Все текущие подарки будут перенесены в архив.", "Архивировать");
}

/* INITIALIZATION */
async function initializeApp() {
  try {
    const devInfo = await fetch("/api/v1/dev-mode").then(r => r.ok ? r.json() : null);
    if (devInfo?.dev) {
      state.devMode = true;
      state.userId = 0;
    }
  } catch (_) {}

  const initData = telegramInitData();
  const hasTelegram = !!(initData || location.search.includes("tgWebAppData") || location.hash.includes("tgWebAppData"));

  if (!hasTelegram && !state.devMode) {
    renderAccessDenied("Приложение доступно только через Telegram Mini App для авторизованных пользователей.");
    return;
  }

  if (!state.devMode) {
    state.userId = telegramUserId();
  }

  initializeTheme();

  if (state.devMode) {
    const topbarActions = document.querySelector(".topbarActions");
    if (topbarActions) {
      const devBadge = document.createElement("div");
      devBadge.className = "devModeBadge";
      devBadge.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg> DEV';
      devBadge.title = "Dev-режим активен (user_id=0). Telegram не требуется.";
      topbarActions.prepend(devBadge);
    }
  }

  // Tab Listeners (Rules & Gifts)
  el("tabRulesBtn")?.addEventListener("click", () => switchTab("rules"));
  el("tabGiftsBtn")?.addEventListener("click", () => switchTab("gifts"));

  // Add rule navigation listeners
  el("openAddRulePageButton")?.addEventListener("click", openAddRulePage);
  el("backToRulesBtn")?.addEventListener("click", () => switchTab("rules"));
  el("cancelAddRuleBtn")?.addEventListener("click", () => switchTab("rules"));

  // Progress bar step navigation
  document.querySelectorAll(".wizardStepLabel").forEach((btn) => {
    btn.addEventListener("click", () => {
      const step = Number(btn.dataset.step);
      const collection = el("collectionInput")?.value?.trim();
      if (step >= 2 && !collection) {
        showToast("Сначала выберите коллекцию", true);
        return;
      }
      setWizardStep(step);
    });
  });

  // Model search input
  el("modelSearchInput")?.addEventListener("input", (e) => {
    state.modelSearchQuery = e.target.value;
    const collection = el("collectionInput")?.value?.trim() || "";
    const models = state.catalog.models_by_collection?.[collection] || [];
    renderModelGrid(models);
  });

  // Collection input listener
  el("collectionInput")?.addEventListener("input", () => {
    renderCollectionSelection();
    updateRuleSummary();
  });

  // Theme & Bot Toggle Listeners
  el("themeToggle")?.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("giftify-theme", theme);
    applyTheme(theme);
  });

  el("ruleForm")?.addEventListener("submit", createRule);
  el("botToggleButton")?.addEventListener("click", toggleBot);
  el("cancelConfirmButton")?.addEventListener("click", closeConfirm);
  el("confirmActionButton")?.addEventListener("click", async () => {
    const action = state.confirmAction;
    closeConfirm();
    try { await action?.(); } catch (error) { showToast(error.message, true); }
  });

  el("confirmModal")?.addEventListener("click", (e) => { if (e.target === el("confirmModal")) closeConfirm(); });
  el("giftDetailsModal")?.addEventListener("click", (e) => { if (e.target === el("giftDetailsModal")) closeGiftDetails(); });
  el("closeGiftDetailsButton")?.addEventListener("click", closeGiftDetails);

  el("rulesList")?.addEventListener("click", (e) => {
    const toggle = e.target.closest(".toggleRuleButton");
    if (toggle) toggleRule(toggle.dataset.ruleId, toggle.checked);
    const remove = e.target.closest(".deleteRuleButton");
    if (remove) deleteRule(remove.dataset.ruleId);
  });

  el("savedGiftsList")?.addEventListener("click", (e) => {
    const detailsBtn = e.target.closest(".detailsButton");
    if (detailsBtn) openGiftDetails(detailsBtn.dataset.giftId);
  });

  el("archiveAllGiftsButton")?.addEventListener("click", archiveAllGifts);

  for (const id of ["maxPriceInput", "maxSpendInput"]) el(id)?.addEventListener("input", updateRuleSummary);

  for (const id of ["giftSearchInput", "giftMarketFilter"]) el(id)?.addEventListener("input", renderGifts);

  // Backdrop picker listeners
  const backdropInput = el("backdropInput");
  const backdropMenu = el("backdropMenu");
  const pickerToggle = document.querySelector('.pickerToggle[data-picker="backdrop"]');

  if (backdropInput && backdropMenu) {
    const showMenu = () => {
      backdropMenu.hidden = false;
      loadAndRenderBackdrops();
    };

    backdropInput.addEventListener("focus", showMenu);
    backdropInput.addEventListener("click", showMenu);
    backdropInput.addEventListener("input", () => {
      backdropMenu.hidden = false;
      loadAndRenderBackdrops();
    });

    pickerToggle?.addEventListener("click", (e) => {
      e.stopPropagation();
      backdropMenu.hidden = !backdropMenu.hidden;
      if (!backdropMenu.hidden) loadAndRenderBackdrops();
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest('.optionPicker[data-picker-name="backdrop"]')) {
        backdropMenu.hidden = true;
      }
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (backdropMenu && !backdropMenu.hidden) backdropMenu.hidden = true;
    else if (!el("giftDetailsModal")?.hidden) closeGiftDetails();
    else if (!el("confirmModal")?.hidden) closeConfirm();
  });

  loadAll().catch((error) => renderAccessDenied(error.message));
}

// Boot
initializeTheme();
initializeApp();
