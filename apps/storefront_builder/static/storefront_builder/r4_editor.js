window.RastiSiR4 = {
  selected: null,
  revision: Number(document.querySelector('[data-r4-shell]')?.dataset.editRevision || 0),
  inspectorOpen: false,
  saveState: 'saved',
  conflict: false,
  queue: null,
};

(function () {
  var R4 = window.RastiSiR4;
  var shell = document.querySelector('[data-r4-shell]');
  var inspector = document.getElementById('r4Inspector');
  var previewFrame = document.getElementById('r4PreviewFrame');
  var saveStateEl = document.getElementById('r4SaveState');

  var SAVE_STATE_LABELS = {
    saved: 'ذخیره شد',
    saving: 'در حال ذخیره...',
    error: 'خطا در ذخیره تغییرات',
    conflict: 'نسخه‌ی جدیدتری از این صفحه موجود است',
  };

  function setSaveState(state) {
    R4.saveState = state;
    if (saveStateEl) saveStateEl.textContent = SAVE_STATE_LABELS[state] || '';
  }

  function showConflictBanner() {
    if (!shell || document.getElementById('r4ConflictBanner')) return;
    var banner = document.createElement('div');
    banner.id = 'r4ConflictBanner';
    banner.setAttribute('role', 'alert');
    banner.textContent = SAVE_STATE_LABELS.conflict + ' — ';
    var reloadButton = document.createElement('button');
    reloadButton.type = 'button';
    reloadButton.textContent = 'بارگذاری دوباره';
    reloadButton.addEventListener('click', function () {
      window.location.reload();
    });
    banner.appendChild(reloadButton);
    shell.prepend(banner);
  }

  // ---- Task 5's single mutate endpoint: one serialized queue, one sender.
  R4.sendMutation = function (mutation) {
    if (R4.conflict) return Promise.resolve();
    setSaveState('saving');
    var url = new URL('mutate/', window.location.href);
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ base_revision: R4.revision, mutation: mutation }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { status: response.status, body: body };
        });
      })
      .then(function (result) {
        if (result.status === 200 && result.body && result.body.ok) {
          R4.revision = result.body.new_revision;
          if (shell) shell.dataset.editRevision = String(R4.revision);
          setSaveState('saved');
          return result.body;
        }
        if (result.status === 409) {
          // Explicit conflict state — stop the automatic queue for good;
          // never silently replay the stale mutation, never auto-reload.
          R4.conflict = true;
          setSaveState('conflict');
          showConflictBanner();
          return result.body;
        }
        // Controlled non-409 rejection — surfaced, revision untouched,
        // never treated as success, never silently retried.
        setSaveState('error');
        return result.body;
      })
      .catch(function () {
        setSaveState('error');
      });
  };

  R4.enqueueMutation = function (mutation) {
    if (R4.conflict) return Promise.resolve();
    R4.queue = (R4.queue || Promise.resolve()).then(function () {
      return R4.sendMutation(mutation);
    });
    return R4.queue;
  };

  // ---- Inspector: schema-driven, two tabs, current-value hydration.
  function activateTab(name) {
    if (!inspector) return;
    inspector.querySelectorAll('[data-r4-tab]').forEach(function (tabButton) {
      var isActive = tabButton.getAttribute('data-r4-tab') === name;
      tabButton.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    inspector.querySelectorAll('[data-r4-tab-panel]').forEach(function (panel) {
      var isActive = panel.getAttribute('data-r4-tab-panel') === name;
      if (isActive) panel.removeAttribute('hidden');
      else panel.setAttribute('hidden', '');
    });
  }

  function hydrateFieldValues() {
    if (!inspector) return;
    var script = document.getElementById('r4InspectorFieldValues');
    if (!script) return;
    var values;
    try {
      values = JSON.parse(script.textContent);
    } catch (err) {
      return;
    }
    inspector.querySelectorAll('[data-r4-field-key]').forEach(function (control) {
      var key = control.getAttribute('data-r4-field-key');
      if (!Object.prototype.hasOwnProperty.call(values, key)) return;
      var value = values[key];
      if (control.getAttribute('data-r4-field-type') === 'boolean') {
        control.checked = Boolean(value);
      } else {
        control.value = value == null ? '' : value;
      }
    });
  }

  R4.openSection = function (sectionId) {
    if (!inspector || !sectionId) return Promise.resolve();
    var url = new URL('sections/' + sectionId + '/inspector/', window.location.href);
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) {
        if (!response.ok) return null;
        return response.text();
      })
      .then(function (html) {
        if (html == null) return;
        inspector.innerHTML = html;
        inspector.hidden = false;
        if (shell) shell.dataset.r4InspectorOpen = 'true';
        R4.selected = sectionId;
        R4.inspectorOpen = true;
        activateTab('basic');
        hydrateFieldValues();
      })
      .catch(function () {
        // Network/render failure opening the Inspector — no R3 fallback,
        // no popup; the shell simply stays as it already was.
      });
  };

  function closeInspector() {
    if (!inspector) return;
    inspector.hidden = true;
    inspector.innerHTML = '';
    if (shell) shell.dataset.r4InspectorOpen = 'false';
    R4.selected = null;
    R4.inspectorOpen = false;
  }

  if (inspector) {
    // One delegated field-change path — no per-section save handler.
    inspector.addEventListener('click', function (evt) {
      var tabButton = evt.target.closest('[data-r4-tab]');
      if (tabButton) {
        activateTab(tabButton.getAttribute('data-r4-tab'));
        return;
      }
      var closeButton = evt.target.closest('[data-r4-inspector-close]');
      if (closeButton) closeInspector();
    });

    inspector.addEventListener('change', function (evt) {
      var control = evt.target.closest('[data-r4-field-key]');
      if (!control || R4.selected == null) return;
      var key = control.getAttribute('data-r4-field-key');
      var fieldType = control.getAttribute('data-r4-field-type');
      var value = fieldType === 'boolean' ? control.checked : control.value;
      var patch = {};
      patch[key] = value;
      R4.enqueueMutation({
        type: 'section.update_settings',
        section_id: R4.selected,
        patch: patch,
      });
    });
  }

  // ---- Preview selection compatibility bridge (see Task 6 finding):
  // a normal click on a Preview section currently only ever reaches
  // sfb:openSectionSettings (interceptBuilderEditClick's capture-phase
  // stopImmediatePropagation prevents sfb:selectSection for that same
  // click) — both are accepted and routed to the same openSection().
  window.addEventListener('message', function (evt) {
    if (evt.origin !== window.location.origin) return;
    if (!previewFrame || evt.source !== previewFrame.contentWindow) return;
    if (!evt.data) return;
    var type = evt.data.type;
    if (type !== 'sfb:selectSection' && type !== 'sfb:openSectionSettings') return;
    var sectionId = evt.data.sectionId;
    if (!sectionId) return;
    R4.openSection(Number(sectionId));
  });
})();
