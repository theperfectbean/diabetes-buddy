// Diabetes Buddy Web Interface - JavaScript

class DiabetesBuddyChat {
    constructor() {
        this.chatMessages = document.getElementById('chatMessages');
        this.queryInput = document.getElementById('queryInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.modal = document.getElementById('responseModal');
        this.modalBody = document.getElementById('modalBody');
        this.sourcesList = document.getElementById('sourcesList');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.exportBtn = document.getElementById('exportBtn');
        this.themeToggle = document.getElementById('themeToggle');

        // Configure marked.js for markdown
        if (window.marked) {
            marked.use({ breaks: true, gfm: true, mangle: false, headerIds: false });
        }

        // Initialize conversation
        this.conversationId = this.loadOrCreateConversation();
        this.messages = [];

        this.setupEventListeners();
        this.loadTheme();
        this.loadConversationHistory();
        this.loadSources();
    }

    // ============================================
    // Conversation & History Management
    // ============================================

    loadOrCreateConversation() {
        let id = localStorage.getItem('diabuddy_conversation_id');
        if (!id) {
            id = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            localStorage.setItem('diabuddy_conversation_id', id);
        }
        return id;
    }

    loadConversationHistory() {
        const history = localStorage.getItem(`diabuddy_history_${this.conversationId}`);
        if (history) {
            try {
                this.messages = JSON.parse(history);
                this.messages.forEach(msg => this.renderSavedMessage(msg));
            } catch (e) {
                console.error('Failed to load history:', e);
                this.messages = [];
            }
        }

        // Show welcome if no history
        if (this.messages.length === 0) {
            this.addWelcomeMessage();
        }
    }

    saveMessage(message) {
        this.messages.push(message);
        // Limit to last 50 messages
        if (this.messages.length > 50) {
            this.messages = this.messages.slice(-50);
        }
        localStorage.setItem(
            `diabuddy_history_${this.conversationId}`,
            JSON.stringify(this.messages)
        );
    }

    clearConversation() {
        localStorage.removeItem(`diabuddy_history_${this.conversationId}`);
        this.conversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        localStorage.setItem('diabuddy_conversation_id', this.conversationId);
        this.messages = [];
        this.chatMessages.innerHTML = '';
        this.addWelcomeMessage();
    }

    renderSavedMessage(msg) {
        if (msg.type === 'user') {
            this.addMessage(msg.content, 'user', false);
        } else if (msg.type === 'assistant') {
            this.addAssistantMessage(msg.data, false);
        }
    }

    // ============================================
    // Theme (Dark Mode)
    // ============================================

    loadTheme() {
        const savedTheme = localStorage.getItem('diabuddy_theme');
        if (savedTheme) {
            document.documentElement.setAttribute('data-theme', savedTheme);
            this.updateThemeIcon(savedTheme);
        } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.documentElement.setAttribute('data-theme', 'dark');
            this.updateThemeIcon('dark');
        }
    }

    toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('diabuddy_theme', next);
        this.updateThemeIcon(next);
    }

    updateThemeIcon(theme) {
        if (this.themeToggle) {
            this.themeToggle.innerHTML = theme === 'dark' ? '&#9728;' : '&#9790;';
            this.themeToggle.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`);
        }
    }

    // ============================================
    // Event Listeners
    // ============================================

    setupEventListeners() {
        this.sendBtn.addEventListener('click', () => this.sendQuery());
        this.queryInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendQuery();
            }
        });

        // New chat button
        if (this.newChatBtn) {
            this.newChatBtn.addEventListener('click', () => {
                if (confirm('Start a new conversation? Current chat will be cleared.')) {
                    this.clearConversation();
                }
            });
        }

        // Export button
        if (this.exportBtn) {
            this.exportBtn.addEventListener('click', () => this.exportConversation());
        }

        // Theme toggle
        if (this.themeToggle) {
            this.themeToggle.addEventListener('click', () => this.toggleTheme());
        }

        // Modal close
        const closeBtn = document.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeModal());
        }
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.closeModal();
        });

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.classList.contains('active')) {
                this.closeModal();
            }
        });

        // Focus trap for modal
        this.setupModalFocusTrap();

        // Mobile keyboard handling
        this.queryInput.addEventListener('focus', () => {
            setTimeout(() => {
                this.queryInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 300);
        });
    }

    setupModalFocusTrap() {
        this.modal.addEventListener('keydown', (e) => {
            if (e.key !== 'Tab') return;

            const focusableElements = this.modal.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            if (focusableElements.length === 0) return;

            const firstElement = focusableElements[0];
            const lastElement = focusableElements[focusableElements.length - 1];

            if (e.shiftKey && document.activeElement === firstElement) {
                e.preventDefault();
                lastElement.focus();
            } else if (!e.shiftKey && document.activeElement === lastElement) {
                e.preventDefault();
                firstElement.focus();
            }
        });
    }

    // ============================================
    // Query Handling
    // ============================================

    async sendQuery() {
        const query = this.queryInput.value.trim();

        // Validation
        if (!query) {
            this.showInputError('Please enter a question');
            return;
        }
        if (query.length < 3) {
            this.showInputError('Please ask a complete question');
            return;
        }
        if (query.length > 2000) {
            this.showInputError('Question is too long (max 2000 characters)');
            return;
        }

        // Clear input and disable button
        this.queryInput.value = '';
        this.sendBtn.disabled = true;

        // Add user message
        this.addMessage(query, 'user');
        this.saveMessage({ type: 'user', content: query, timestamp: Date.now() });

        // Add loading indicator
        const loadingId = this.addLoadingIndicator();

        try {
            const data = await this.sendQueryWithRetry(query);
            this.removeMessage(loadingId);
            this.addAssistantMessage(data);
            this.saveMessage({ type: 'assistant', data: data, timestamp: Date.now() });

        } catch (error) {
            this.removeMessage(loadingId);
            this.addMessage(`Error: ${error.message}`, 'system');
        } finally {
            this.sendBtn.disabled = false;
            this.queryInput.focus();
        }
    }

    async sendQueryWithRetry(query, maxRetries = 2) {
        let lastError;

        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query })
                });

                if (response.status === 429) {
                    throw new Error('Rate limit exceeded. Please wait a moment before trying again.');
                }

                if (response.status >= 500 && attempt < maxRetries) {
                    await this.delay(1000 * (attempt + 1));
                    continue;
                }

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || `Server error: ${response.statusText}`);
                }

                return await response.json();

            } catch (error) {
                lastError = error;
                if (error.name === 'TypeError' && attempt < maxRetries) {
                    // Network error - retry
                    await this.delay(1000 * (attempt + 1));
                    continue;
                }
                throw error;
            }
        }

        throw lastError;
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    showInputError(message) {
        // Remove existing error
        const existing = document.querySelector('.input-error');
        if (existing) existing.remove();

        const errorDiv = document.createElement('div');
        errorDiv.className = 'input-error';
        errorDiv.textContent = message;
        errorDiv.setAttribute('role', 'alert');

        const inputArea = document.querySelector('.input-area');
        inputArea.appendChild(errorDiv);

        setTimeout(() => errorDiv.remove(), 3000);
    }

    // ============================================
    // Message Rendering
    // ============================================

    addWelcomeMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message system welcome';

        messageDiv.innerHTML = `
            <div class="welcome-content">
                <p>Welcome to Diabetes Buddy! Ask me anything about diabetes management.</p>
                <div class="suggested-questions">
                    <p class="suggestion-label">Try asking:</p>
                    <div class="suggestion-buttons">
                        <button class="suggestion-btn" data-query="How do I change my pump cartridge?">
                            How do I change my pump cartridge?
                        </button>
                        <button class="suggestion-btn" data-query="What is Ease-off mode in CamAPS?">
                            What is Ease-off mode?
                        </button>
                        <button class="suggestion-btn" data-query="How should I prepare for exercise?">
                            How to prepare for exercise?
                        </button>
                    </div>
                </div>
            </div>
        `;

        messageDiv.querySelectorAll('.suggestion-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.queryInput.value = btn.dataset.query;
                this.sendQuery();
            });
        });

        this.chatMessages.appendChild(messageDiv);
    }

    addMessage(text, type = 'assistant', animate = true) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        if (!animate) messageDiv.style.animation = 'none';

        const p = document.createElement('p');
        p.textContent = text;
        messageDiv.appendChild(p);
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        return messageDiv;
    }

    addLoadingIndicator() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.id = `loading-${Date.now()}`;

        messageDiv.innerHTML = `
            <div class="loading-message">
                <div class="skeleton-line skeleton"></div>
                <div class="skeleton-line skeleton"></div>
                <div class="skeleton-line skeleton"></div>
                <div class="loading-status">
                    <span class="thinking-indicator">Searching knowledge base...</span>
                </div>
            </div>
        `;

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        return messageDiv.id;
    }

    removeMessage(id) {
        const element = document.getElementById(id);
        if (element) element.remove();
    }

    addAssistantMessage(data, animate = true) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        if (!animate) messageDiv.style.animation = 'none';

        const { cleaned, refList } = this.extractAndFormatReferences(data.answer, data.sources);
        const answerContainer = this.formatText(cleaned, refList);

        // Add severity indicator with icon
        const severityDiv = document.createElement('div');
        severityDiv.className = `severity ${data.severity}`;
        severityDiv.setAttribute('role', 'status');
        const icons = { INFO: '\u2713', WARNING: '\u26A0', BLOCKED: '\u2716' };
        severityDiv.innerHTML = `<span class="severity-icon">${icons[data.severity] || ''}</span> ${data.severity}`;
        answerContainer.insertBefore(severityDiv, answerContainer.firstChild);

        messageDiv.appendChild(answerContainer);

        // Disclaimer (if needed)
        if (data.severity !== 'INFO') {
            const disclaimer = document.createElement('div');
            disclaimer.className = 'disclaimer-warning';
            disclaimer.setAttribute('role', 'alert');
            disclaimer.textContent = data.disclaimer;
            messageDiv.appendChild(disclaimer);
        }

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }



    // ============================================
    // Reference Extraction & Formatting
    // ============================================

    extractAndFormatReferences(text, apiSources = []) {
        const references = {};
        const refList = [];
        let refCount = 0;

        // Use API-provided sources directly
        if (apiSources && apiSources.length > 0) {
            apiSources.forEach((source) => {
                const citation = `${source.source}${source.page ? `, Page ${source.page}` : ''}`;
                if (!references[citation]) {
                    refCount += 1;
                    references[citation] = refCount;
                    refList.push({
                        citation,
                        excerpt: source.excerpt,
                        confidence: source.confidence,
                        full_excerpt: source.full_excerpt
                    });
                }
            });
        }

        // Also extract inline citations from text
        const citationRegex = /\(([^)]+?(?:,\s*[Pp]age\s*\d+)?)\)/g;
        const matches = [...text.matchAll(citationRegex)];

        matches.forEach(match => {
            const citation = match[1];
            if (!references[citation] && this.looksLikeCitation(citation)) {
                refCount += 1;
                references[citation] = refCount;
                refList.push({ citation, excerpt: null, confidence: null });
            }
        });

        // Replace citations with superscript numbers
        let cleaned = text;
        Object.entries(references).forEach(([citation, num]) => {
            const full = `(${citation})`;
            cleaned = cleaned.split(full).join(`__REF${num}__`);
        });

        return { cleaned, refList };
    }

    looksLikeCitation(text) {
        const falsePositives = ['e.g.', 'i.e.', 'etc.', 'vs.'];
        if (falsePositives.some(fp => text.toLowerCase().includes(fp))) return false;
        const sourceKeywords = ['manual', 'page', 'pancreas', 'libre', 'camaps', 'ypsomed', 'think like'];
        return sourceKeywords.some(kw => text.toLowerCase().includes(kw));
    }

    formatLineWithReferences(text, references) {
        let line = text;
        references.forEach((ref, idx) => {
            const num = idx + 1;
            const citation = typeof ref === 'string' ? ref : ref.citation;
            line = line.replace(
                new RegExp(`__REF${num}__`, 'g'),
                `<sup class="ref-link" title="${citation}" data-ref="${num}">[${num}]</sup>`
            );
        });
        return line;
    }

    formatText(text, references = []) {
        const container = document.createElement('div');
        container.className = 'answer';

        // Remove disclaimers from the main text
        const withoutDisclaimers = text
            .split('\n')
            .filter(line => !line.toLowerCase().includes('disclaimer'))
            .join('\n');

        const withRefs = this.formatLineWithReferences(withoutDisclaimers, references);

        let html = withRefs;
        if (window.marked) {
            html = marked.parse(withRefs);
        } else {
            html = withRefs
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/__(.*?)__/g, '<strong>$1</strong>');
        }

        container.innerHTML = html;

        // Add references section
        if (references.length > 0) {
            const refSection = document.createElement('div');
            refSection.className = 'references-section';

            const title = document.createElement('div');
            title.className = 'ref-title';
            title.textContent = 'Sources';
            refSection.appendChild(title);

            const list = document.createElement('ol');
            list.className = 'references-list';
            references.forEach((ref, idx) => {
                const li = document.createElement('li');
                li.className = 'reference-item';
                const citation = typeof ref === 'string' ? ref : ref.citation;
                li.innerHTML = `<span class="ref-citation">${citation}</span>`;

                // Add view details button if we have excerpt
                if (ref.excerpt) {
                    const viewBtn = document.createElement('button');
                    viewBtn.className = 'ref-view-btn';
                    viewBtn.textContent = 'View';
                    viewBtn.addEventListener('click', () => this.showSourceDetails(ref));
                    li.appendChild(viewBtn);
                }

                list.appendChild(li);
            });
            refSection.appendChild(list);
            container.appendChild(refSection);
        }

        return container;
    }

    // ============================================
    // Modal & Source Details
    // ============================================

    showSourceDetails(source) {
        const confidence = source.confidence ? `${(source.confidence * 100).toFixed(0)}%` : 'N/A';
        const excerpt = source.full_excerpt || source.excerpt || 'No excerpt available';

        this.modalBody.innerHTML = `
            <h2 id="modalTitle">Source Details</h2>
            <p><strong>Source:</strong> ${source.citation || source.source}</p>
            <p><strong>Confidence:</strong> ${confidence}</p>
            <div class="source-excerpt">
                <strong>Excerpt:</strong>
                <p class="excerpt-text">${excerpt}</p>
            </div>
        `;
        this.modal.classList.add('active');
        this.modal.querySelector('.modal-close').focus();
    }

    closeModal() {
        this.modal.classList.remove('active');
        this.queryInput.focus();
    }

    // ============================================
    // Export Functionality
    // ============================================

    exportConversation() {
        if (this.messages.length === 0) {
            alert('No conversation to export.');
            return;
        }

        const format = prompt('Export format: Enter "text" for plain text or "json" for JSON', 'text');

        if (format === 'json') {
            this.downloadJSON();
        } else if (format === 'text') {
            this.downloadText();
        }
    }

    downloadText() {
        let content = `Diabetes Buddy Conversation\n`;
        content += `Exported: ${new Date().toLocaleString()}\n`;
        content += `${'='.repeat(50)}\n\n`;

        this.messages.forEach(msg => {
            const time = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : '';
            if (msg.type === 'user') {
                content += `[${time}] You:\n${msg.content}\n\n`;
            } else if (msg.type === 'assistant') {
                content += `[${time}] Diabetes Buddy:\n${msg.data.answer}\n`;
                content += `Classification: ${msg.data.classification} | Severity: ${msg.data.severity}\n\n`;
            }
        });

        this.downloadFile(content, 'diabetes-buddy-chat.txt', 'text/plain');
    }

    downloadJSON() {
        const data = {
            exportDate: new Date().toISOString(),
            conversationId: this.conversationId,
            messages: this.messages
        };

        this.downloadFile(JSON.stringify(data, null, 2), 'diabetes-buddy-chat.json', 'application/json');
    }

    downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // ============================================
    // Sources Sidebar
    // ============================================

    async loadSources() {
        try {
            const response = await fetch('/api/sources');
            const data = await response.json();

            this.sourcesList.innerHTML = '';

            data.sources.forEach(source => {
                const div = document.createElement('div');
                div.className = 'source-item';
                div.setAttribute('role', 'listitem');
                div.innerHTML = `
                    <strong>${source.name}</strong>
                    ${source.author ? `<small>${source.author}</small>` : ''}
                    <small>${source.description}</small>
                `;
                this.sourcesList.appendChild(div);
            });
        } catch (error) {
            this.sourcesList.innerHTML = `<div class="source-item error">Failed to load sources</div>`;
        }
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    new DiabetesBuddyChat();
});
