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

    /** tooltip خودکار روی سلول‌های بریده‌شده */
    function addTruncationTooltips(table) {
        requestAnimationFrame(function() {
            table.querySelectorAll('tbody td.cell-truncate').forEach(function(td) {
                if (td.scrollWidth > td.clientWidth + 1) {
                    td.setAttribute('title', td.textContent.trim());
                } else {
                    td.removeAttribute('title');
                }
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

            addTruncationTooltips(table);

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

    function fixCheckboxLabels() {
        // Place checkboxes inside their label elements and add a helper class
        document.querySelectorAll('.field-box input[type="checkbox"]').forEach(function(checkbox) {
            // Skip if this is part of a clearable file input (the "پاک کردن" checkbox)
            if (checkbox.closest('.clearable-file-input') || checkbox.parentNode.querySelector('input[type="file"]')) {
                return;
            }

            var fieldBox = checkbox.closest('.field-box');
            if (!fieldBox) return;

            // Find label by for attribute
            var label = document.querySelector('label[for="' + checkbox.id + '"]');
            if (!label) return;

            // If checkbox is not already inside label, move it into label as first child
            if (checkbox.parentNode !== label) {
                label.insertBefore(checkbox, label.firstChild);
            }

            // Mark label so CSS can style it
            label.classList.add('inline-checkbox');

            // Reset inline styles to avoid prior positioning issues
            checkbox.style.width = '';
            checkbox.style.height = '';
            checkbox.style.margin = '';
            checkbox.style.cursor = 'pointer';
            checkbox.style.flexShrink = '';
            checkbox.style.verticalAlign = '';

            // Ensure field box spacing
            fieldBox.style.display = '';
        });
    }

    function displayOnlyFileNameInFileInputs() {
        // Find all file input fields and show only the filename (not the full path)
        document.querySelectorAll('input[type="file"]').forEach(function(fileInput) {
            // Get the parent container
            var container = fileInput.parentNode;
            if (!container) return;
            
            // Find all links with /media/ path
            var links = container.querySelectorAll('a[href*="/media/"]');
            links.forEach(function(link) {
                var href = link.getAttribute('href');
                if (href) {
                    // Extract just the filename from the full path
                    var filename = href.split('/').pop();
                    link.textContent = filename;
                    // Optionally limit width to prevent layout issues
                    link.style.maxWidth = '250px';
                    link.style.display = 'inline-block';
                    link.style.overflow = 'hidden';
                    link.style.textOverflow = 'ellipsis';
                    
                    // Prevent default navigation and open image in modal instead
                    link.addEventListener('click', function(event) {
                        event.preventDefault();
                        showImageInModal(href);
                    });
                }
            });
            
            // Also find any paragraphs containing file path text and clean them
            var paragraphs = container.querySelectorAll('p');
            paragraphs.forEach(function(p) {
                var text = p.textContent || '';
                // If paragraph contains a file path pattern, update it
                if (text.includes('/media/')) {
                    // Find href in the link inside this p tag if exists
                    var link = p.querySelector('a[href*="/media/"]');
                    if (link) {
                        // Already handled above
                        return;
                    }
                    // Otherwise, replace the text directly
                    var match = text.match(/\/([^\/]+\.(jpg|jpeg|png|gif|webp|bmp|tif|tiff))$/i);
                    if (match) {
                        p.textContent = match[1]; // Just show the filename
                    }
                }
            });
        });
    }

    function fixClearableFileInputs() {
        // For Django's clearable-file-input paragraphs, ensure checkbox and label stay inline
        document.querySelectorAll('.clearable-file-input').forEach(function(container) {
            var p = container.querySelector('p') || container;
            var chk = p.querySelector('input[type="checkbox"]');
            var lbl = p.querySelector('label');
            if (!chk || !lbl) return;

            // If already wrapped, skip
            if (lbl.previousElementSibling === chk && lbl.parentNode.classList.contains('clear-checkbox-wrap')) {
                return;
            }

            // Create wrapper and insert before the checkbox
            var wrap = document.createElement('span');
            wrap.className = 'clear-checkbox-wrap';
            // Insert wrapper at checkbox position
            p.insertBefore(wrap, chk);
            // Move checkbox and label into wrapper
            wrap.appendChild(chk);
            wrap.appendChild(lbl);
        });
    }

    function showImageInModal(imageUrl) {
        // Check if modal already exists, if so reuse it
        var existingModal = document.querySelector('.file-preview-modal');
        if (existingModal) {
            existingModal.remove();
        }
        
        // Create modal overlay
        var modal = document.createElement('div');
        modal.className = 'file-preview-modal';
        modal.style.cssText = `
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            opacity: 0;
            transition: opacity 0.2s ease;
        `;
        
        // Create modal content container
        var content = document.createElement('div');
        content.style.cssText = `
            position: relative;
            max-width: 90vw;
            max-height: 90vh;
            background: white;
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: auto;
        `;
        
        // Create close button
        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.innerHTML = '✕';
        closeBtn.style.cssText = `
            position: absolute;
            top: 8px;
            right: 8px;
            background: rgba(0, 0, 0, 0.6);
            color: white;
            border: none;
            border-radius: 50%;
            width: 36px;
            height: 36px;
            font-size: 20px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
            transition: background 0.2s ease;
        `;
        closeBtn.addEventListener('mouseover', function() {
            closeBtn.style.background = 'rgba(0, 0, 0, 0.9)';
        });
        closeBtn.addEventListener('mouseout', function() {
            closeBtn.style.background = 'rgba(0, 0, 0, 0.6)';
        });
        
        // Create image element
        var img = document.createElement('img');
        img.src = imageUrl;
        img.style.cssText = `
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border-radius: 4px;
        `;
        
        // Assemble modal
        content.appendChild(closeBtn);
        content.appendChild(img);
        modal.appendChild(content);
        document.body.appendChild(modal);
        
        // Trigger animation
        setTimeout(function() {
            modal.style.opacity = '1';
        }, 10);
        
        // Close function
        function closeModal() {
            modal.style.opacity = '0';
            setTimeout(function() {
                if (modal.parentNode) {
                    modal.parentNode.removeChild(modal);
                }
            }, 200);
        }
        
        // Close on button click
        closeBtn.addEventListener('click', closeModal);
        
        // Close on overlay click (not on content)
        modal.addEventListener('click', function(event) {
            if (event.target === modal) {
                closeModal();
            }
        });
        
        // Close on ESC key
        function handleKeyPress(event) {
            if (event.key === 'Escape' || event.keyCode === 27) {
                closeModal();
                document.removeEventListener('keydown', handleKeyPress);
            }
        }
        document.addEventListener('keydown', handleKeyPress);
    }

    function enhanceAvatarUploadPreview() {
        document.querySelectorAll('form').forEach(function (form) {
            if (form.dataset.avatarPreviewReady === '1') return;
            var fileInput = form.querySelector('input[type="file"][name="avatar_image"]');
            var preview = form.querySelector('.profile-avatar-preview');
            if (!fileInput || !preview) return;
            form.dataset.avatarPreviewReady = '1';

            var avatarBox = preview.querySelector('.app-user-avatar');
            if (!avatarBox) return;

            avatarBox.style.position = 'relative';
            avatarBox.style.overflow = 'hidden';

            var hiddenFields = {};
            ['avatar_crop_x', 'avatar_crop_y', 'avatar_crop_width', 'avatar_crop_height'].forEach(function(name) {
                var input = form.querySelector('[name="' + name + '"]');
                if (!input) {
                    input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = name;
                    form.appendChild(input);
                }
                hiddenFields[name] = input;
            });

            var overlay = document.createElement('div');
            overlay.className = 'profile-avatar-cropper-overlay';
            overlay.style.display = 'none';
            overlay.style.pointerEvents = 'auto'; // Ensure pointer events reach this element
            overlay.innerHTML =
                '<div class="profile-avatar-cropper-backdrop"></div>' +
                '<div class="profile-avatar-cropper-dialog">' +
                  '<button type="button" class="avatar-cropper-close" aria-label="بستن">×</button>' +
                  '<h2>تنظیم نمایه</h2>' +
                  '<div class="avatar-cropper-viewer" aria-label="نمایش تصویر برای برش">' +
                    '<img class="avatar-cropper-image" alt="پیش‌نمایش کراپ">' +
                    '<div class="avatar-cropper-mask"></div>' +
                  '</div>' +
                  '<div class="avatar-cropper-controls">' +
                    '<button type="button" class="avatar-zoom-out" title="کوچک کردن">-</button>' +
                    '<span class="avatar-zoom-label">100%</span>' +
                    '<button type="button" class="avatar-zoom-in" title="بزرگ کردن">+</button>' +
                    '<button type="button" class="avatar-reset">بازنشانی</button>' +
                  '</div>' +
                  '<div class="avatar-cropper-actions">' +
                    '<button type="button" class="avatar-cropper-save">ثبت</button>' +
                    '<button type="button" class="avatar-cropper-cancel">انصراف</button>' +
                  '</div>' +
                '</div>';
            document.body.appendChild(overlay);

            var viewer = overlay.querySelector('.avatar-cropper-viewer');
            var cropImage = overlay.querySelector('.avatar-cropper-image');
            var cropClose = overlay.querySelector('.avatar-cropper-close');
            var zoomOut = overlay.querySelector('.avatar-zoom-out');
            var zoomIn = overlay.querySelector('.avatar-zoom-in');
            var zoomLabel = overlay.querySelector('.avatar-zoom-label');
            var resetButton = overlay.querySelector('.avatar-reset');
            var saveButton = overlay.querySelector('.avatar-cropper-save');
            var cancelButton = overlay.querySelector('.avatar-cropper-cancel');
            var backdrop = overlay.querySelector('.profile-avatar-cropper-backdrop');

            var state = {
                naturalWidth: 0,
                naturalHeight: 0,
                displayWidth: 0,
                displayHeight: 0,
                scale: 1,
                x: 0,
                y: 0,
                active: false,
                startX: 0,
                startY: 0,
                baseX: 0,
                baseY: 0,
                objectUrl: null,
                previewUrl: null,
            };

            function clamp(value, min, max) {
                return Math.min(max, Math.max(min, value));
            }

            function updateImage() {
                if (!cropImage) return;
                var viewerRect = viewer.getBoundingClientRect();
                // Fit image to cover the viewer area while preserving aspect ratio.
                var baseScale = Math.max(viewerRect.width / state.naturalWidth, viewerRect.height / state.naturalHeight);
                state.displayWidth = state.naturalWidth * baseScale;
                state.displayHeight = state.naturalHeight * baseScale;
                cropImage.style.width = state.displayWidth + 'px';
                cropImage.style.height = state.displayHeight + 'px';
                cropImage.style.position = 'absolute';
                cropImage.style.top = '50%';
                cropImage.style.left = '50%';
                cropImage.style.transformOrigin = 'center center';
                // keep the image centered then apply scale and pixel offset
                cropImage.style.transform = 'translate(-50%, -50%) scale(' + state.scale + ') translate(' + state.x + 'px, ' + state.y + 'px)';
            }

            function getBounds() {
                var viewerRect = viewer.getBoundingClientRect();
                var scaledWidth = state.displayWidth * state.scale;
                var scaledHeight = state.displayHeight * state.scale;
                var extraX = Math.max(0, (scaledWidth - viewerRect.width) / 2);
                var extraY = Math.max(0, (scaledHeight - viewerRect.height) / 2);
                return {
                    minX: -extraX,
                    maxX: extraX,
                    minY: -extraY,
                    maxY: extraY,
                };
            }

            function setTransform(x, y, scale) {
                        state.scale = clamp(scale, 0.3, 3);
                var bounds = getBounds();
                state.x = clamp(x, bounds.minX, bounds.maxX);
                state.y = clamp(y, bounds.minY, bounds.maxY);
                        cropImage.style.transform = 'translate(-50%, -50%) scale(' + state.scale + ') translate(' + state.x + 'px, ' + state.y + 'px)';
                zoomLabel.textContent = Math.round(state.scale * 100) + '%';
            }

            function resetPosition() {
                state.scale = 1;
                state.x = 0;
                state.y = 0;
                updateImage();
                setTransform(0, 0, 1);
                zoomLabel.textContent = '100%';
            }

            function startDrag(event, target) {
                state.active = true;
                state.startX = event.clientX;
                state.startY = event.clientY;
                state.baseX = state.x;
                state.baseY = state.y;
                cropImage.style.cursor = 'grabbing';
                try {
                    target.setPointerCapture(event.pointerId);
                } catch (e) {
                    // ignore if pointer capture is not available on this element
                }
                event.preventDefault();
            }

            function dragMove(event) {
                if (!state.active) return;
                var newX = state.baseX + event.clientX - state.startX;
                var newY = state.baseY + event.clientY - state.startY;
                setTransform(newX, newY, state.scale);
            }

            function endDrag(event) {
                state.active = false;
                cropImage.style.cursor = 'grab';
                try {
                    cropImage.releasePointerCapture(event.pointerId);
                } catch (e) {}
            }

            function showOverlay(file) {
                if (state.objectUrl) {
                    URL.revokeObjectURL(state.objectUrl);
                }
                state.objectUrl = URL.createObjectURL(file);
                cropImage.src = state.objectUrl;
                overlay.style.display = 'flex';
                cropImage.onload = function () {
                    state.naturalWidth = cropImage.naturalWidth;
                    state.naturalHeight = cropImage.naturalHeight;
                    // Ensure layout has settled before computing display sizes
                    requestAnimationFrame(function () {
                        requestAnimationFrame(function () {
                            resetPosition();
                        });
                    });
                };
            }

            function hideOverlay() {
                overlay.style.display = 'none';
                if (state.objectUrl) {
                    URL.revokeObjectURL(state.objectUrl);
                    state.objectUrl = null;
                }
            }

            var dialog = overlay.querySelector('.profile-avatar-cropper-dialog');
            if (dialog) {
                dialog.addEventListener('click', function (event) {
                    event.stopPropagation();
                });
            }

            overlay.addEventListener('click', function (event) {
                if (event.target === overlay || event.target === backdrop) {
                    hideOverlay();
                }
            });

            function updatePreviewImage(url) {
                if (!url) return;
                var previewImg = avatarBox.querySelector('img');
                if (!previewImg) {
                    avatarBox.textContent = '';
                    previewImg = document.createElement('img');
                    avatarBox.appendChild(previewImg);
                }
                previewImg.src = url;
                previewImg.style.width = '100%';
                previewImg.style.height = '100%';
                previewImg.style.objectFit = 'cover';
                previewImg.style.position = 'absolute';
                previewImg.style.top = '0';
                previewImg.style.left = '0';
                previewImg.style.transform = 'none';
                previewImg.style.cursor = 'default';
                state.previewUrl = url;
            }

            function saveCrop() {
                // Compute the crop rectangle by reading the computed position/size
                var viewerRect = viewer.getBoundingClientRect();
                var imgRect = cropImage.getBoundingClientRect();

                // compute overlap of image and viewer in viewport coordinates
                var overlapLeft = Math.max(viewerRect.left, imgRect.left);
                var overlapTop = Math.max(viewerRect.top, imgRect.top);
                var overlapRight = Math.min(viewerRect.right, imgRect.right);
                var overlapBottom = Math.min(viewerRect.bottom, imgRect.bottom);

                var visibleWidth = Math.max(0, overlapRight - overlapLeft);
                var visibleHeight = Math.max(0, overlapBottom - overlapTop);

                var cropXOnImage = Math.max(0, overlapLeft - imgRect.left);
                var cropYOnImage = Math.max(0, overlapTop - imgRect.top);

                var origCropX = (cropXOnImage / imgRect.width) * state.naturalWidth;
                var origCropY = (cropYOnImage / imgRect.height) * state.naturalHeight;
                var origCropWidth = (visibleWidth / imgRect.width) * state.naturalWidth;
                var origCropHeight = (visibleHeight / imgRect.height) * state.naturalHeight;

                hiddenFields.avatar_crop_x.value = Math.round(origCropX);
                hiddenFields.avatar_crop_y.value = Math.round(origCropY);
                hiddenFields.avatar_crop_width.value = Math.round(origCropWidth);
                hiddenFields.avatar_crop_height.value = Math.round(origCropHeight);

                // Create a cropped preview using an offscreen canvas so the preview matches the saved crop
                try {
                    var canvas = document.createElement('canvas');
                    var outSize = Math.max(64, Math.min(200, avatarBox.clientWidth || 92));
                    canvas.width = outSize;
                    canvas.height = outSize;
                    var ctx = canvas.getContext('2d');
                    var srcImg = new Image();
                    srcImg.onload = function () {
                        try {
                            ctx.drawImage(srcImg, origCropX, origCropY, origCropWidth, origCropHeight, 0, 0, canvas.width, canvas.height);
                            var dataUrl = canvas.toDataURL('image/jpeg', 0.9);
                            updatePreviewImage(dataUrl);
                        } catch (err) {
                            updatePreviewImage(state.objectUrl);
                        }
                        hideOverlay();
                    };
                    srcImg.onerror = function () {
                        updatePreviewImage(state.objectUrl);
                        hideOverlay();
                    };
                    srcImg.src = state.objectUrl || cropImage.src;
                } catch (e) {
                    updatePreviewImage(state.objectUrl);
                    hideOverlay();
                }
            }

            // Improve panning reliability: disable default touch actions and
            // attach move/up listeners to the overlay so dragging continues
            // even if the pointer leaves the image element (overlay covers viewport).
            cropImage.style.touchAction = 'none';
            cropImage.style.userSelect = 'none';
            cropImage.style.cursor = 'grab';

            cropImage.addEventListener('pointerdown', function (event) {
                startDrag(event, cropImage);
            });
            
            overlay.addEventListener('pointermove', function(event) {
                dragMove(event);
            });
            
            overlay.addEventListener('pointerup', function(event) {
                endDrag(event);
            });
            
            overlay.addEventListener('pointercancel', function(event) {
                endDrag(event);
            });

            zoomIn.addEventListener('click', function () {
                setTransform(state.x, state.y, state.scale + 0.1);
            });
            zoomOut.addEventListener('click', function () {
                setTransform(state.x, state.y, state.scale - 0.1);
            });
            resetButton.addEventListener('click', function () {
                resetPosition();
            });
            cancelButton.addEventListener('click', function () {
                hideOverlay();
            });
            cropClose.addEventListener('click', function () {
                hideOverlay();
            });
            backdrop.addEventListener('click', function () {
                hideOverlay();
            });
            saveButton.addEventListener('click', function () {
                saveCrop();
            });

            fileInput.addEventListener('change', function () {
                var file = fileInput.files && fileInput.files[0];
                if (!file || !file.type.startsWith('image/')) return;
                showOverlay(file);
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

            viewer.addEventListener('pointerdown', function (event) {
                if (event.target === cropImage) return;
                startDrag(event);
            });
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
                    list.innerHTML = '<div class="notification-empty">📭 پیام جدیدی وجود ندارد.</div>';
                    return;
                }
                list.innerHTML = items.map(function (item) {
                    var icon = item.icon || '🔔';
                    var time = item.time_label ? '<span class="notif-time">' + escapeHtml(item.time_label) + '</span>' : '';
                    return '<a class="notification-item" href="' + escapeHtml(item.url) + '" data-notif-id="' + item.id + '">' +
                        '<span class="notif-icon">' + icon + '</span>' +
                        '<span class="notif-body">' +
                            '<strong class="notif-title">' + escapeHtml(item.title) + '</strong>' +
                            '<span class="notif-msg">' + escapeHtml(item.message) + '</span>' +
                            time +
                        '</span>' +
                        '</a>';
                }).join('');

                // کلیک روی هر item → read شدن همان notification و به‌روزرسانی فوری شمارنده
                list.querySelectorAll('[data-notif-id]').forEach(function (link) {
                    link.addEventListener('click', function () {
                        var nid = link.dataset.notifId;
                        if (!readUrl || !nid || link.dataset.notifRead === '1') return;
                        link.dataset.notifRead = '1';
                        // keepalive: درخواست با وجود انتقال صفحه (کلیک روی لینک) ناتمام نمی‌ماند
                        fetch(readUrl, {
                            method: 'POST',
                            credentials: 'same-origin',
                            keepalive: true,
                            headers: {
                                'X-CSRFToken': getCookie('csrftoken'),
                                'Content-Type': 'application/x-www-form-urlencoded'
                            },
                            body: 'id=' + encodeURIComponent(nid)
                        }).then(function (response) {
                            return response.ok ? response.json() : null;
                        }).then(function (data) {
                            if (data && typeof data.unread_count === 'number') updateBadge(data.unread_count);
                        }).catch(function () { /* silent */ });
                    });
                });
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
                trigger.addEventListener('click', async function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    var wasOpen = bell.classList.contains('open');
                    setOpen(!wasOpen);
                    // باز کردن → mark all as read بعد از ۲ ثانیه (کاربر دید)
                    if (!wasOpen && readUrl) {
                        setTimeout(async function () {
                            try {
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
                            } catch (e) { /* silent */ }
                        }, 2000);
                    }
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
        document.querySelectorAll('.app-nav-group[open]').forEach(function (group) {
            group.removeAttribute('open');
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
            document.querySelectorAll('.app-nav-group[open]').forEach(function (group) {
                group.removeAttribute('open');
            });
            document.querySelectorAll('.notification-bell.open').forEach(function (bell) {
                bell.classList.remove('open');
                var trigger = bell.querySelector('.notification-trigger');
                if (trigger) trigger.setAttribute('aria-expanded', 'false');
            });
        }
    });

    function enhanceNavDropdowns() {
        document.querySelectorAll('.app-nav-dropdown').forEach(function(dd) {
            var btn = dd.querySelector('.app-nav-drop-btn');
            if (!btn) return;
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                var isOpen = dd.classList.toggle('open');
                // بستن بقیه dropdown ها
                document.querySelectorAll('.app-nav-dropdown.open').forEach(function(other) {
                    if (other !== dd) other.classList.remove('open');
                });
            });
        });

        document.addEventListener('click', function() {
            document.querySelectorAll('.app-nav-dropdown.open').forEach(function(dd) {
                dd.classList.remove('open');
            });
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                document.querySelectorAll('.app-nav-dropdown.open').forEach(function(dd) {
                    dd.classList.remove('open');
                });
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        localStorage.removeItem('paymentAppTheme');
        document.documentElement.removeAttribute('data-theme');
        enhanceShellNavigation();
        enhanceNavDropdowns();
        enhanceTables();
        document.querySelectorAll('.app-table-wrap table').forEach(function(t) {
            addTruncationTooltips(t);
        });
        enhanceCustomerSelects();
        disableDateAutocomplete();
        fixCheckboxLabels();
        displayOnlyFileNameInFileInputs();
        enhanceAvatarUploadPreview();
        enhanceNotifications();
        enhanceZoomableImages();
        
        // Run displayOnlyFileNameInFileInputs again after a short delay
        // to catch dynamically rendered elements
        setTimeout(function() {
            fixCheckboxLabels();
            displayOnlyFileNameInFileInputs();
        }, 100);
    });
}());
