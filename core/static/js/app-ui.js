(function () {
    function closeMenus(except) {
        document.querySelectorAll('.top-bar.app-menu-open').forEach(function (bar) {
            if (bar !== except) {
                bar.classList.remove('app-menu-open');
                var trigger = bar.querySelector('.app-menu-trigger');
                if (trigger) trigger.setAttribute('aria-expanded', 'false');
            }
        });
    }

    function enhanceMenus() {
        document.querySelectorAll('.top-bar').forEach(function (bar) {
            var actions = bar.querySelector('.top-actions');
            if (!actions || bar.querySelector('.app-menu-trigger')) return;

            Array.from(actions.children).forEach(function (item) {
                var isAction = item.matches('a, button, form') || item.querySelector('a, button');
                var isDisplayOnly = item.classList.contains('notification-bell') || item.dataset.menuExclude === '1';
                if (!isAction || isDisplayOnly) {
                    item.classList.add('app-menu-static-item');
                    actions.parentNode.insertBefore(item, actions);
                }
            });

            if (actions.children.length < 3) return;

            var trigger = document.createElement('button');
            trigger.type = 'button';
            trigger.className = 'app-menu-trigger';
            trigger.textContent = 'منو';
            trigger.setAttribute('aria-expanded', 'false');
            trigger.setAttribute('aria-label', 'باز کردن منوی عملیات');
            actions.parentNode.insertBefore(trigger, actions);
            bar.classList.add('app-menu-ready');

            trigger.addEventListener('click', function (event) {
                event.stopPropagation();
                var isOpen = bar.classList.toggle('app-menu-open');
                trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
                closeMenus(bar);
            });
        });
    }

    function enhanceTables() {
        document.querySelectorAll('table').forEach(function (table, index) {
            if (table.closest('.app-table-wrap')) return;
            var wrapper = document.createElement('div');
            wrapper.className = 'app-table-wrap';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);

            if (table.dataset.noClientSearch === '1') return;
            var searchableRows = table.querySelectorAll('tbody tr');
            if (searchableRows.length < 8) return;

            var tools = document.createElement('div');
            tools.className = 'app-table-tools';
            var title = document.createElement('div');
            title.className = 'tiny';
            title.textContent = searchableRows.length + ' ردیف در این صفحه';
            var input = document.createElement('input');
            input.className = 'app-table-search';
            input.type = 'search';
            input.placeholder = 'جستجو در ردیف‌های همین صفحه';
            input.setAttribute('aria-label', 'جستجو در جدول');
            tools.appendChild(title);
            tools.appendChild(input);
            wrapper.parentNode.insertBefore(tools, wrapper);

            input.addEventListener('input', function () {
                var value = input.value.trim().toLowerCase();
                table.querySelectorAll('tbody tr').forEach(function (row) {
                    if (row.classList.contains('detail-row')) return;
                    row.style.display = !value || row.textContent.toLowerCase().indexOf(value) !== -1 ? '' : 'none';
                    var next = row.nextElementSibling;
                    if (next && next.classList.contains('detail-row') && row.style.display === 'none') {
                        next.classList.remove('open');
                        next.style.display = 'none';
                    } else if (next && next.classList.contains('detail-row')) {
                        next.style.display = '';
                    }
                });
            });
        });
    }

    document.addEventListener('click', function () {
        closeMenus();
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeMenus();
    });

    document.addEventListener('DOMContentLoaded', function () {
        enhanceMenus();
        enhanceTables();
    });
}());
