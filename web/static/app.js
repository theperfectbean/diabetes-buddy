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

        // Tab navigation
        this.chatTab = document.getElementById('chatTab');
        this.dataTab = document.getElementById('dataTab');
        this.chatPanel = document.getElementById('chatPanel');
        this.dataPanel = document.getElementById('dataPanel');

        // Data analysis elements
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.uploadProgress = document.getElementById('uploadProgress');
        this.dashboardSection = document.getElementById('dashboardSection');
        this.historyList = document.getElementById('historyList');

        // Configure marked.js for markdown
        if (window.marked) {
            marked.use({ breaks: true, gfm: true, mangle: false, headerIds: false });
        }

        // Initialize conversation
        this.conversationId = this.loadOrCreateConversation();
        this.messages = [];

        // Analysis state
        this.currentAnalysis = null;
        this.tirChart = null;

        this.setupEventListeners();
        this.setupDataAnalysisListeners();
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

    // ============================================
    // Tab Navigation
    // ============================================

    setupDataAnalysisListeners() {
        // Tab switching
        if (this.chatTab) {
            this.chatTab.addEventListener('click', () => this.switchTab('chat'));
        }
        if (this.dataTab) {
            this.dataTab.addEventListener('click', () => this.switchTab('data'));
        }

        // File upload - drag and drop
        if (this.uploadArea) {
            this.uploadArea.addEventListener('click', () => this.fileInput?.click());
            this.uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                this.uploadArea.classList.add('dragover');
            });
            this.uploadArea.addEventListener('dragleave', () => {
                this.uploadArea.classList.remove('dragover');
            });
            this.uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                this.uploadArea.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) this.uploadFile(files[0]);
            });
        }

        // File input change
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) this.uploadFile(e.target.files[0]);
            });
        }

        // Load history when data tab is shown
        if (this.dataPanel) {
            this.loadAnalysisHistory();
        }
    }

    switchTab(tab) {
        if (tab === 'chat') {
            this.chatTab?.classList.add('active');
            this.dataTab?.classList.remove('active');
            this.chatTab?.setAttribute('aria-selected', 'true');
            this.dataTab?.setAttribute('aria-selected', 'false');
            this.chatPanel?.classList.add('active');
            this.chatPanel?.removeAttribute('hidden');
            this.dataPanel?.classList.remove('active');
            this.dataPanel?.setAttribute('hidden', '');
        } else {
            this.dataTab?.classList.add('active');
            this.chatTab?.classList.remove('active');
            this.dataTab?.setAttribute('aria-selected', 'true');
            this.chatTab?.setAttribute('aria-selected', 'false');
            this.dataPanel?.classList.add('active');
            this.dataPanel?.removeAttribute('hidden');
            this.chatPanel?.classList.remove('active');
            this.chatPanel?.setAttribute('hidden', '');
            // Load latest analysis
            this.loadLatestAnalysis();
            this.loadAnalysisHistory();
        }
    }

    // ============================================
    // File Upload
    // ============================================

    async uploadFile(file) {
        // Validate file type
        if (!file.name.toLowerCase().endsWith('.zip')) {
            alert('Please upload a ZIP file exported from Glooko');
            return;
        }

        // Check size (50MB max)
        if (file.size > 50 * 1024 * 1024) {
            alert('File too large. Maximum size is 50MB');
            return;
        }

        // Show progress
        this.uploadProgress?.removeAttribute('hidden');
        this.uploadArea?.setAttribute('hidden', '');
        const progressFill = document.getElementById('progressFill');
        const uploadStatus = document.getElementById('uploadStatus');

        try {
            const formData = new FormData();
            formData.append('file', file);

            // Upload with progress simulation (fetch doesn't support progress)
            if (uploadStatus) uploadStatus.textContent = 'Uploading...';
            if (progressFill) progressFill.style.width = '30%';

            const response = await fetch('/api/upload-glooko', {
                method: 'POST',
                body: formData
            });

            if (progressFill) progressFill.style.width = '60%';

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const result = await response.json();
            if (progressFill) progressFill.style.width = '80%';

            // Run analysis
            if (uploadStatus) uploadStatus.textContent = 'Analyzing data...';
            await this.runAnalysis(result.filename);

            if (progressFill) progressFill.style.width = '100%';
            if (uploadStatus) uploadStatus.textContent = 'Complete!';

            // Reset after delay
            setTimeout(() => {
                this.uploadProgress?.setAttribute('hidden', '');
                this.uploadArea?.removeAttribute('hidden');
                if (progressFill) progressFill.style.width = '0%';
            }, 1500);

        } catch (error) {
            console.error('Upload error:', error);
            if (uploadStatus) uploadStatus.textContent = `Error: ${error.message}`;
            setTimeout(() => {
                this.uploadProgress?.setAttribute('hidden', '');
                this.uploadArea?.removeAttribute('hidden');
            }, 3000);
        }
    }

    // ============================================
    // Analysis Loading
    // ============================================

    async runAnalysis(filename = null) {
        try {
            const url = filename
                ? `/api/glooko-analysis/run?filename=${encodeURIComponent(filename)}`
                : '/api/glooko-analysis/run';

            const response = await fetch(url, { method: 'POST' });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Analysis failed');
            }

            const analysis = await response.json();
            this.displayAnalysis(analysis);
            this.loadAnalysisHistory();

        } catch (error) {
            console.error('Analysis error:', error);
            alert(`Analysis failed: ${error.message}`);
        }
    }

    async loadLatestAnalysis() {
        try {
            const response = await fetch('/api/glooko-analysis/latest');

            if (response.status === 404) {
                // No analysis available
                return;
            }

            if (!response.ok) {
                throw new Error('Failed to load analysis');
            }

            const analysis = await response.json();
            this.displayAnalysis(analysis);

        } catch (error) {
            console.error('Failed to load latest analysis:', error);
        }
    }

    async loadAnalysisHistory() {
        if (!this.historyList) return;

        try {
            const response = await fetch('/api/glooko-analysis/history');
            const data = await response.json();

            if (data.history.length === 0) {
                this.historyList.innerHTML = '<p class="no-history">No analysis history yet</p>';
                return;
            }

            this.historyList.innerHTML = data.history.map(item => `
                <div class="history-item ${item.status === 'not_analyzed' ? 'not-analyzed' : ''}"
                     data-id="${item.id || ''}" data-file="${item.file}">
                    <div class="history-info">
                        <span class="history-file">${item.file}</span>
                        <span class="history-date">${item.date ? new Date(item.date).toLocaleDateString() : 'Not analyzed'}</span>
                    </div>
                    ${item.time_in_range !== null ? `
                        <div class="history-metrics">
                            <span class="tir-badge ${this.getTIRClass(item.time_in_range)}">${item.time_in_range}% TIR</span>
                            <span class="patterns-count">${item.patterns_found} patterns</span>
                        </div>
                    ` : `
                        <button class="analyze-btn" onclick="window.diabuddyChat.runAnalysis('${item.file}')">Analyze</button>
                    `}
                </div>
            `).join('');

            // Add click handlers for history items with analysis
            this.historyList.querySelectorAll('.history-item[data-id]').forEach(item => {
                if (item.dataset.id) {
                    item.addEventListener('click', () => this.loadAnalysisById(item.dataset.id));
                    item.style.cursor = 'pointer';
                }
            });

        } catch (error) {
            console.error('Failed to load history:', error);
            this.historyList.innerHTML = '<p class="error">Failed to load history</p>';
        }
    }

    async loadAnalysisById(analysisId) {
        try {
            const response = await fetch(`/api/glooko-analysis/${analysisId}`);
            if (!response.ok) throw new Error('Failed to load analysis');

            const analysis = await response.json();
            this.displayAnalysis(analysis);
        } catch (error) {
            console.error('Failed to load analysis:', error);
        }
    }

    // ============================================
    // Dashboard Display
    // ============================================

    displayAnalysis(analysis) {
        this.currentAnalysis = analysis;
        this.dashboardSection?.removeAttribute('hidden');

        const metrics = analysis.metrics || {};

        // Update metric values
        this.updateElement('avgGlucose', metrics.average_glucose || '--');
        this.updateElement('stdDev', metrics.std_deviation || '--');
        this.updateElement('cvValue', metrics.coefficient_of_variation || '--');
        this.updateElement('totalReadings', metrics.total_glucose_readings || '--');
        this.updateElement('tirValue', metrics.time_in_range_percent ? `${metrics.time_in_range_percent}%` : '--');

        // Update time distribution bars
        this.updateTimeDistribution(
            metrics.time_below_range_percent || 0,
            metrics.time_in_range_percent || 0,
            metrics.time_above_range_percent || 0
        );

        // Draw TIR gauge
        this.drawTIRGauge(metrics.time_in_range_percent || 0);

        // Display patterns
        this.displayPatterns(analysis.patterns || []);

        // Display research questions
        this.displayResearchQuestions(analysis.research_queries || []);

        // Display warnings
        this.displayWarnings(analysis.warnings || []);
    }

    updateElement(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    updateTimeDistribution(below, inRange, above) {
        const belowBar = document.getElementById('belowBar');
        const inRangeBar = document.getElementById('inRangeBar');
        const aboveBar = document.getElementById('aboveBar');

        if (belowBar) {
            belowBar.style.flex = below || 0.1;
            document.getElementById('belowValue').textContent = `${below}%`;
        }
        if (inRangeBar) {
            inRangeBar.style.flex = inRange || 0.1;
            document.getElementById('inRangeValue').textContent = `${inRange}%`;
        }
        if (aboveBar) {
            aboveBar.style.flex = above || 0.1;
            document.getElementById('aboveValue').textContent = `${above}%`;
        }
    }

    drawTIRGauge(value) {
        const canvas = document.getElementById('tirGauge');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const centerX = canvas.width / 2;
        const centerY = canvas.height - 10;
        const radius = 80;

        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Draw background arc (grey)
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, Math.PI, 0, false);
        ctx.lineWidth = 20;
        ctx.strokeStyle = '#e0e0e0';
        ctx.stroke();

        // Draw value arc
        const angle = Math.PI + (value / 100) * Math.PI;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, Math.PI, angle, false);
        ctx.lineWidth = 20;

        // Color based on value
        if (value >= 70) {
            ctx.strokeStyle = '#4caf50'; // Green
        } else if (value >= 50) {
            ctx.strokeStyle = '#ff9800'; // Orange
        } else {
            ctx.strokeStyle = '#f44336'; // Red
        }
        ctx.stroke();
    }

    getTIRClass(value) {
        if (value >= 70) return 'tir-good';
        if (value >= 50) return 'tir-warning';
        return 'tir-danger';
    }

    displayPatterns(patterns) {
        const container = document.getElementById('patternsList');
        if (!container) return;

        if (patterns.length === 0) {
            container.innerHTML = '<p class="no-patterns">No significant patterns detected</p>';
            return;
        }

        container.innerHTML = patterns.map(p => `
            <div class="pattern-item ${this.getPatternClass(p.confidence)}">
                <div class="pattern-header">
                    <span class="pattern-type">${this.formatPatternType(p.type)}</span>
                    <span class="pattern-confidence">${Math.round(p.confidence * 100)}% confidence</span>
                </div>
                <p class="pattern-description">${p.description}</p>
                ${p.recommendation ? `<p class="pattern-recommendation">${p.recommendation}</p>` : ''}
            </div>
        `).join('');
    }

    formatPatternType(type) {
        const types = {
            'dawn_phenomenon': 'Dawn Phenomenon',
            'post_meal_spike': 'Post-Meal Spike',
            'nocturnal_hypo': 'Nocturnal Hypoglycemia',
            'exercise_drop': 'Exercise-Related Drop',
            'insulin_stacking': 'Insulin Stacking',
            'rebound_high': 'Rebound High',
            'consistent_high': 'Consistent Highs',
            'consistent_low': 'Consistent Lows',
            'high_variability': 'High Variability'
        };
        return types[type] || type.replace(/_/g, ' ');
    }

    getPatternClass(confidence) {
        if (confidence >= 0.7) return 'pattern-high';
        if (confidence >= 0.4) return 'pattern-medium';
        return 'pattern-low';
    }

    displayResearchQuestions(queries) {
        const container = document.getElementById('questionsList');
        if (!container) return;

        if (queries.length === 0) {
            container.innerHTML = '<p class="no-questions">No research questions available</p>';
            return;
        }

        container.innerHTML = queries.slice(0, 5).map(q => `
            <button class="question-btn" data-query="${this.escapeHtml(q.query)}">
                <span class="question-priority priority-${q.priority}">${q.priority}</span>
                <span class="question-text">${q.query}</span>
            </button>
        `).join('');

        // Add click handlers to ask questions
        container.querySelectorAll('.question-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const query = btn.dataset.query;
                this.switchTab('chat');
                this.queryInput.value = query;
                this.queryInput.focus();
            });
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    displayWarnings(warnings) {
        const section = document.getElementById('warningsSection');
        const list = document.getElementById('warningsList');
        if (!section || !list) return;

        if (warnings.length === 0) {
            section.setAttribute('hidden', '');
            return;
        }

        section.removeAttribute('hidden');
        list.innerHTML = warnings.map(w => `<li>${w}</li>`).join('');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.diabuddyChat = new DiabetesBuddyChat();
});
