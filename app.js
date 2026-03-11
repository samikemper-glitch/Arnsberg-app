const state = {
  places: [],
  items: [],
};

const els = {
  generatedAt: document.getElementById('generatedAt'),
  itemsTotal: document.getElementById('itemsTotal'),
  warningBox: document.getElementById('warningBox'),
  placeSelect: document.getElementById('placeSelect'),
  searchInput: document.getElementById('searchInput'),
  cityWideCheckbox: document.getElementById('cityWideCheckbox'),
  refreshButton: document.getElementById('refreshButton'),
  statusLine: document.getElementById('statusLine'),
  itemsList: document.getElementById('itemsList'),
  itemTemplate: document.getElementById('itemTemplate'),
};

function formatDate(value) {
  if (!value) return 'unbekannt';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'medium',
    timeStyle: value.includes('T') ? 'short' : undefined,
  }).format(date);
}

function setStatus(text) {
  els.statusLine.textContent = text;
}

async function fetchJSON(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function loadMeta() {
  const meta = await fetchJSON('/api/meta');
  els.generatedAt.textContent = meta.generated_at ? formatDate(meta.generated_at) : 'unbekannt';
  els.itemsTotal.textContent = meta.items_total ?? '–';

  if (meta.warning) {
    els.warningBox.textContent = meta.warning;
    els.warningBox.classList.remove('hidden');
  } else {
    els.warningBox.classList.add('hidden');
  }
}

async function loadPlaces() {
  state.places = await fetchJSON('/api/places');
  const current = els.placeSelect.value;
  els.placeSelect.innerHTML = '<option value="">Alle Orte</option>';

  for (const place of state.places) {
    const option = document.createElement('option');
    option.value = place;
    option.textContent = place;
    if (place === current) option.selected = true;
    els.placeSelect.appendChild(option);
  }
}

function renderItems(items) {
  els.itemsList.innerHTML = '';

  if (!items.length) {
    setStatus('Keine Einträge gefunden.');
    return;
  }

  setStatus(`${items.length} Einträge gefunden.`);

  for (const item of items) {
    const node = els.itemTemplate.content.firstElementChild.cloneNode(true);

    node.querySelector('.section-badge').textContent = item.section || 'Thema';
    const citywide = node.querySelector('.citywide-badge');
    if (item.city_wide) citywide.classList.remove('hidden');

    node.querySelector('.card-title').textContent = item.title || 'Ohne Titel';
    node.querySelector('.summary').textContent = item.citizen_summary || item.teaser || 'Keine Kurzfassung vorhanden.';
    node.querySelector('.place').textContent = Array.isArray(item.places) && item.places.length ? item.places.join(', ') : 'Unklar';
    node.querySelector('.source').textContent = item.source_name || 'Unbekannt';
    node.querySelector('.date').textContent = formatDate(item.published_at);
    node.querySelector('.teaser').textContent = item.teaser || 'Keine Zusatzinformationen.';

    const link = node.querySelector('.source-link');
    link.href = item.source_url || '#';

    els.itemsList.appendChild(node);
  }
}

async function loadItems() {
  setStatus('Lade Einträge…');

  const params = new URLSearchParams();
  if (els.placeSelect.value) params.set('ort', els.placeSelect.value);
  if (els.cityWideCheckbox.checked) params.set('stadtweit', 'true');
  if (els.searchInput.value.trim()) params.set('suche', els.searchInput.value.trim());
  params.set('limit', '200');

  const url = `/api/items?${params.toString()}`;
  state.items = await fetchJSON(url);
  renderItems(state.items);
}

let debounceTimer;
function debounceReload() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    loadItems().catch(handleError);
  }, 250);
}

async function refreshData() {
  els.refreshButton.disabled = true;
  els.refreshButton.textContent = 'Aktualisiere…';
  try {
    await fetchJSON('/api/refresh');
    await Promise.all([loadMeta(), loadPlaces(), loadItems()]);
  } finally {
    els.refreshButton.disabled = false;
    els.refreshButton.textContent = 'Aktualisieren';
  }
}

function handleError(error) {
  console.error(error);
  setStatus(`Fehler: ${error.message}`);
}

async function init() {
  els.placeSelect.addEventListener('change', () => loadItems().catch(handleError));
  els.cityWideCheckbox.addEventListener('change', () => loadItems().catch(handleError));
  els.searchInput.addEventListener('input', debounceReload);
  els.refreshButton.addEventListener('click', () => refreshData().catch(handleError));

  await Promise.all([loadMeta(), loadPlaces()]);
  await loadItems();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/service-worker.js').catch(console.error);
  }
}

init().catch(handleError);
