/* Read-only Dolci-Think comparison viewer. Plain browser JavaScript. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { data: null, selected: 0, filter: 'all' };

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function getMessage(message) {
    if (!message || typeof message !== 'object') throw new Error('Invalid message');
    const think = typeof message.think === 'string' ? message.think : '';
    const main = typeof message.main === 'string' ? message.main :
      typeof message.content === 'string' ? message.content : '';
    return { think, main };
  }

  function normalize(input) {
    let samples;
    let label;
    if (Array.isArray(input)) {
      // Raw output from the existing MN5 translation/reconstruction script.
      label = 'MN5 translations';
      samples = input.map((entry, index) => {
        const original = entry.original_messages;
        const translated = entry.translated_messages;
        if (!Array.isArray(original) || !Array.isArray(translated) ||
            original.length !== translated.length || !original.length) {
          throw new Error(`Sample ${index + 1}: missing/misaligned messages`);
        }
        return {
          id: String(entry.original_id ?? `sample-${index + 1}`),
          messages: original.map((msg, j) => ({
            role: String(msg.role || 'unknown'),
            translatedRole: String(translated[j]?.role || 'unknown'),
            original: getMessage(msg), translated: getMessage(translated[j])
          })),
          chunkCount: null, truncatedChunkCount: null
        };
      });
    } else if (input && Array.isArray(input.samples)) {
      // Minimal publishable JSON from prepare_review_data.py.
      label = String(input.datasetLabel || 'Dolci-Think translations');
      samples = input.samples.map((entry, index) => ({
        id: String(entry.id ?? `sample-${index + 1}`),
        chunkCount: Number.isInteger(entry.chunkCount) ? entry.chunkCount : null,
        truncatedChunkCount: Number.isInteger(entry.truncatedChunkCount) ? entry.truncatedChunkCount : null,
        messages: (Array.isArray(entry.messages) ? entry.messages : []).map(msg => ({
          role: String(msg.role || 'unknown'), translatedRole: String(msg.role || 'unknown'),
          original: getMessage(msg.original), translated: getMessage(msg.translated)
        }))
      }));
    } else {
      throw new Error('Expected reconstructed_samples.json or prepared samples.json');
    }
    const ids = new Set();
    for (const sample of samples) {
      if (!sample.messages.length) throw new Error(`Empty sample: ${sample.id}`);
      if (ids.has(sample.id)) throw new Error(`Duplicate sample ID: ${sample.id}`);
      ids.add(sample.id);
      for (const [i, m] of sample.messages.entries()) {
        if (m.role !== m.translatedRole) throw new Error(`${sample.id}, turn ${i + 1}: roles differ`);
      }
    }
    return { label, samples };
  }

  function messagePane(text, lang) {
    const wrap = make('div', 'pane');
    const content = make('div', 'text');
    content.setAttribute('lang', lang);
    if (text.trim()) content.textContent = text;
    else content.appendChild(make('em', 'placeholder', 'Empty section'));
    wrap.appendChild(content);
    return wrap;
  }

  function renderComparisons(sample) {
    const root = $('comparisons');
    root.replaceChildren();
    let count = 0;
    for (const [index, msg] of sample.messages.entries()) {
      for (const part of ['think', 'main']) {
        if (state.filter !== 'all' && state.filter !== part) continue;
        if (!msg.original[part].trim() && !msg.translated[part].trim()) continue;
        const card = make('article', 'comparison');
        const header = make('div', 'comparison-header');
        header.appendChild(make('strong', 'role', `${msg.role} · turn ${index + 1}`));
        header.appendChild(make('span', 'section', part === 'think' ? 'Reasoning / CoT' :
          msg.role.toLowerCase() === 'assistant' ? 'Final answer' : 'Message'));
        const grid = make('div', 'pane-grid');
        grid.append(messagePane(msg.original[part], 'en'), messagePane(msg.translated[part], 'pt-PT'));
        card.append(header, grid);
        root.appendChild(card);
        count++;
      }
    }
    if (!count) root.appendChild(make('p', 'no-results', 'No text in this section.'));
  }

  function renderSidebar() {
    const list = $('sampleList');
    list.replaceChildren();
    if (!state.data) return;
    state.data.samples.forEach((sample, i) => {
      const selected = i === state.selected;
      const button = make('button', `sample-button ${selected ? 'selected' : ''}`);
      button.type = 'button';
      button.setAttribute('aria-current', selected ? 'true' : 'false');
      button.append(make('span', 'sample-number', String(i + 1).padStart(2, '0')),
        make('span', 'sample-details'));
      button.lastChild.append(make('strong', '', `Sample ${i + 1}`), make('small', '', sample.id));
      button.addEventListener('click', () => select(i));
      list.appendChild(button);
    });
  }

  function render() {
    const sample = state.data.samples[state.selected];
    $('samplePosition').textContent = `Sample ${state.selected + 1} of ${state.data.samples.length}`;
    $('sampleName').textContent = `Sample ${state.selected + 1}`;
    $('sampleMetadata').textContent = `ID: ${sample.id} · ${sample.messages.length} turns` +
      (sample.chunkCount === null ? '' : ` · ${sample.chunkCount} chunks`);
    $('prev').disabled = state.selected === 0;
    $('next').disabled = state.selected === state.data.samples.length - 1;
    const warn = $('warning');
    warn.hidden = !(sample.truncatedChunkCount > 0);
    if (!warn.hidden) warn.textContent = `${sample.truncatedChunkCount} translated chunk(s) may be truncated.`;
    $('empty').hidden = true;
    $('viewer').hidden = false;
    renderSidebar();
    renderComparisons(sample);
  }

  function select(index, updateHash = true) {
    if (!state.data || index < 0 || index >= state.data.samples.length) return;
    state.selected = index;
    if (updateHash) history.replaceState(null, '', `#sample=${encodeURIComponent(state.data.samples[index].id)}`);
    render();
  }

  function useData(raw) {
    state.data = normalize(raw);
    $('sampleCount').textContent = String(state.data.samples.length);
    $('datasetName').textContent = state.data.label;
    if (!state.data.samples.length) {
      $('viewer').hidden = true;
      $('empty').hidden = false;
      $('empty').querySelector('p').textContent = 'This dataset has no samples. Open a different JSON file.';
      renderSidebar();
      return;
    }
    const requestedId = new URLSearchParams(location.hash.slice(1)).get('sample');
    const index = requestedId === null ? -1 : state.data.samples.findIndex(x => x.id === requestedId);
    select(index >= 0 ? index : 0, false);
  }

  function notice(text) {
    const node = $('notice');
    node.textContent = text;
    node.hidden = false;
    clearTimeout(notice.timer);
    notice.timer = setTimeout(() => { node.hidden = true; }, 4000);
  }

  async function loadLocalFile(file) {
    if (!file) return;
    try {
      useData(JSON.parse(await file.text()));
      notice(`Loaded ${state.data.samples.length} samples`);
    } catch (e) { notice(`Unable to open JSON: ${e.message}`); }
  }

  async function start() {
    $('jsonFile').addEventListener('change', event => {
      loadLocalFile(event.target.files?.[0]);
      event.target.value = '';
    });
    $('prev').addEventListener('click', () => select(state.selected - 1));
    $('next').addEventListener('click', () => select(state.selected + 1));
    document.querySelectorAll('[data-filter]').forEach(button => {
      button.addEventListener('click', () => {
        state.filter = button.dataset.filter;
        document.querySelectorAll('[data-filter]').forEach(item => {
          const active = item === button;
          item.classList.toggle('active', active);
          item.setAttribute('aria-pressed', String(active));
        });
        if (state.data?.samples.length) renderComparisons(state.data.samples[state.selected]);
      });
    });
    window.addEventListener('hashchange', () => {
      if (!state.data?.samples.length) return;
      const id = new URLSearchParams(location.hash.slice(1)).get('sample');
      const index = state.data.samples.findIndex(s => s.id === id);
      if (index !== -1 && index !== state.selected) select(index, false);
    });
    try {
      const response = await fetch('data/samples.json', {cache: 'no-store'});
      if (response.ok) useData(await response.json());
    } catch (_) { /* file:// and missing JSON: the local picker remains available */ }
  }
  document.addEventListener('DOMContentLoaded', start);
})();
