// app-table-prefs.js — column visibility and per-page row count preferences
// stored in localStorage per-user, per-table.
// Activates automatically on any table with data-table-prefs="unique-id".
// Per-page selects must have class="per-page-select" + data-table-prefs-for="same-id".
(function () {
    'use strict';

    var userId = (window._appUserId || 'guest');

    function lsGet(key) {
        try { return localStorage.getItem('tp_' + userId + '_' + key); } catch (e) { return null; }
    }
    function lsSet(key, val) {
        try { localStorage.setItem('tp_' + userId + '_' + key, String(val)); } catch (e) {}
    }
    function lsGetJson(key) {
        try { var v = lsGet(key); return v ? JSON.parse(v) : null; } catch (e) { return null; }
    }
    function lsSetJson(key, val) {
        lsSet(key, JSON.stringify(val));
    }

    // ─── per-page persistence ────────────────────────────────────────────────
    function initPerPage(tableId, selectEl) {
        var paramName = selectEl.getAttribute('name') || 'per_page';
        var prefKey = tableId + '_pp_' + paramName;
        var params = new URLSearchParams(window.location.search);

        if (params.has(paramName)) {
            lsSet(prefKey, params.get(paramName));
        } else {
            var saved = lsGet(prefKey);
            if (saved) {
                // Add saved per_page to current URL and redirect (preserves other filters)
                var url = new URL(window.location.href);
                url.searchParams.set(paramName, saved);
                window.location.replace(url.toString());
                return;
            }
        }

        selectEl.addEventListener('change', function () {
            lsSet(prefKey, selectEl.value);
        });
    }

    // ─── column visibility ───────────────────────────────────────────────────
    function setColVisible(table, colIdx, visible) {
        table.querySelectorAll('tr > *:nth-child(' + colIdx + ')').forEach(function (cell) {
            cell.style.display = visible ? '' : 'none';
        });
    }

    function buildToggleUI(table, tableId, columns, savedCols) {
        var wrap = document.createElement('div');
        wrap.className = 'col-prefs-wrap';

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'col-prefs-btn button-link outline sm';
        btn.setAttribute('title', 'نمایش / پنهان کردن ستون‌ها');
        btn.textContent = '⚙ ستون‌ها';
        wrap.appendChild(btn);

        var panel = document.createElement('div');
        panel.className = 'col-prefs-panel';
        panel.hidden = true;

        var header = document.createElement('div');
        header.className = 'col-prefs-header';
        header.textContent = 'نمایش ستون‌ها';
        panel.appendChild(header);

        var list = document.createElement('div');
        list.className = 'col-prefs-list';

        columns.forEach(function (col) {
            if (col.fixed) return;
            var lbl = document.createElement('label');
            lbl.className = 'col-prefs-item';
            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = col.visible;
            lbl.appendChild(cb);
            lbl.appendChild(document.createTextNode(' ' + col.label));
            list.appendChild(lbl);

            cb.addEventListener('change', function () {
                col.visible = cb.checked;
                setColVisible(table, col.idx, col.visible);
                savedCols['c' + col.idx] = col.visible;
                lsSetJson(tableId + '_cols', savedCols);
            });
        });

        panel.appendChild(list);
        wrap.appendChild(panel);

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            panel.hidden = !panel.hidden;
        });

        document.addEventListener('click', function (e) {
            if (!wrap.contains(e.target)) panel.hidden = true;
        });

        // Insert the toggle button wrapper right before the table
        if (table.parentNode) {
            table.parentNode.insertBefore(wrap, table);
        }
    }

    function initTable(table) {
        var tableId = table.getAttribute('data-table-prefs');
        if (!tableId) return;

        var headerRow = table.querySelector('thead tr');
        if (!headerRow) return;

        var ths = Array.prototype.slice.call(headerRow.children);
        if (ths.length < 2) return;

        var savedCols = lsGetJson(tableId + '_cols') || {};

        var columns = ths.map(function (th, i) {
            var idx = i + 1; // 1-based nth-child
            var fixed = th.hasAttribute('data-col-fixed');
            var visible = savedCols.hasOwnProperty('c' + idx) ? savedCols['c' + idx] : true;
            var label = th.textContent.trim() || ('ستون ' + idx);
            return { idx: idx, label: label, fixed: fixed, visible: visible };
        });

        // Apply saved hidden columns before rendering (avoid flash of hidden content)
        columns.forEach(function (col) {
            if (!col.fixed && !col.visible) {
                setColVisible(table, col.idx, false);
            }
        });

        // Only show toggle button if there are toggleable columns
        var toggleable = columns.filter(function (c) { return !c.fixed; });
        if (toggleable.length > 0) {
            buildToggleUI(table, tableId, columns, savedCols);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('table[data-table-prefs]').forEach(function (table) {
            initTable(table);
        });

        document.querySelectorAll('.per-page-select[data-table-prefs-for]').forEach(function (sel) {
            var tableId = sel.getAttribute('data-table-prefs-for');
            initPerPage(tableId, sel);
        });
    });
})();
