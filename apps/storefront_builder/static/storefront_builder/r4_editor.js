window.RastiSiR4 = {
  selected: null,
  revision: Number(document.querySelector('[data-r4-shell]')?.dataset.editRevision || 0),
  inspectorOpen: false,
  saveState: 'saved',
  conflict: false,
  queue: null,
  resourcePicker: null,
};

(function () {
  var R4 = window.RastiSiR4;
  var shell = document.querySelector('[data-r4-shell]');
  var inspector = document.getElementById('r4Inspector');
  var previewFrame = document.getElementById('r4PreviewFrame');
  var saveStateEl = document.getElementById('r4SaveState');
  var sidebarToggle = document.getElementById('r4SidebarToggle');
  var structurePanel = document.getElementById('r4Structure');
  var structureToggle = document.getElementById('r4StructureToggle');
  // R4 Task 10 — the shared Resource Picker overlay root is created here
  // (never added to editor.html's own markup, which Task 10 leaves
  // untouched) so it always exists as a direct child of the R4 shell.
  var pickerRoot = document.getElementById('r4ResourcePicker');
  if (!pickerRoot && shell) {
    pickerRoot = document.createElement('div');
    pickerRoot.id = 'r4ResourcePicker';
    pickerRoot.hidden = true;
    shell.appendChild(pickerRoot);
  }
  var pickerSearchTimer = null;

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

  // ---- Structure panel: R4 Task 8, CLOSED by default on every fresh load
  // (nothing persisted), same toggle pattern as the admin sidebar above.
  if (structureToggle && shell) {
    structureToggle.addEventListener('click', function () {
      var open = shell.dataset.r4StructureOpen === 'true';
      open = !open;
      shell.dataset.r4StructureOpen = open ? 'true' : 'false';
      structureToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
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

  // ---- R4 Task 8 — structural mutations (add/remove/duplicate/move) go
  // through the SAME single queue/endpoint as every other mutation; this
  // wrapper only adds the read-side refresh a successful structural change
  // needs (existing Preview iframe reload + Structure panel re-fetch), per
  // instruction Section 31. No new write endpoint, no fake client DOM
  // renderer, no second renderer.
  function refreshStructureAndPreview() {
    if (previewFrame && previewFrame.contentWindow) {
      previewFrame.contentWindow.location.reload();
    }
    if (!structurePanel) return Promise.resolve();
    return fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var freshDoc = new DOMParser().parseFromString(html, 'text/html');
        var freshStructure = freshDoc.getElementById('r4Structure');
        if (freshStructure) structurePanel.innerHTML = freshStructure.innerHTML;
      })
      .catch(function () {
        // The mutation itself already succeeded and the server-authoritative
        // revision already advanced — a failed read-side refresh just means
        // the merchant sees the stale list until their next action.
      });
  }

  R4.enqueueStructuralMutation = function (mutation) {
    return R4.enqueueMutation(mutation).then(function (result) {
      if (result && result.ok) {
        if (mutation.type === 'section.remove' && R4.selected === mutation.section_id) {
          closeInspector();
        }
        // Awaited: callers (and this session's own QA) must be able to
        // trust that once this promise resolves, the Structure panel/
        // Preview iframe reflect the just-applied mutation — not just that
        // the server accepted it.
        return refreshStructureAndPreview().then(function () {
          return result;
        });
      }
      return result;
    });
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
      // handles scalar controls. resource_source (R4 Task 9) is a
      // server-rendered READ-ONLY summary with no editable control at
      // all — nothing to hydrate client-side.
      if (fieldType === 'appearance_override' || fieldType === 'resource_source') return;
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
      if (closeButton) { closeInspector(); return; }
      // R4 Task 10 — the ONE generic open control on a resource_source
      // field row; identical for product_section and brand_carousel, no
      // Product/Brand-specific handler.
      var pickerOpenButton = evt.target.closest('[data-r4-resource-picker-open]');
      if (pickerOpenButton) {
        var pickerFieldWrapper = pickerOpenButton.closest('[data-r4-field-key]');
        R4.openResourcePicker(pickerFieldWrapper);
      }
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

  // ---- R4 Task 8 — Structure panel: one delegated click handler for
  // select/move/duplicate/remove/add, bound to the stable container so it
  // keeps working after refreshStructureAndPreview() replaces the panel's
  // innerHTML (delegation, never re-bound per row).
  if (structurePanel) {
    structurePanel.addEventListener('click', function (evt) {
      var moveBtn = evt.target.closest('[data-r4-structure-move]');
      if (moveBtn) {
        if (moveBtn.disabled) return;
        var moveRow = moveBtn.closest('[data-r4-structure-row]');
        if (!moveRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.move',
          section_id: Number(moveRow.getAttribute('data-r4-structure-section-id')),
          direction: moveBtn.getAttribute('data-r4-structure-move'),
        });
        return;
      }
      var duplicateBtn = evt.target.closest('[data-r4-structure-duplicate]');
      if (duplicateBtn) {
        var duplicateRow = duplicateBtn.closest('[data-r4-structure-row]');
        if (!duplicateRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.duplicate',
          section_id: Number(duplicateRow.getAttribute('data-r4-structure-section-id')),
        });
        return;
      }
      var removeBtn = evt.target.closest('[data-r4-structure-remove]');
      if (removeBtn) {
        if (removeBtn.disabled) return;
        var removeRow = removeBtn.closest('[data-r4-structure-row]');
        if (!removeRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.remove',
          section_id: Number(removeRow.getAttribute('data-r4-structure-section-id')),
        });
        return;
      }
      var addBtn = evt.target.closest('#r4StructureAddButton');
      if (addBtn) {
        var addSelect = structurePanel.querySelector('#r4StructureAddSelect');
        var sectionKey = addSelect ? addSelect.value : '';
        if (!sectionKey) return;
        R4.enqueueStructuralMutation({ type: 'section.add', section_key: sectionKey });
        if (addSelect) addSelect.value = '';
        return;
      }
      var label = evt.target.closest('.r4-structure-label');
      if (label) {
        var labelRow = label.closest('[data-r4-structure-row]');
        if (!labelRow) return;
        R4.openSection(Number(labelRow.getAttribute('data-r4-structure-section-id')));
      }
    });
  }

  // ---- R4 Task 10 — the ONE shared Resource Picker lifecycle for both
  // Product and Brand. One state object (R4.resourcePicker), one fetch
  // endpoint (resources/picker/), one apply path (the existing Task 5
  // R4.enqueueMutation queue) — never a per-kind picker/component/endpoint.
  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function pickerFetchUrl(kind, query, selectedIds) {
    var url = new URL('resources/picker/', window.location.href);
    url.searchParams.set('kind', kind);
    if (query) url.searchParams.set('q', query);
    selectedIds.forEach(function (id) { url.searchParams.append('selected', String(id)); });
    return url;
  }

  function pickerAllowedAutoRules() {
    var rules = [];
    if (!pickerRoot) return rules;
    pickerRoot.querySelectorAll('[data-r4-picker-auto-rule]').forEach(function (button) {
      rules.push(button.getAttribute('data-r4-picker-auto-rule'));
    });
    return rules;
  }

  function pickerHasValidSelection() {
    var state = R4.resourcePicker;
    if (!state) return false;
    if (state.mode === 'manual') return state.selectedIds.length > 0;
    if (state.mode === 'auto') return pickerAllowedAutoRules().indexOf(state.autoRule) !== -1;
    return false;
  }

  function updatePickerApplyEnabled() {
    if (!pickerRoot) return;
    var applyButton = pickerRoot.querySelector('[data-r4-picker-apply]');
    if (applyButton) applyButton.disabled = !pickerHasValidSelection();
  }

  function buildPickerSelectedRowHTML(item) {
    return (
      '<div class="r4-picker-row r4-picker-row--selected" data-r4-picker-selected-item '
      + 'data-r4-picker-item-id="' + item.id + '" '
      + 'data-r4-picker-item-label="' + escapeHtml(item.label) + '" '
      + 'data-r4-picker-item-sublabel="' + escapeHtml(item.sublabel || '') + '">'
      + '<span class="r4-picker-row-label">' + escapeHtml(item.label) + '</span>'
      + '<span class="r4-picker-row-sublabel">' + escapeHtml(item.sublabel || '') + '</span>'
      + '<span class="r4-picker-row-actions">'
      + '<button type="button" data-r4-picker-move="up" aria-label="جابه‌جایی به بالا">↑</button>'
      + '<button type="button" data-r4-picker-move="down" aria-label="جابه‌جایی به پایین">↓</button>'
      + '<button type="button" data-r4-picker-remove aria-label="حذف">✕</button>'
      + '</span></div>'
    );
  }

  function renderPickerSelectedList() {
    var state = R4.resourcePicker;
    if (!state || !pickerRoot) return;
    var listEl = pickerRoot.querySelector('#r4PickerSelectedList');
    if (!listEl) return;
    if (state.selectedIds.length === 0) {
      listEl.innerHTML = '<p class="r4-picker-empty" data-r4-picker-selected-empty-hint>هنوز چیزی انتخاب نشده است.</p>';
    } else {
      listEl.innerHTML = state.selectedIds.map(function (id) {
        var item = state.itemCache[id] || { id: id, label: String(id), sublabel: '' };
        return buildPickerSelectedRowHTML(item);
      }).join('');
    }
    var countEl = pickerRoot.querySelector('[data-r4-picker-selected-count]');
    if (countEl) countEl.textContent = String(state.selectedIds.length);
    updatePickerApplyEnabled();
  }

  function syncPickerModeUI() {
    var state = R4.resourcePicker;
    if (!state || !pickerRoot) return;
    var activeTabName = state.mode === 'manual' ? 'manual' : (state.mode === 'auto' ? 'auto' : null);
    pickerRoot.querySelectorAll('[data-r4-picker-mode]').forEach(function (tabButton) {
      var isActive = tabButton.getAttribute('data-r4-picker-mode') === activeTabName;
      tabButton.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    pickerRoot.querySelectorAll('[data-r4-picker-panel]').forEach(function (panel) {
      var name = panel.getAttribute('data-r4-picker-panel');
      var show = state.mode === 'manual' ? name === 'manual' : name === 'auto';
      if (show) panel.removeAttribute('hidden'); else panel.setAttribute('hidden', '');
    });
    var allowedRules = pickerAllowedAutoRules();
    pickerRoot.querySelectorAll('[data-r4-picker-auto-rule]').forEach(function (ruleButton) {
      var isActive = ruleButton.getAttribute('data-r4-picker-auto-rule') === state.autoRule;
      ruleButton.classList.toggle('r4-picker-auto-rule--active', isActive);
      ruleButton.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
    // Task 9's typed Product auto rules (by_category/by_brand/by_collection)
    // are preserved but not directly editable here (Section 17) — surfaced
    // as read-only info, never silently replaced by opening/closing.
    var currentNote = pickerRoot.querySelector('[data-r4-picker-auto-current]');
    if (currentNote) {
      if (state.mode === 'auto' && state.autoRule && allowedRules.indexOf(state.autoRule) === -1) {
        currentNote.hidden = false;
        currentNote.textContent = 'این بخش هم‌اکنون از یک قانون خودکار دیگر استفاده می‌کند که در این پنجره قابل تغییر مستقیم نیست. برای تغییر، حالت دستی یا یکی از گزینه‌های بالا را انتخاب کنید.';
      } else {
        currentNote.hidden = true;
      }
    }
    updatePickerApplyEnabled();
  }

  function closeResourcePicker() {
    if (!pickerRoot) return;
    pickerRoot.hidden = true;
    pickerRoot.innerHTML = '';
    R4.resourcePicker = null;
  }

  function refreshPickerResults() {
    var state = R4.resourcePicker;
    if (!state || !pickerRoot) return Promise.resolve();
    var url = pickerFetchUrl(state.kind, state.query, state.selectedIds);
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var freshDoc = new DOMParser().parseFromString(html, 'text/html');
        var freshResults = freshDoc.getElementById('r4PickerResults');
        var currentResults = pickerRoot.querySelector('#r4PickerResults');
        if (freshResults && currentResults) {
          currentResults.innerHTML = freshResults.innerHTML;
          currentResults.querySelectorAll('[data-r4-picker-item-id]').forEach(function (el) {
            var id = Number(el.getAttribute('data-r4-picker-item-id'));
            state.itemCache[id] = {
              id: id,
              label: el.getAttribute('data-r4-picker-item-label'),
              sublabel: el.getAttribute('data-r4-picker-item-sublabel'),
            };
          });
        }
      })
      .catch(function () {
        // A failed search refresh leaves the previous results visible —
        // never treated as "nothing found", never retried automatically.
      });
  }

  function buildResourceSourcePayload() {
    var state = R4.resourcePicker;
    if (!state) return null;
    if (state.mode === 'manual') {
      if (!state.selectedIds.length) return null;
      return {
        kind: state.kind, mode: 'manual', auto_rule: null, auto_parameters: {},
        manual_ids: state.selectedIds.slice(),
      };
    }
    if (state.mode === 'auto' && pickerAllowedAutoRules().indexOf(state.autoRule) !== -1) {
      return { kind: state.kind, mode: 'auto', auto_rule: state.autoRule, auto_parameters: {}, manual_ids: [] };
    }
    return null;
  }

  function applyResourcePicker() {
    var state = R4.resourcePicker;
    var payload = buildResourceSourcePayload();
    if (!state || !payload) return Promise.resolve();
    var sectionId = R4.selected;
    var patch = {};
    patch[state.fieldKey] = payload;
    // The ONE Section write remains the existing Task 5 mutation queue —
    // the Picker has no save endpoint/form of its own.
    return R4.enqueueMutation({
      type: 'section.update_settings',
      section_id: sectionId,
      patch: patch,
    }).then(function (result) {
      if (result && result.ok) {
        closeResourcePicker();
        if (previewFrame && previewFrame.contentWindow) {
          previewFrame.contentWindow.location.reload();
        }
        // Re-open the Inspector so its summary comes back from the
        // server-authoritative legacy -> ResourceSource projection —
        // never reconstructed client-side.
        return R4.openSection(sectionId);
      }
      // Controlled 400/409/network failure — overlay stays open, nothing
      // is pretended to be saved; the existing save-state/conflict
      // handling in R4.sendMutation already governs what happens next.
      return result;
    });
  }

  R4.openResourcePicker = function (fieldWrapper) {
    if (!fieldWrapper || !pickerRoot || R4.selected == null) return Promise.resolve();
    var fieldKey = fieldWrapper.getAttribute('data-r4-field-key');
    var script = document.getElementById('r4InspectorFieldValues');
    var values = {};
    if (script) {
      try { values = JSON.parse(script.textContent) || {}; } catch (err) { values = {}; }
    }
    // The CURRENT typed ResourceSource, already projected server-side
    // (Task 9) from the real legacy Section.settings — never reconstructed
    // from visible Persian summary text.
    var current = values[fieldKey] || {};
    if (!current.kind) return Promise.resolve();

    R4.resourcePicker = {
      fieldKey: fieldKey,
      kind: current.kind,
      mode: current.mode === 'manual' ? 'manual' : 'auto',
      autoRule: current.auto_rule || null,
      autoParameters: current.auto_parameters || {},
      selectedIds: (current.manual_ids || []).slice(),
      itemCache: {},
      maxItems: 0,
      query: '',
    };

    var url = pickerFetchUrl(current.kind, '', R4.resourcePicker.selectedIds);
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.ok ? response.text() : null; })
      .then(function (html) {
        if (html == null || !R4.resourcePicker) return;
        pickerRoot.innerHTML = html;
        pickerRoot.hidden = false;
        var maxItemsEl = pickerRoot.querySelector('[data-r4-picker-max-items]');
        R4.resourcePicker.maxItems = maxItemsEl ? Number(maxItemsEl.textContent) || 0 : 0;
        pickerRoot.querySelectorAll('[data-r4-picker-item-id]').forEach(function (el) {
          var id = Number(el.getAttribute('data-r4-picker-item-id'));
          R4.resourcePicker.itemCache[id] = {
            id: id,
            label: el.getAttribute('data-r4-picker-item-label'),
            sublabel: el.getAttribute('data-r4-picker-item-sublabel'),
          };
        });
        syncPickerModeUI();
        var searchInput = pickerRoot.querySelector('[data-r4-picker-search]');
        if (searchInput) searchInput.focus();
      })
      .catch(function () {
        closeResourcePicker();
      });
  };

  if (pickerRoot) {
    pickerRoot.addEventListener('input', function (evt) {
      var searchInput = evt.target.closest('[data-r4-picker-search]');
      if (!searchInput || !R4.resourcePicker) return;
      R4.resourcePicker.query = searchInput.value;
      if (pickerSearchTimer) clearTimeout(pickerSearchTimer);
      pickerSearchTimer = setTimeout(refreshPickerResults, 300);
    });

    pickerRoot.addEventListener('click', function (evt) {
      if (evt.target.closest('[data-r4-picker-close]') || evt.target.closest('[data-r4-picker-cancel]')) {
        closeResourcePicker();
        return;
      }
      var modeTab = evt.target.closest('[data-r4-picker-mode]');
      if (modeTab && R4.resourcePicker) {
        R4.resourcePicker.mode = modeTab.getAttribute('data-r4-picker-mode');
        syncPickerModeUI();
        return;
      }
      var ruleButton = evt.target.closest('[data-r4-picker-auto-rule]');
      if (ruleButton && R4.resourcePicker) {
        R4.resourcePicker.mode = 'auto';
        R4.resourcePicker.autoRule = ruleButton.getAttribute('data-r4-picker-auto-rule');
        syncPickerModeUI();
        return;
      }
      var addButton = evt.target.closest('[data-r4-picker-add]');
      if (addButton && R4.resourcePicker) {
        var state = R4.resourcePicker;
        if (state.selectedIds.length >= state.maxItems) return;
        var addId = Number(addButton.getAttribute('data-r4-picker-item-id'));
        if (state.selectedIds.indexOf(addId) !== -1) return;
        state.itemCache[addId] = {
          id: addId,
          label: addButton.getAttribute('data-r4-picker-item-label'),
          sublabel: addButton.getAttribute('data-r4-picker-item-sublabel'),
        };
        state.selectedIds.push(addId);
        state.mode = 'manual';
        renderPickerSelectedList();
        syncPickerModeUI();
        return;
      }
      var removeButton = evt.target.closest('[data-r4-picker-remove]');
      if (removeButton && R4.resourcePicker) {
        var removeRow = removeButton.closest('[data-r4-picker-selected-item]');
        if (!removeRow) return;
        var removeId = Number(removeRow.getAttribute('data-r4-picker-item-id'));
        R4.resourcePicker.selectedIds = R4.resourcePicker.selectedIds.filter(function (v) { return v !== removeId; });
        renderPickerSelectedList();
        return;
      }
      var moveButton = evt.target.closest('[data-r4-picker-move]');
      if (moveButton && R4.resourcePicker) {
        var moveRow = moveButton.closest('[data-r4-picker-selected-item]');
        if (!moveRow) return;
        var moveId = Number(moveRow.getAttribute('data-r4-picker-item-id'));
        var ids = R4.resourcePicker.selectedIds;
        var idx = ids.indexOf(moveId);
        var swapWith = moveButton.getAttribute('data-r4-picker-move') === 'up' ? idx - 1 : idx + 1;
        if (idx === -1 || swapWith < 0 || swapWith >= ids.length) return;
        var tmp = ids[idx];
        ids[idx] = ids[swapWith];
        ids[swapWith] = tmp;
        renderPickerSelectedList();
        return;
      }
      if (evt.target.closest('[data-r4-picker-apply]')) {
        applyResourcePicker();
      }
    });
  }

  document.addEventListener('keydown', function (evt) {
    if (evt.key === 'Escape' && pickerRoot && !pickerRoot.hidden) {
      closeResourcePicker();
    }
  });

  // ---- Preview selection compatibility bridge (see Task 6 finding):
  // a normal click on a Preview section currently only ever reaches
  // sfb:openSectionSettings (interceptBuilderEditClick's capture-phase
  // stopImmediatePropagation prevents sfb:selectSection for that same
  // click) — both are accepted and routed to the same openSection().
  //
  // R4 Task 8 also maps the shared Preview toolbar's existing
  // sfb:sectionCommand/sfb:blockCommand messages, but ONLY the four
  // Task-8-supported commands (duplicate/remove/up/down) — toggle, lock,
  // cellCommand and containerCommand are deliberately left unhandled
  // (never routed to an R3 endpoint, never given a new mutation type).
  window.addEventListener('message', function (evt) {
    if (evt.origin !== window.location.origin) return;
    if (!previewFrame || evt.source !== previewFrame.contentWindow) return;
    if (!evt.data) return;
    var type = evt.data.type;
    if (type === 'sfb:selectSection' || type === 'sfb:openSectionSettings') {
      var sectionId = evt.data.sectionId;
      if (!sectionId) return;
      R4.openSection(Number(sectionId));
      return;
    }
    if (type === 'sfb:sectionCommand') {
      var sectionCommandId = evt.data.sectionId;
      if (!sectionCommandId) return;
      if (evt.data.command === 'duplicate') {
        R4.enqueueStructuralMutation({ type: 'section.duplicate', section_id: Number(sectionCommandId) });
      } else if (evt.data.command === 'remove') {
        R4.enqueueStructuralMutation({ type: 'section.remove', section_id: Number(sectionCommandId) });
      }
      return;
    }
    if (type === 'sfb:blockCommand') {
      var blockCommandId = evt.data.sectionId;
      if (!blockCommandId) return;
      if (evt.data.command === 'up' || evt.data.command === 'down') {
        R4.enqueueStructuralMutation({
          type: 'section.move', section_id: Number(blockCommandId), direction: evt.data.command,
        });
      } else if (evt.data.command === 'remove') {
        R4.enqueueStructuralMutation({ type: 'section.remove', section_id: Number(blockCommandId) });
      }
    }
  });
})();
