const DATA = {};
const state = {
  route: 'overview',
  queries: { agencies: '', brands: '', relationships: '', sources: '' },
  category: 'all',
  quality: 'all',
  agency: 'all',
  relationship: 'all',
  sourceStatus: 'all',
  limit: 300,
};

const routes = [
  ['overview', 'Overview'],
  ['agencies', 'Agencies'],
  ['brands', 'Brands & properties'],
  ['relationships', 'Agency–brand links'],
  ['sources', 'Sources & failures'],
  ['database', 'Database'],
];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));
const fmt = (value) => new Intl.NumberFormat('en-US').format(Number(value || 0));
const pct = (value) => `${Math.round(Number(value || 0) * 100)}%`;
const pretty = (value) => String(value || 'unknown').replaceAll('_', ' ');
const date = (value) => value
  ? new Date(value).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
  : '—';
const pill = (value) => `<span class="pill ${esc(value)}">${esc(pretty(value))}</span>`;
const safeHost = (value) => {
  try { return new URL(value).hostname; } catch { return value || ''; }
};
const parseList = (value) => {
  if (Array.isArray(value)) return value;
  try {
    const parsed = JSON.parse(value || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch { return []; }
};
const documentedBrandCount = () => Number(DATA.meta.clean_high_confidence_brands || 0)
  + Number(DATA.meta.clean_documented_brands || 0);

function renderNav() {
  for (const id of ['nav', 'mobile-nav']) {
    const node = $(`#${id}`);
    if (!node) continue;
    node.innerHTML = routes.map(([key, label]) => (
      `<button data-route="${key}" class="${state.route === key ? 'active' : ''}">${label}</button>`
    )).join('');
  }
}

function go(route) {
  state.route = routes.some(([key]) => key === route) ? route : 'overview';
  $$('.route').forEach((node) => node.classList.toggle('active', node.id === `route-${state.route}`));
  renderNav();
  renderRoute(state.route);
  history.replaceState(null, '', `#${state.route}`);
}

function intro(eyebrow, title, lede) {
  return `<div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p class="lede">${esc(lede)}</p>`;
}

function metricCards() {
  const m = DATA.meta;
  const entries = [
    ['Licensing agencies', m.clean_agencies],
    ['Documented brands', documentedBrandCount()],
    ['Agency–brand links', m.clean_relationships],
    ['Pages captured', m.pages_captured],
    ['Clean evidence records', m.clean_evidence_records],
    ['Registered sources', m.registered_sources],
  ];
  return `<div class="metrics">${entries.map(([label, value]) => (
    `<div class="metric"><div class="n">${fmt(value)}</div><div class="l">${esc(label)}</div></div>`
  )).join('')}</div>`;
}

function cap(items) {
  return { rows: items.slice(0, state.limit), total: items.length };
}

function resultCount(total, shown) {
  return `<span class="pill">${fmt(total)} matched${shown < total ? ` · first ${fmt(shown)} shown` : ''}</span>`;
}

function qualityOrder(a, b) {
  return Number(b.quality_score || 0) - Number(a.quality_score || 0)
    || Number(b.evidence_count || 0) - Number(a.evidence_count || 0)
    || Number(b.agency_count || 0) - Number(a.agency_count || 0)
    || String(a.canonical_name || '').localeCompare(String(b.canonical_name || ''));
}

function brandTable(items) {
  return `<table><thead><tr>
    <th>Brand / property</th><th>Category</th><th>Quality</th><th>Agencies</th>
    <th>Evidence</th><th>First-party evidence</th><th>Sources</th>
  </tr></thead><tbody>${items.map((item) => `<tr data-brand-id="${item.id}">
    <td><div class="name">${esc(item.canonical_name)}</div>${item.website
      ? `<a class="small link" target="_blank" rel="noopener" href="${esc(item.website)}" onclick="event.stopPropagation()">${esc(safeHost(item.website))}</a>`
      : ''}</td>
    <td>${pill(item.category || 'other')}</td>
    <td>${pill(item.quality_status)} <span class="score">${pct(item.quality_score)}</span></td>
    <td><b>${fmt(item.agency_count)}</b></td>
    <td>${fmt(item.evidence_count)}</td>
    <td>${fmt(item.first_party_evidence_count)}</td>
    <td>${fmt(item.source_count)}</td>
  </tr>`).join('')}</tbody></table>`;
}

function agencyTable(items) {
  return `<table><thead><tr>
    <th>Agency</th><th>Region</th><th>Focus</th><th>Brands found</th>
    <th>First-party portfolio</th><th>Agent list</th><th>Sources</th><th>Website</th>
  </tr></thead><tbody>${items.map((item) => `<tr data-agency-id="${item.id}">
    <td><div class="name">${esc(item.canonical_name)}</div><div class="small">${esc(item.country || '')}</div></td>
    <td>${esc(item.region || '—')}</td>
    <td class="small">${esc(item.description || '—')}</td>
    <td><b>${fmt(item.represented_brand_count)}</b></td>
    <td>${fmt(item.first_party_brand_count)}</td>
    <td>${fmt(item.agent_list_brand_count)}</td>
    <td>${fmt(item.source_count)}</td>
    <td>${item.website
      ? `<a class="link" target="_blank" rel="noopener" href="${esc(item.website)}" onclick="event.stopPropagation()">Open</a>`
      : '—'}</td>
  </tr>`).join('')}</tbody></table>`;
}

function renderOverview() {
  const m = DATA.meta;
  const categories = {};
  DATA.brands.forEach((item) => {
    const key = item.category || 'other';
    categories[key] = (categories[key] || 0) + 1;
  });
  const maxCategory = Math.max(1, ...Object.values(categories));
  const strongest = [...DATA.brands].sort(qualityOrder).slice(0, 30);
  const failed = DATA.sources.filter((item) => item.status !== 'complete');

  $('#route-overview').innerHTML = `
    ${intro(
      'Live research corpus',
      'Licensing-market database',
      'This interface is reading the populated crawl and deterministic clean layer. It does not use the withdrawn Top 50 or browser-local seed data.',
    )}
    ${metricCards()}
    <div class="notice"><b>Coverage:</b> ${esc(m.scope)} ${esc(m.completeness_caveat)}</div>
    <section class="panel">
      <div class="panel-head"><div><h2>Raw crawl → clean discovery layer</h2><p>The complete raw material remains in SQLite. Obvious navigation, country, font, page-metadata and article-headline noise is excluded from the clean tables.</p></div></div>
      <div class="source-cards">
        ${[
          ['Raw extracted strings', m.raw_brand_strings],
          ['Clean candidate records', m.clean_brands],
          ['Documented / high confidence', documentedBrandCount()],
          ['Review queue', m.clean_review_brands],
          ['Rejected or unresolved', m.rejected_or_unresolved_brand_strings],
          ['Raw evidence retained', m.raw_evidence_records],
        ].map(([label, value]) => `<div class="source-card"><div class="count">${fmt(value)}</div><div class="small">${esc(label)}</div></div>`).join('')}
      </div>
    </section>
    <div class="grid2">
      <section class="panel">
        <div class="panel-head"><div><h2>Documented brands by category</h2><p>Deterministic topic classification for triage, not an AI judgment of commercial fit.</p></div></div>
        <div class="bars">${Object.entries(categories).sort((a, b) => b[1] - a[1]).map(([key, value]) => `
          <div class="bar-row"><span>${esc(pretty(key))}</span><div class="bar-track"><div class="bar-fill" style="width:${value / maxCategory * 100}%"></div></div><b>${fmt(value)}</b></div>
        `).join('')}</div>
      </section>
      <section class="panel">
        <div class="panel-head"><div><h2>Acquisition audit</h2><p>Failed and gated sources remain visible in the denominator.</p></div></div>
        <div class="source-cards">
          ${[
            ['Complete sources', m.sources_complete],
            ['Failed sources', m.sources_failed],
            ['Gated / skipped', m.sources_skipped_gated],
            ['Pages captured', m.pages_captured],
            ['Conference records', m.raw_conference_records],
            ['Clean agency links', m.clean_relationships],
          ].map(([label, value]) => `<div class="source-card"><div class="count">${fmt(value)}</div><div class="small">${esc(label)}</div></div>`).join('')}
        </div>
      </section>
    </div>
    <section class="panel">
      <div class="panel-head"><div><h2>Highest-confidence extracted properties</h2><p>Ordered by evidence quality and volume. This is not the final Leatherback opportunity ranking.</p></div><button class="button" data-jump="brands">Open all</button></div>
      <div class="table-wrap" style="max-height:560px">${brandTable(strongest)}</div>
    </section>
    <p class="footer-note">Generated ${date(m.generated_at)}. ${fmt(failed.length)} registered sources did not complete; their URLs and errors are retained under Sources & failures.</p>`;
}

function renderAgencies() {
  const query = state.queries.agencies.trim().toLowerCase();
  const matched = DATA.agencies.filter((item) => !query || [
    item.canonical_name, item.region, item.country, item.description, item.website,
  ].join(' ').toLowerCase().includes(query));
  const { rows, total } = cap(matched);
  $('#route-agencies').innerHTML = `
    ${intro('Rights representation', 'Licensing agencies', 'The agency layer is deduplicated from registered portfolios and discovered agency listings. Click a row to inspect its extracted portfolio.')}
    <div class="toolbar"><input class="input" id="agency-q" value="${esc(state.queries.agencies)}" placeholder="Search agency, region or focus">${resultCount(total, rows.length)}</div>
    <section class="panel"><div class="table-wrap">${agencyTable(rows)}</div></section>`;
}

function renderBrands() {
  const categories = ['all', ...new Set(DATA.brands.map((item) => item.category || 'other'))].sort();
  const qualities = ['all', 'high_confidence', 'documented'];
  const query = state.queries.brands.trim().toLowerCase();
  const agencyNamesByBrand = DATA.agencyNamesByBrand;
  const matched = DATA.brands.filter((item) => (
    (state.category === 'all' || item.category === state.category)
    && (state.quality === 'all' || item.quality_status === state.quality)
    && (!query || [
      item.canonical_name, item.category, item.website,
      ...(agencyNamesByBrand.get(Number(item.id)) || []),
    ].join(' ').toLowerCase().includes(query))
  )).sort(qualityOrder);
  const { rows, total } = cap(matched);
  $('#route-brands').innerHTML = `
    ${intro('Clean discovery corpus', 'Brands & properties', 'These records survived deterministic quality filtering and have stored agency or source evidence. Legal availability of travel rights still requires direct verification.')}
    <div class="toolbar">
      <input class="input" id="brand-q" value="${esc(state.queries.brands)}" placeholder="Search brand or representing agency">
      <select class="select" id="brand-cat">${categories.map((value) => `<option value="${esc(value)}" ${value === state.category ? 'selected' : ''}>${esc(pretty(value))}</option>`).join('')}</select>
      <select class="select" id="brand-quality">${qualities.map((value) => `<option value="${esc(value)}" ${value === state.quality ? 'selected' : ''}>${esc(pretty(value))}</option>`).join('')}</select>
      ${resultCount(total, rows.length)}
    </div>
    <section class="panel"><div class="table-wrap">${brandTable(rows)}</div></section>`;
}

function firstSourceUrl(item) {
  return parseList(item.source_urls)[0] || '';
}

function renderRelationships() {
  const agencies = ['all', ...new Set(DATA.reps.map((item) => item.agency_name).filter(Boolean))].sort();
  const relationships = ['all', ...new Set(DATA.reps.map((item) => item.relationship_status).filter(Boolean))].sort();
  const query = state.queries.relationships.trim().toLowerCase();
  const matched = DATA.reps.filter((item) => (
    (state.agency === 'all' || item.agency_name === state.agency)
    && (state.relationship === 'all' || item.relationship_status === state.relationship)
    && (!query || [item.agency_name, item.brand_name, item.category, item.relationship_status].join(' ').toLowerCase().includes(query))
  ));
  const { rows, total } = cap(matched);
  $('#route-relationships').innerHTML = `
    ${intro('Representation evidence', 'Agency–brand links', 'Each row maps an extracted property to the agency and evidence source that produced it. Portfolio presence is not treated as proof that global travel rights are available.')}
    <div class="toolbar">
      <input class="input" id="rel-q" value="${esc(state.queries.relationships)}" placeholder="Search agency or brand">
      <select class="select" id="rel-agency">${agencies.map((value) => `<option value="${esc(value)}" ${value === state.agency ? 'selected' : ''}>${esc(value)}</option>`).join('')}</select>
      <select class="select" id="rel-type">${relationships.map((value) => `<option value="${esc(value)}" ${value === state.relationship ? 'selected' : ''}>${esc(pretty(value))}</option>`).join('')}</select>
      ${resultCount(total, rows.length)}
    </div>
    <section class="panel"><div class="table-wrap"><table><thead><tr>
      <th>Agency</th><th>Brand / property</th><th>Category</th><th>Evidence type</th><th>Quality</th><th>Evidence</th>
    </tr></thead><tbody>${rows.map((item) => {
      const source = firstSourceUrl(item);
      return `<tr data-brand-id="${item.brand_id}"><td class="name">${esc(item.agency_name)}</td><td>${esc(item.brand_name)}</td><td>${pill(item.category || 'other')}</td><td class="small">${esc(pretty(item.relationship_status))}</td><td class="score">${pct(item.quality_score)}</td><td>${source ? `<a class="link" href="${esc(source)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Source</a>` : '—'}</td></tr>`;
    }).join('')}</tbody></table></div></section>`;
}

function renderSources() {
  const statuses = ['all', 'complete', 'failed', 'skipped_gated', 'pending'];
  const query = state.queries.sources.trim().toLowerCase();
  const matched = DATA.sources.filter((item) => (
    (state.sourceStatus === 'all' || item.status === state.sourceStatus)
    && (!query || [item.name, item.agency_name, item.source_type, item.region, item.error, item.crawl_url].join(' ').toLowerCase().includes(query))
  ));
  const { rows, total } = cap(matched);
  $('#route-sources').innerHTML = `
    ${intro('Acquisition audit', 'Sources & failures', 'The complete registered source universe is shown here, including failed, blocked and login-gated sources. No failed source is silently removed.')}
    <div class="toolbar">
      <input class="input" id="source-q" value="${esc(state.queries.sources)}" placeholder="Search source, agency, URL or error">
      <select class="select" id="source-status">${statuses.map((value) => `<option value="${esc(value)}" ${value === state.sourceStatus ? 'selected' : ''}>${esc(pretty(value))}</option>`).join('')}</select>
      ${resultCount(total, rows.length)}
    </div>
    <section class="panel"><div class="table-wrap"><table><thead><tr>
      <th>Source</th><th>Type</th><th>Status</th><th>Pages</th><th>Raw / promoted</th><th>HTTP</th><th>Error or note</th><th>URL</th>
    </tr></thead><tbody>${rows.map((item) => `<tr>
      <td><div class="name">${esc(item.name)}</div><div class="small">${esc(item.agency_name || item.region || '')}</div></td>
      <td class="small">${esc(pretty(item.source_type))}</td><td>${pill(item.status)}</td><td>${fmt(item.pages_fetched)}</td>
      <td>${fmt(item.raw_candidates)} / ${fmt(item.promoted_entities)}</td><td>${item.http_status || '—'}</td>
      <td class="small">${esc(item.error || item.notes || '—')}</td>
      <td><a class="link" href="${esc(item.final_url || item.crawl_url)}" target="_blank" rel="noopener">Open</a></td>
    </tr>`).join('')}</tbody></table></div></section>`;
}

function renderDatabase() {
  const files = [
    ['Clean + raw SQLite database', 'licensing_database.sqlite', 'The complete relational database: raw crawl tables plus clean_agencies, clean_brands, clean_representations and clean_evidence.'],
    ['Clean brands JSON', 'brands.json', 'High-confidence and documented properties used by this application.'],
    ['Review queue JSON', 'review_brands.json', 'Lower-confidence candidate records kept out of the main interface.'],
    ['Clean agencies JSON', 'agencies.json', 'Deduplicated agency records and extracted portfolio counts.'],
    ['Clean relationships JSON', 'representations.json', 'Agency–brand evidence links and quality scores.'],
    ['Full sources JSON', 'sources.json', 'All registered sources, statuses, URLs and crawl errors.'],
    ['AI analysis queue', 'analysis_queue.json', 'Structured clean candidates prepared for the separate AI-ranking stage.'],
    ['Brands CSV', 'brands.csv', 'Spreadsheet-friendly clean brand export.'],
    ['Relationships CSV', 'representations.csv', 'Spreadsheet-friendly clean agency–brand map.'],
    ['Quality report', 'QUALITY_REPORT.md', 'Human-readable raw-to-clean counts and methodology.'],
  ];
  $('#route-database').innerHTML = `
    ${intro('Underlying files', 'Database', 'This is a generated relational database, not mock data or local browser storage. The raw crawl and cleaned tables are kept together for auditability.')}
    ${metricCards()}
    <section class="panel"><div class="panel-head"><div><h2>Database and machine-readable exports</h2><p>Generated ${date(DATA.meta.generated_at)}</p></div></div>
      <div class="db-links">${files.map(([title, file, description]) => `<a class="db-link" href="database-v3/${file}" target="_blank"><b>${esc(title)}</b><span class="small">${esc(description)}</span></a>`).join('')}</div>
    </section>
    <section class="panel"><div class="panel-head"><div><h2>Raw crawl archive</h2><p>Uncleaned extraction layer retained for reproducibility and future parser improvements.</p></div></div>
      <div class="db-links">
        <a class="db-link" href="database-v2/CRAWL_REPORT.md" target="_blank"><b>Raw crawl report</b><span class="small">Original acquisition counts and incomplete-source audit.</span></a>
        <a class="db-link" href="database-v2/brands.json" target="_blank"><b>Raw extracted brand strings</b><span class="small">Contains noise by design; use only for parser auditing.</span></a>
        <a class="db-link" href="database-v2/representations.json" target="_blank"><b>Raw relationship extractions</b><span class="small">All promoted first-pass mappings before deterministic cleaning.</span></a>
      </div>
    </section>
    <div class="notice"><b>Ranking status:</b> ${esc(pretty(DATA.meta.ranking_status))}. The database-building step is complete. The final AI-reviewed Leatherback Top 50 is a separate stage and is not being simulated by the deterministic score fields.</div>`;
}

function renderRoute(route) {
  if (!DATA.meta) return;
  ({
    overview: renderOverview,
    agencies: renderAgencies,
    brands: renderBrands,
    relationships: renderRelationships,
    sources: renderSources,
    database: renderDatabase,
  }[route] || renderOverview)();
  bindRoute();
}

function openDrawer(content) {
  $('#drawer').innerHTML = content;
  $('#drawer-bg').classList.add('open');
}
function closeDrawer() { $('#drawer-bg').classList.remove('open'); }

function brandDetails(id) {
  const item = DATA.brandsById.get(Number(id));
  if (!item) return;
  const reps = DATA.repsByBrand.get(Number(id)) || [];
  openDrawer(`
    <button class="drawer-close" data-close>×</button><div class="eyebrow">Documented property</div>
    <h1 style="font-size:29px">${esc(item.canonical_name)}</h1>
    <p class="lede">This record survived deterministic quality filtering. It still requires direct rights verification before outreach.</p>
    <div class="detail-grid">
      <div class="detail-item"><b>Category</b>${esc(pretty(item.category))}</div>
      <div class="detail-item"><b>Evidence quality</b>${pct(item.quality_score)} · ${esc(pretty(item.quality_status))}</div>
      <div class="detail-item"><b>Evidence records</b>${fmt(item.evidence_count)}</div>
      <div class="detail-item"><b>Agencies found</b>${fmt(item.agency_count)}</div>
      <div class="detail-item"><b>First-party evidence</b>${fmt(item.first_party_evidence_count)}</div>
      <div class="detail-item"><b>Source pages</b>${fmt(item.source_count)}</div>
    </div>
    ${item.website ? `<p><a class="button primary" href="${esc(item.website)}" target="_blank" rel="noopener">Open portfolio page</a></p>` : ''}
    <h2>Agency evidence</h2><div style="margin-top:12px">${reps.length ? reps.map((rep) => {
      const source = firstSourceUrl(rep);
      return `<div class="detail-item" style="margin-bottom:8px"><b>${esc(rep.agency_name)}</b><div class="small">${esc(pretty(rep.relationship_status))} · ${pct(rep.quality_score)} evidence quality</div>${source ? `<a class="link small" target="_blank" rel="noopener" href="${esc(source)}">Open source evidence</a>` : ''}</div>`;
    }).join('') : '<div class="small">No clean agency relationship stored.</div>'}</div>
    <div class="notice"><b>Triage only:</b> The database contains a deterministic opportunity score for queue ordering, but no final commercial or AI judgment has been made.</div>`);
}

function agencyDetails(id) {
  const item = DATA.agenciesById.get(Number(id));
  if (!item) return;
  const reps = DATA.repsByAgency.get(Number(id)) || [];
  openDrawer(`
    <button class="drawer-close" data-close>×</button><div class="eyebrow">Licensing agency</div>
    <h1 style="font-size:29px">${esc(item.canonical_name)}</h1><p class="lede">${esc(item.description || 'No focus description stored.')}</p>
    <div class="detail-grid">
      <div class="detail-item"><b>Region</b>${esc(item.region || '—')}</div>
      <div class="detail-item"><b>Brands found</b>${fmt(item.represented_brand_count)}</div>
      <div class="detail-item"><b>First-party portfolio records</b>${fmt(item.first_party_brand_count)}</div>
      <div class="detail-item"><b>Agent-list records</b>${fmt(item.agent_list_brand_count)}</div>
    </div>
    ${item.website ? `<p><a class="button primary" href="${esc(item.website)}" target="_blank" rel="noopener">Open agency site</a></p>` : ''}
    <h2>Extracted clean portfolio</h2><div style="margin-top:12px">${reps.slice(0, 150).map((rep) => `<div class="detail-item" data-brand-id="${rep.brand_id}" style="margin-bottom:8px;cursor:pointer"><b>${esc(rep.brand_name)}</b><div class="small">${esc(pretty(rep.category))} · ${pct(rep.quality_score)}</div></div>`).join('') || '<div class="small">No clean portfolio records.</div>'}</div>
    ${reps.length > 150 ? `<p class="small">First 150 of ${fmt(reps.length)} relationships shown.</p>` : ''}`);
}

function debounce(handler, delay = 150) {
  let timer;
  return (event) => {
    clearTimeout(timer);
    timer = setTimeout(() => handler(event), delay);
  };
}

function bindRoute() {
  $$('[data-brand-id]').forEach((node) => { node.onclick = () => brandDetails(node.dataset.brandId); });
  $$('[data-agency-id]').forEach((node) => { node.onclick = () => agencyDetails(node.dataset.agencyId); });
  $$('[data-jump]').forEach((node) => { node.onclick = () => go(node.dataset.jump); });
  $$('[data-close]').forEach((node) => { node.onclick = closeDrawer; });

  const bindQuery = (id, key, renderer) => {
    const input = $(`#${id}`);
    if (input) input.oninput = debounce((event) => {
      state.queries[key] = event.target.value;
      renderer();
      const next = $(`#${id}`);
      if (next) { next.focus(); next.setSelectionRange(next.value.length, next.value.length); }
    });
  };
  bindQuery('agency-q', 'agencies', renderAgencies);
  bindQuery('brand-q', 'brands', renderBrands);
  bindQuery('rel-q', 'relationships', renderRelationships);
  bindQuery('source-q', 'sources', renderSources);

  const cat = $('#brand-cat'); if (cat) cat.onchange = (event) => { state.category = event.target.value; renderBrands(); };
  const quality = $('#brand-quality'); if (quality) quality.onchange = (event) => { state.quality = event.target.value; renderBrands(); };
  const agency = $('#rel-agency'); if (agency) agency.onchange = (event) => { state.agency = event.target.value; renderRelationships(); };
  const relation = $('#rel-type'); if (relation) relation.onchange = (event) => { state.relationship = event.target.value; renderRelationships(); };
  const sourceStatus = $('#source-status'); if (sourceStatus) sourceStatus.onchange = (event) => { state.sourceStatus = event.target.value; renderSources(); };
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-route]');
  if (button) go(button.dataset.route);
});
$('#drawer-bg').addEventListener('click', (event) => { if (event.target === $('#drawer-bg')) closeDrawer(); });
window.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeDrawer(); });

async function fetchJson(name) {
  const response = await fetch(`database-v3/${name}.json?v=${Date.now()}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${name}.json returned HTTP ${response.status}`);
  return response.json();
}

async function load() {
  try {
    const [meta, agencies, brands, reps, sources] = await Promise.all([
      fetchJson('metadata'), fetchJson('agencies'), fetchJson('brands'), fetchJson('representations'), fetchJson('sources'),
    ]);
    Object.assign(DATA, { meta, agencies, brands, reps, sources });
    DATA.brandsById = new Map(brands.map((item) => [Number(item.id), item]));
    DATA.agenciesById = new Map(agencies.map((item) => [Number(item.id), item]));
    DATA.repsByBrand = new Map(); DATA.repsByAgency = new Map(); DATA.agencyNamesByBrand = new Map();
    reps.forEach((item) => {
      const brandId = Number(item.brand_id); const agencyId = Number(item.agency_id);
      if (!DATA.repsByBrand.has(brandId)) DATA.repsByBrand.set(brandId, []);
      if (!DATA.repsByAgency.has(agencyId)) DATA.repsByAgency.set(agencyId, []);
      if (!DATA.agencyNamesByBrand.has(brandId)) DATA.agencyNamesByBrand.set(brandId, []);
      DATA.repsByBrand.get(brandId).push(item);
      DATA.repsByAgency.get(agencyId).push(item);
      DATA.agencyNamesByBrand.get(brandId).push(item.agency_name);
    });

    $('#loading').hidden = true;
    $('#routes').hidden = false;
    $('#routes').innerHTML = routes.map(([key]) => `<section class="route" id="route-${key}"></section>`).join('');
    $('#live-dot').classList.add('ok');
    $('#live-label').textContent = `Clean database generated ${date(meta.generated_at)}`;
    state.route = (location.hash || '#overview').slice(1);
    go(state.route);
  } catch (error) {
    $('#loading').hidden = true;
    $('#error').hidden = false;
    $('#error').className = 'error-box';
    $('#error').innerHTML = `<h2>Database unavailable</h2><p>${esc(error.message)}</p><p class="small">The application will not substitute the withdrawn Top 50 or the old seed list.</p>`;
    $('#live-dot').classList.add('bad');
    $('#live-label').textContent = 'Database load failed';
  }
}

renderNav();
load();
