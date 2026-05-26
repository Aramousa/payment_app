(function () {
    function enhanceShellNavigation() {
        document.querySelectorAll('.app-shell-nav').forEach(function (nav) {
            if (nav.dataset.navReady === '1') return;
            nav.dataset.navReady = '1';
            var trigger = nav.querySelector('.app-nav-toggle');
            if (!trigger) return;

            trigger.addEventListener('click', function (event) {
                event.stopPropagation();
                var isOpen = nav.classList.toggle('open');
                trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            });
            nav.addEventListener('click', function (event) {
                event.stopPropagation();
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
            var searchableRows = table.querySelectorAll('tbody tr:not(.detail-row)');
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

    function enhanceCustomerSelects() {
        document.querySelectorAll('select[data-customer-select="1"]').forEach(function (select) {
            if (select.dataset.customerSearchReady === '1') return;
            select.dataset.customerSearchReady = '1';

            var filters = document.createElement('div');
            filters.className = 'app-customer-select-filters';
            filters.style.display = 'grid';
            filters.style.gridTemplateColumns = 'repeat(auto-fit, minmax(130px, 1fr))';
            filters.style.gap = '6px';
            filters.style.marginBottom = '6px';

            var filterConfig = [
                ['q', 'نام، کاربری، تلفن'],
                ['organization', 'مجموعه'],
                ['province', 'استان'],
                ['city', 'شهر']
            ];
            var inputs = {};

            filterConfig.forEach(function (item) {
                var input = document.createElement('input');
                input.type = 'search';
                input.className = 'app-customer-select-search';
                input.placeholder = item[1];
                input.setAttribute('aria-label', item[1]);
                input.dataset.customerFilter = item[0];
                inputs[item[0]] = input;
                filters.appendChild(input);
            });

            select.parentNode.insertBefore(filters, select);

            var hint = document.createElement('div');
            hint.className = 'tiny';
            hint.style.margin = '4px 0 0';
            hint.textContent = select.multiple
                ? 'ابتدا فیلتر کنید، سپس مشتریان موردنظر را از همین لیست انتخاب کنید. برای انتخاب چند مشتری از Ctrl یا Shift استفاده کنید.'
                : 'ابتدا فیلتر کنید، سپس مشتری موردنظر را از همین لیست انتخاب کنید.';
            if (hint.textContent) {
                select.parentNode.insertBefore(hint, select.nextSibling);
            }

            function optionMatches(option) {
                var text = option.textContent.toLowerCase();
                return Object.keys(inputs).every(function (key) {
                    var value = inputs[key].value.trim().toLowerCase();
                    return !value || text.indexOf(value) !== -1;
                });
            }

            function applyFilters() {
                Array.from(select.options).forEach(function (option) {
                    if (!option.value) return;
                    var visible = optionMatches(option);
                    if (option.selected && !visible) {
                        option.hidden = false;
                        option.disabled = false;
                        return;
                    }
                    option.hidden = !visible;
                    option.disabled = !visible;
                });
            }

            Object.keys(inputs).forEach(function (key) {
                inputs[key].addEventListener('input', applyFilters);
            });
        });
    }

    function disableDateAutocomplete() {
        var selector = [
            'input.jalali-date',
            'input[name="date"]',
            'input[name="start_date"]',
            'input[name="end_date"]',
            'input[name$="_date"]',
            'input[name$="_from"]',
            'input[name$="_until"]'
        ].join(',');

        document.querySelectorAll(selector).forEach(function (input) {
            input.setAttribute('autocomplete', 'off');
            input.setAttribute('autocorrect', 'off');
            input.setAttribute('autocapitalize', 'off');
            input.setAttribute('spellcheck', 'false');
            input.setAttribute('data-lpignore', 'true');
            input.setAttribute('data-form-type', 'other');
        });
    }

    function enhanceZoomableImages() {
        var registry = new WeakMap();

        function clamp(value, min, max) {
            return Math.min(max, Math.max(min, value));
        }

        function enhanceImage(img) {
            if (!img || img.dataset.zoomReady === '1') return;
            img.dataset.zoomReady = '1';
            img.classList.add('app-zoomable-image');

            var viewport = document.createElement('div');
            viewport.className = 'app-image-zoom-viewport';
            img.parentNode.insertBefore(viewport, img);
            viewport.appendChild(img);

            var toolbar = document.createElement('div');
            toolbar.className = 'app-image-zoom-toolbar';
            toolbar.innerHTML =
                '<button type="button" data-zoom="in" title="بزرگنمایی">+</button>' +
                '<button type="button" data-zoom="out" title="کوچکنمایی">-</button>' +
                '<button type="button" data-zoom="reset" title="نمایش عادی">100%</button>' +
                '<span class="app-image-zoom-level">100%</span>';
            viewport.appendChild(toolbar);

            var level = toolbar.querySelector('.app-image-zoom-level');
            var state = { scale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, baseX: 0, baseY: 0 };

            function render() {
                if (state.scale <= 1) {
                    state.x = 0;
                    state.y = 0;
                }
                img.style.transform = 'translate(' + state.x + 'px, ' + state.y + 'px) scale(' + state.scale + ')';
                img.style.cursor = state.scale > 1 ? 'grab' : 'zoom-in';
                if (level) level.textContent = Math.round(state.scale * 100) + '%';
            }

            function setScale(nextScale) {
                state.scale = clamp(nextScale, 1, 6);
                render();
            }

            function reset() {
                state.scale = 1;
                state.x = 0;
                state.y = 0;
                render();
            }

            toolbar.addEventListener('click', function (event) {
                var button = event.target.closest('button[data-zoom]');
                if (!button) return;
                event.preventDefault();
                event.stopPropagation();
                if (button.dataset.zoom === 'in') setScale(state.scale + 0.25);
                if (button.dataset.zoom === 'out') setScale(state.scale - 0.25);
                if (button.dataset.zoom === 'reset') reset();
            });

            viewport.addEventListener('wheel', function (event) {
                event.preventDefault();
                setScale(state.scale + (event.deltaY < 0 ? 0.18 : -0.18));
            }, { passive: false });

            viewport.addEventListener('dblclick', function (event) {
                if (event.target.closest('.app-image-zoom-toolbar')) return;
                event.preventDefault();
                if (state.scale > 1) reset();
                else setScale(2);
            });

            viewport.addEventListener('pointerdown', function (event) {
                if (event.target.closest('.app-image-zoom-toolbar')) return;
                if (state.scale <= 1) {
                    setScale(2);
                    return;
                }
                state.dragging = true;
                state.startX = event.clientX;
                state.startY = event.clientY;
                state.baseX = state.x;
                state.baseY = state.y;
                img.classList.add('is-dragging');
                viewport.setPointerCapture(event.pointerId);
            });

            viewport.addEventListener('pointermove', function (event) {
                if (!state.dragging) return;
                state.x = state.baseX + event.clientX - state.startX;
                state.y = state.baseY + event.clientY - state.startY;
                render();
            });

            function stopDrag(event) {
                if (!state.dragging) return;
                state.dragging = false;
                img.classList.remove('is-dragging');
                try {
                    viewport.releasePointerCapture(event.pointerId);
                } catch (e) {}
            }

            viewport.addEventListener('pointerup', stopDrag);
            viewport.addEventListener('pointercancel', stopDrag);
            img.addEventListener('load', reset);

            registry.set(img, { reset: reset });
            reset();
        }

        document.querySelectorAll('img.app-zoomable-image, img[data-zoomable-image="1"]').forEach(enhanceImage);

        window.AppImageZoom = {
            enhance: enhanceImage,
            reset: function (img) {
                var item = registry.get(img);
                if (item) item.reset();
                else enhanceImage(img);
            }
        };
    }

    function getCookie(name) {
        var value = '; ' + document.cookie;
        var parts = value.split('; ' + name + '=');
        if (parts.length === 2) return parts.pop().split(';').shift();
        return '';
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, function (char) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            }[char];
        });
    }

    function enhanceNotifications() {
        document.querySelectorAll('.notification-bell').forEach(function (bell) {
            if (bell.dataset.notificationReady === '1') return;
            bell.dataset.notificationReady = '1';

            var trigger = bell.querySelector('.notification-trigger');
            var badge = bell.querySelector('.notification-badge');
            var list = bell.querySelector('.notification-list') || document.getElementById('notificationList');
            var enableButton = bell.querySelector('.enable-browser-notifications') || document.getElementById('enableBrowserNotifications');
            var readButton = bell.querySelector('.mark-notifications-read') || document.getElementById('markNotificationsRead');
            var feedUrl = bell.dataset.feedUrl || window.notificationFeedUrl;
            var readUrl = bell.dataset.readUrl || window.notificationReadUrl;
            var userId = bell.dataset.userId || '';
            var storageKey = 'paymentAppNotificationLastSeen:' + userId;
            var lastSeenId = Number(localStorage.getItem(storageKey) || '0');
            var firstPoll = true;

            function setOpen(open) {
                bell.classList.toggle('open', open);
                if (trigger) trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
            }

            function updateBadge(count) {
                if (!badge) return;
                badge.textContent = count;
                badge.classList.toggle('zero', count === 0);
            }

            function renderItems(items) {
                if (!list) return;
                if (!items.length) {
                    list.innerHTML = '<div class="notification-empty">اعلان جدیدی وجود ندارد.</div>';
                    return;
                }
                list.innerHTML = items.map(function (item) {
                    return '<a class="notification-item" href="' + escapeHtml(item.url) + '">' +
                        '<strong>' + escapeHtml(item.title) + ':</strong> ' + escapeHtml(item.message) +
                        '</a>';
                }).join('');
            }

            function showBrowserNotification(item) {
                if (!('Notification' in window) || Notification.permission !== 'granted') return;
                var notification = new Notification(item.title, {
                    body: item.message,
                    tag: 'payment-app-' + item.id
                });
                notification.onclick = function () {
                    window.focus();
                    if (item.url) window.location.href = item.url;
                    notification.close();
                };
            }

            async function poll() {
                if (!feedUrl) return;
                try {
                    var response = await fetch(feedUrl, { credentials: 'same-origin' });
                    if (!response.ok) return;
                    var data = await response.json();
                    var items = data.items || [];
                    updateBadge(data.unread_count || 0);
                    renderItems(items);
                    items.slice().sort(function (a, b) { return a.id - b.id; }).forEach(function (item) {
                        if (item.id > lastSeenId && !firstPoll) {
                            showBrowserNotification(item);
                        }
                        if (item.id > lastSeenId) {
                            lastSeenId = item.id;
                        }
                    });
                    if (lastSeenId) {
                        localStorage.setItem(storageKey, String(lastSeenId));
                    }
                    firstPoll = false;
                } catch (error) {
                    firstPoll = false;
                }
            }

            if (trigger) {
                trigger.addEventListener('click', function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    setOpen(!bell.classList.contains('open'));
                });
            }
            bell.addEventListener('click', function (event) {
                event.stopPropagation();
            });

            if (enableButton) {
                if (!('Notification' in window)) {
                    enableButton.style.display = 'none';
                } else if (Notification.permission === 'granted') {
                    enableButton.textContent = 'اعلان فعال است';
                }
                enableButton.addEventListener('click', async function () {
                    if (!('Notification' in window)) return;
                    var permission = await Notification.requestPermission();
                    enableButton.textContent = permission === 'granted' ? 'اعلان فعال است' : 'اجازه اعلان داده نشد';
                });
            }

            if (readButton) {
                readButton.addEventListener('click', async function () {
                    if (!readUrl) return;
                    await fetch(readUrl, {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'X-CSRFToken': getCookie('csrftoken'),
                            'Content-Type': 'application/x-www-form-urlencoded'
                        },
                        body: ''
                    });
                    await poll();
                });
            }

            poll();
            setInterval(poll, 30000);
        });
    }

    document.addEventListener('click', function () {
        document.querySelectorAll('.app-shell-nav.open').forEach(function (nav) {
            nav.classList.remove('open');
            var trigger = nav.querySelector('.app-nav-toggle');
            if (trigger) trigger.setAttribute('aria-expanded', 'false');
        });
        document.querySelectorAll('.notification-bell.open').forEach(function (bell) {
            bell.classList.remove('open');
            var trigger = bell.querySelector('.notification-trigger');
            if (trigger) trigger.setAttribute('aria-expanded', 'false');
        });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            document.querySelectorAll('.app-shell-nav.open').forEach(function (nav) {
                nav.classList.remove('open');
                var trigger = nav.querySelector('.app-nav-toggle');
                if (trigger) trigger.setAttribute('aria-expanded', 'false');
            });
            document.querySelectorAll('.notification-bell.open').forEach(function (bell) {
                bell.classList.remove('open');
                var trigger = bell.querySelector('.notification-trigger');
                if (trigger) trigger.setAttribute('aria-expanded', 'false');
            });
        }
    });

    document.addEventListener('DOMContentLoaded', function () {
        localStorage.removeItem('paymentAppTheme');
        document.documentElement.removeAttribute('data-theme');
        enhanceShellNavigation();
        enhanceTables();
        enhanceCustomerSelects();
        disableDateAutocomplete();
        enhanceNotifications();
        enhanceZoomableImages();
    });
}());
