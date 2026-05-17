/**
 * Bank Name Autocomplete JavaScript
 * Provides autocomplete functionality for bank name fields
 */

(function() {
    'use strict';

    console.log('[BankAutocomplete] Script loaded');

    function init() {
        console.log('[BankAutocomplete] Initializing...');
        const inputs = document.querySelectorAll('.bank-autocomplete-input');
        console.log('[BankAutocomplete] Found inputs:', inputs.length);

        if (inputs.length === 0) {
            console.warn('[BankAutocomplete] No inputs found with class "bank-autocomplete-input"');
            return;
        }

        inputs.forEach((input, idx) => {
            console.log('[BankAutocomplete] Initializing input', idx, input, 'data-bank-type:', input.dataset.bankType);
            new BankAutocomplete(input);
        });
    }

    class BankAutocomplete {
        constructor(inputElement) {
            this.input = inputElement;
            this.bankType = this.input.dataset.bankType || 'payer';
            this.suggestionsList = null;
            this.selectedIndex = -1;
            this.apiUrl = '/api/bank-names/';
            this.debounceTimer = null;
            this.minChars = 1;
            this.debounceDelay = 300;

            this.setupHTML();
            this.attachListeners();
        }

        setupHTML() {
            const container = document.createElement('div');
            container.className = 'bank-autocomplete-container';
            container.style.position = 'relative';
            container.style.width = '100%';

            this.suggestionsList = document.createElement('ul');
            this.suggestionsList.className = 'bank-autocomplete-suggestions';
            this.suggestionsList.style.display = 'none';
            this.suggestionsList.style.position = 'absolute';
            this.suggestionsList.style.top = '100%';
            this.suggestionsList.style.left = '0';
            this.suggestionsList.style.right = '0';
            this.suggestionsList.style.zIndex = '1000';
            this.suggestionsList.style.margin = '0';
            this.suggestionsList.style.padding = '0';
            this.suggestionsList.style.listStyle = 'none';
            this.suggestionsList.style.backgroundColor = '#fff';
            this.suggestionsList.style.border = '1px solid #ccc';
            this.suggestionsList.style.borderTop = 'none';
            this.suggestionsList.style.borderRadius = '0 0 4px 4px';
            this.suggestionsList.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.15)';
            this.suggestionsList.style.maxHeight = '200px';
            this.suggestionsList.style.overflowY = 'auto';

            this.input.parentNode.insertBefore(container, this.input.nextSibling);
            container.appendChild(this.input);
            container.appendChild(this.suggestionsList);

            this.addStyles();
        }

        addStyles() {
            if (document.getElementById('bank-autocomplete-styles')) {
                return;
            }

            const style = document.createElement('style');
            style.id = 'bank-autocomplete-styles';
            style.textContent = `
                .bank-autocomplete-container {
                    position: relative;
                }

                .bank-autocomplete-suggestions {
                    list-style: none;
                    margin: 0;
                    padding: 0;
                }

                .bank-autocomplete-suggestions li {
                    padding: 8px 12px;
                    cursor: pointer;
                    border-bottom: 1px solid #f0f0f0;
                }

                .bank-autocomplete-suggestions li:last-child {
                    border-bottom: none;
                }

                .bank-autocomplete-suggestions li:hover,
                .bank-autocomplete-suggestions li.selected {
                    background-color: #e8f4f8;
                }

                .bank-autocomplete-suggestions li.highlighted {
                    background-color: #0d6efd;
                    color: white;
                }
            `;
            document.head.appendChild(style);
        }

        attachListeners() {
            this.input.addEventListener('input', (e) => this.onInput(e));
            this.input.addEventListener('keydown', (e) => this.onKeyDown(e));
            this.input.addEventListener('focus', (e) => this.onFocus(e));
            document.addEventListener('click', (e) => this.onDocumentClick(e));
        }

        onInput(event) {
            const value = this.input.value.trim();
            clearTimeout(this.debounceTimer);

            if (value.length < this.minChars) {
                this.hideSuggestions();
                return;
            }

            this.debounceTimer = setTimeout(() => {
                this.fetchSuggestions(value);
            }, this.debounceDelay);
        }

        onKeyDown(event) {
            const items = this.suggestionsList.querySelectorAll('li');
            const visibleCount = items.length;

            if (!this.suggestionsList.style.display || this.suggestionsList.style.display === 'none') {
                if (event.key === 'ArrowDown' && this.input.value.trim().length >= this.minChars) {
                    event.preventDefault();
                    this.fetchSuggestions(this.input.value.trim());
                }
                return;
            }

            switch (event.key) {
                case 'ArrowDown':
                    event.preventDefault();
                    this.selectedIndex = Math.min(this.selectedIndex + 1, visibleCount - 1);
                    this.updateSelection();
                    break;
                case 'ArrowUp':
                    event.preventDefault();
                    this.selectedIndex = Math.max(this.selectedIndex - 1, -1);
                    this.updateSelection();
                    break;
                case 'Enter':
                    event.preventDefault();
                    if (this.selectedIndex >= 0 && this.selectedIndex < visibleCount) {
                        items[this.selectedIndex].click();
                    }
                    break;
                case 'Escape':
                    event.preventDefault();
                    this.hideSuggestions();
                    this.selectedIndex = -1;
                    break;
            }
        }

        onFocus(event) {
            const value = this.input.value.trim();
            if (value.length >= this.minChars) {
                this.showSuggestions();
            }
        }

        onDocumentClick(event) {
            if (!event.target.closest('.bank-autocomplete-container')) {
                this.hideSuggestions();
                this.selectedIndex = -1;
            }
        }

        async fetchSuggestions(query) {
            try {
                const params = new URLSearchParams({
                    q: query,
                    type: this.bankType,
                });

                const response = await fetch(`${this.apiUrl}?${params.toString()}`, {
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                    },
                });

                if (!response.ok) {
                    console.error('Autocomplete API error:', response.status);
                    return;
                }

                const data = await response.json();
                this.displaySuggestions(data.results || []);
            } catch (error) {
                console.error('Autocomplete fetch error:', error);
            }
        }

        displaySuggestions(results) {
            this.suggestionsList.innerHTML = '';
            this.selectedIndex = -1;

            if (results.length === 0) {
                this.hideSuggestions();
                return;
            }

            results.forEach((item, index) => {
                const li = document.createElement('li');
                li.textContent = item.text;
                li.dataset.value = item.id;
                li.addEventListener('click', () => this.selectItem(item.text));
                li.addEventListener('mouseenter', () => {
                    document.querySelectorAll('.bank-autocomplete-suggestions li').forEach((el) => {
                        el.classList.remove('highlighted');
                    });
                    li.classList.add('highlighted');
                    this.selectedIndex = index;
                });
                this.suggestionsList.appendChild(li);
            });

            this.showSuggestions();
        }

        updateSelection() {
            const items = this.suggestionsList.querySelectorAll('li');
            items.forEach((item, index) => {
                if (index === this.selectedIndex) {
                    item.classList.add('highlighted');
                    item.scrollIntoView({ block: 'nearest' });
                } else {
                    item.classList.remove('highlighted');
                }
            });
        }

        selectItem(value) {
            this.input.value = value;
            this.hideSuggestions();
            this.selectedIndex = -1;
            this.input.focus();
            this.input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        showSuggestions() {
            this.suggestionsList.style.display = 'block';
            this.suggestionsList.classList.add('show');
        }

        hideSuggestions() {
            this.suggestionsList.style.display = 'none';
            this.suggestionsList.classList.remove('show');
        }
    }

    window.BankAutocomplete = BankAutocomplete;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
