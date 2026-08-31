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
  var sidebarToggle = document.getElementById('r4SidebarToggle');

  // ---- Admin sidebar: R4-page-only, defaults to collapsed on every fresh
  // load (nothing persisted between page loads) — driven purely by a data
  // attribute on the R4 shell root that r4_editor.css's :has() selectors
  // key off of.
  if (sidebarToggle && shell) {
    sidebarToggle.addEventListener('click', function () {
      var r4SidebarExpanded = shell.dataset.r4SidebarExpanded === 'true';
      r4SidebarExpanded = !r4SidebarExpanded;
      shell.dataset.r4SidebarExpanded = r4SidebarExpanded ? 'true' : 'false';
      sidebarToggle.setAttribute('aria-expanded', r4SidebarExpanded ? 'true' : 'false');
    });
  }

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

  // ---- appearance_override: a compound field (one schema key, an object
  // value) — hydrated from BOTH the persisted/current value and the
  // inherited-global fallback (shown while disabled, per instruction
  // Section 14), never from a second ad-hoc allowlist.
  function hydrateAppearanceOverrideFields(values) {
    if (!inspector) return;
    var inheritedScript = document.getElementById('r4InspectorInheritedAppearance');
    var inherited = {};
    if (inheritedScript) {
      try {
        inherited = JSON.parse(inheritedScript.textContent) || {};
      } catch (err) {
        inherited = {};
      }
    }
    inspector.querySelectorAll('[data-r4-field-type="appearance_override"]').forEach(function (wrapper) {
      var key = wrapper.getAttribute('data-r4-field-key');
      var stored = Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null;
      var typography = (stored && stored.typography) || {};
      var enabled = Boolean(typography.enabled);
      var fallback = inherited[key] || {};
      var font = typography.font != null ? typography.font : fallback.font;
      var typeScale = typography.type_scale != null ? typography.type_scale : fallback.type_scale;

      var enabledInput = wrapper.querySelector('[data-r4-appearance-enabled]');
      var fontSelect = wrapper.querySelector('[data-r4-appearance-font]');
      var scaleSelect = wrapper.querySelector('[data-r4-appearance-type-scale]');
      if (enabledInput) enabledInput.checked = enabled;
      if (fontSelect) {
        if (font != null) fontSelect.value = font;
        fontSelect.disabled = !enabled;
      }
      if (scaleSelect) {
        if (typeScale != null) scaleSelect.value = typeScale;
        scaleSelect.disabled = !enabled;
      }
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
      var fieldType = control.getAttribute('data-r4-field-type');
      // Compound fields are hydrated separately below — this loop only
      // handles scalar controls.
      if (fieldType === 'appearance_override') return;
      var key = control.getAttribute('data-r4-field-key');
      if (!Object.prototype.hasOwnProperty.call(values, key)) return;
      var value = values[key];
      if (fieldType === 'boolean') {
        control.checked = Boolean(value);
      } else {
        control.value = value == null ? '' : value;
      }
    });
    hydrateAppearanceOverrideFields(values);
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
        // Hydrate the raw backing values (incl. the rich_text textarea)
        // BEFORE Alpine mounts CKEditor, so it initializes from the real
        // current body_html rather than an empty source element.
        hydrateFieldValues();
        // Alpine 3's own MutationObserver auto-initializes x-data elements
        // added anywhere in the document (verified against this build) —
        // it already mounts storefrontRichTextEditor()'s CKEditor here.
        // Do NOT also call Alpine.initTree(): doing so double-mounts.
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
      var fieldType = control.getAttribute('data-r4-field-type');
      // CKEditor mounts over the rich_text textarea (aria-hidden, no
      // direct user interaction) — its save path is the dedicated
      // focusout handler below, not this native 'change' listener.
      // appearance_override is a compound field handled by the dedicated
      // listener below — it must never be sent as a scalar patch here.
      if (fieldType === 'rich_text' || fieldType === 'appearance_override') return;
      var key = control.getAttribute('data-r4-field-key');
      var value = fieldType === 'boolean' ? control.checked : control.value;
      var patch = {};
      patch[key] = value;
      R4.enqueueMutation({
        type: 'section.update_settings',
        section_id: R4.selected,
        patch: patch,
      });
    });

    // appearance_override: one compound patch per change, built from the
    // widget's three nested controls — never a raw JSON/CSS input, never a
    // new endpoint.
    inspector.addEventListener('change', function (evt) {
      var wrapper = evt.target.closest('[data-r4-field-type="appearance_override"]');
      if (!wrapper || R4.selected == null) return;
      if (!evt.target.closest('[data-r4-appearance-enabled],[data-r4-appearance-font],[data-r4-appearance-type-scale]')) return;
      var key = wrapper.getAttribute('data-r4-field-key');
      var enabledInput = wrapper.querySelector('[data-r4-appearance-enabled]');
      var fontSelect = wrapper.querySelector('[data-r4-appearance-font]');
      var scaleSelect = wrapper.querySelector('[data-r4-appearance-type-scale]');
      var enabled = Boolean(enabledInput && enabledInput.checked);
      if (fontSelect) fontSelect.disabled = !enabled;
      if (scaleSelect) scaleSelect.disabled = !enabled;

      var typography = { enabled: enabled };
      if (enabled) {
        if (fontSelect) typography.font = fontSelect.value;
        if (scaleSelect) typography.type_scale = scaleSelect.value;
      }
      var patch = {};
      patch[key] = { typography: typography };
      R4.enqueueMutation({
        type: 'section.update_settings',
        section_id: R4.selected,
        patch: patch,
      });
    });

    // Rich text: enqueue one patch only when focus genuinely LEAVES the
    // whole CKEditor wrapper (not on every keystroke, not when focus just
    // moves between the toolbar and the editable area within it).
    inspector.addEventListener('focusout', function (evt) {
      var richEditorWrapper = evt.target.closest('.sfb-rich-editor');
      if (!richEditorWrapper || R4.selected == null) return;
      if (evt.relatedTarget && richEditorWrapper.contains(evt.relatedTarget)) return;
      var textarea = richEditorWrapper.querySelector('[data-r4-field-key]');
      if (!textarea) return;
      var key = textarea.getAttribute('data-r4-field-key');
      var patch = {};
      patch[key] = textarea.value;
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
