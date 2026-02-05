// Diabetes Buddy Web Interface - JavaScript

class DiabetesBuddyChat {
    // Source display name mapping - fixes 'undefined' in KB status
    SOURCE_DISPLAY_NAMES = {
        'ada_standards': 'ADA Standards of Care',
        'australian_guidelines': 'Australian Diabetes Guidelines',
        'openaps_docs': 'OpenAPS Documentation',
        'loop_docs': 'Loop Documentation',
        'androidaps_docs': 'AndroidAPS Documentation',
        'wikipedia_education': 'Wikipedia T1D Education',
        'research_papers': 'PubMed Research Papers',
        'camaps_docs': 'CamAPS Documentation',
        'user_sources': 'Your Uploaded Documents',
        'user_manuals': 'Your Uploaded Documents',
        'glooko': 'Glooko Data',
        'general': 'General Medical Knowledge'
    };

    constructor() {
        console.log('DiabetesBuddyChat constructor called');
        
        this.chatMessages = document.getElementById('chatMessages');
        this.queryInput = document.getElementById('queryInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.modal = document.getElementById('responseModal');
        this.modalBody = document.getElementById('modalBody');
        this.sourcesList = document.getElementById('sourcesList');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.exportBtn = document.getElementById('exportBtn');
        this.themeToggle = document.getElementById('themeToggle');

        // Conversation sidebar elements
        this.conversationList = document.getElementById('conversationList');
        this.newConversationBtn = document.getElementById('newConversationBtn');

        // Settings modal elements
        this.settingsBtn = document.getElementById('settingsBtn');
        this.settingsModal = document.getElementById('settingsModal');
        this.pdfUploadArea = document.getElementById('pdfUploadArea');
        this.pdfFileInput = document.getElementById('pdfFileInput');

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

        console.log('Elements initialized:');
        console.log('  uploadArea:', this.uploadArea);
        console.log('  fileInput:', this.fileInput);
        console.log('  uploadProgress:', this.uploadProgress);

        // Configure marked.js for markdown
        if (window.marked) {
            marked.setOptions({
                breaks: true,
                gfm: true,
                mangle: false,
                headerIds: false,
                pedantic: false
            });
            console.log('✓ Marked.js configured for markdown parsing');
        } else {
            console.warn('⚠️  Marked.js not available - markdown will use fallback HTML conversion');
        }
        
        // Configure DOMPurify for XSS prevention
        if (window.DOMPurify) {
            console.log('✓ DOMPurify loaded for HTML sanitization');
        }

        // Initialize conversation - always start with empty chat
        this.conversationId = null;
        this.messages = [];
        this.conversations = []; // List of all conversations

        this.sessionId = this.getOrCreateSessionId();

        this.currentAnalysis = null;
        this.tirChart = null;

        this.setupEventListeners();
        this.setupDataAnalysisListeners();
        this.setupDeviceConfirmation();
        this.setupGlucoseUnitSettings();
        this.loadTheme();
        this.loadGlucoseUnit();
        this.loadConversationHistory();
        this.loadSources();

        // Show welcome box on initial page load
        this.showWelcomeState();

        console.log('DiabetesBuddyChat initialization complete');
    }

    getOrCreateSessionId() {
        const storageKey = 'diabuddy_session_id';
        let sessionId = localStorage.getItem(storageKey);
        if (!sessionId) {
            if (window.crypto?.randomUUID) {
                sessionId = window.crypto.randomUUID();
            } else {
                sessionId = `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
            }
            localStorage.setItem(storageKey, sessionId);
        }
        return sessionId;
    }

    /**
     * Get display name for a source, with fallback handling
     * @param {Object} source - Source object from API
     * @returns {string} Display name for the source
     */
    getSourceDisplayName(source) {
        if (!source) return 'Unknown Source';

        const sourceId = source.id || source.key || source.collection_key || source.collection_name || source.source_id || '';
        const sourceName = source.display_name || source.name || source.collection_name || sourceId || '';
        const filename = source.filename || '';

        if (sourceId && this.SOURCE_DISPLAY_NAMES[sourceId]) {
            return this.SOURCE_DISPLAY_NAMES[sourceId];
        }
        if (sourceName && this.SOURCE_DISPLAY_NAMES[sourceName.toLowerCase()]) {
            return this.SOURCE_DISPLAY_NAMES[sourceName.toLowerCase()];
        }
        if (filename) {
            const withoutExt = filename.replace(/\.[^/.]+$/, '');
            const pretty = withoutExt.replace(/[_-]+/g, ' ').trim();
            if (pretty) {
                return pretty.replace(/\b\w/g, (c) => c.toUpperCase());
            }
            return filename;
        }

        return sourceName || sourceId || 'Unknown Source';
    }

    /**
     * Update knowledge breakdown display with RAG/Parametric percentages
     * @param {Object} breakdown - Knowledge breakdown object from response
     */
    async updateKnowledgeBreakdownDisplay(breakdown) {
        const kbStatus = document.getElementById('kbStatus');
        if (!kbStatus || !breakdown) return;

        let breakdownDiv = kbStatus.querySelector('.kb-breakdown');
        if (!breakdownDiv) {
            breakdownDiv = document.createElement('div');
            breakdownDiv.className = 'kb-breakdown';
            kbStatus.appendChild(breakdownDiv);
        }

        const ragPercent = Math.round(breakdown.rag_ratio * 100);
        const paraPercent = Math.round(breakdown.parametric_ratio * 100);

        breakdownDiv.innerHTML = `
            <div class="breakdown-stats">
                <div class="breakdown-item">
                    <span class="stat-label">RAG</span>
                    <span class="stat-value">${ragPercent}%</span>
                </div>
                <div class="breakdown-item">
                    <span class="stat-label">Parametric</span>
                    <span class="stat-value">${paraPercent}%</span>
                </div>
            </div>
        `;
    }

    // ============================================
    // Welcome Box / Chat State Management
    // ============================================

    /**
     * Show the welcome state with sample questions.
     * Called on initial page load and when starting a new chat.
     */
    showWelcomeState() {
        this.chatMessages.innerHTML = '';
        this.addWelcomeMessage();
    }

    /**
     * Hide welcome and show chat interface.
     * Called when first message is sent or conversation is loaded.
     */
    showChatState() {
        // Remove any welcome message if present
        const welcomeMsg = this.chatMessages.querySelector('.message.welcome');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }
    }

    // ============================================
    // Conversation & History Management
    // ============================================

    async loadConversationHistory() {
        try {
            const response = await fetch('/api/conversations');
            if (response.ok) {
                this.conversations = await response.json();
                this.renderConversationList();
            } else {
                console.error('Failed to load conversations');
                this.conversations = [];
            }
        } catch (error) {
            console.error('Error loading conversation history:', error);
            this.conversations = [];
        }
    }

    async createNewConversation() {
        try {
            const response = await fetch('/api/conversations', { method: 'POST' });
            if (response.ok) {
                const data = await response.json();
                this.conversationId = data.conversationId;
                return this.conversationId;
            }
        } catch (error) {
            console.error('Error creating new conversation:', error);
        }
        return null;
    }

    async loadConversation(conversationId) {
        try {
            console.log('Loading conversation:', conversationId);
            const response = await fetch(`/api/conversations/${conversationId}`);
            if (response.ok) {
                const conversation = await response.json();
                console.log('Conversation loaded:', conversation);
                this.conversationId = conversationId;
                this.messages = conversation.messages || [];
                console.log(`Loaded ${this.messages.length} messages`);

                // Clear current chat (including any welcome message) and render messages
                this.chatMessages.innerHTML = '';

                // Only render messages if there are any
                if (this.messages.length > 0) {
                    console.log('Rendering saved messages');
                    this.messages.forEach((msg, idx) => {
                        console.log(`  Rendering message ${idx+1}: type=${msg.type}, contentLength=${msg.content?.length || 0}, hasData=${!!msg.data}`);
                        this.renderSavedMessage(msg);
                    });
                } else {
                    // Empty conversation - show welcome
                    console.log('No messages in conversation, showing welcome');
                    this.addWelcomeMessage();
                }

                // Update active conversation in sidebar
                this.updateActiveConversation(conversationId);
                console.log('Conversation loaded successfully');

                return true;
            } else {
                console.error('Failed to load conversation, status:', response.status);
            }
        } catch (error) {
            console.error('Error loading conversation:', error);
        }
        return false;
    }

    async deleteConversation(conversationId) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}`, { method: 'DELETE' });
            if (response.ok) {
                // Remove from conversations list
                this.conversations = this.conversations.filter(conv => conv.id !== conversationId);
                this.renderConversationList();
                
                // If this was the current conversation, start a new one
                if (this.conversationId === conversationId) {
                    await this.startFreshConversation();
                }
            }
        } catch (error) {
            console.error('Error deleting conversation:', error);
        }
    }

    async startFreshConversation() {
        // Don't create backend conversation yet - just reset UI state
        // Conversation will be created when first message is sent
        this.conversationId = null;
        this.messages = [];

        // Clear chat and add welcome message
        this.chatMessages.innerHTML = '';
        this.addWelcomeMessage();

        // Clear active state in sidebar
        const items = this.conversationList?.querySelectorAll('.conversation-item');
        items?.forEach(item => item.classList.remove('active'));
    }

    renderConversationList() {
        if (!this.conversationList) return;
        
        const sidebar = document.querySelector('.conversation-sidebar');
        
        // Always show the sidebar
        if (sidebar) sidebar.style.display = 'block';
        
        this.conversationList.innerHTML = '';
        
        if (this.conversations.length === 0) {
            // Show empty state message
            const emptyMsg = document.createElement('div');
            emptyMsg.className = 'conversation-item empty-state';
            emptyMsg.textContent = 'No conversations yet';
            this.conversationList.appendChild(emptyMsg);
            return;
        }

        this.conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = `conversation-item${this.conversationId === conv.id ? ' active' : ''}`;
            item.setAttribute('data-conversation-id', conv.id);
            
            const timestamp = new Date(conv.timestamp).toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
            });
            
            item.innerHTML = `
                <div class="conversation-timestamp">${timestamp}</div>
                <div class="conversation-preview">${conv.firstQuery}</div>
                <div class="conversation-meta">
                    <span>${conv.messageCount} messages</span>
                    <button class="conversation-delete" aria-label="Delete conversation" title="Delete conversation">🗑️</button>
                </div>
            `;
            
            // Click to load conversation
            item.addEventListener('click', (e) => {
                if (!e.target.classList.contains('conversation-delete')) {
                    this.loadConversation(conv.id);
                }
            });
            
            // Delete button
            const deleteBtn = item.querySelector('.conversation-delete');
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm('Are you sure you want to delete this conversation?')) {
                    this.deleteConversation(conv.id);
                }
            });
            
            this.conversationList.appendChild(item);
        });
    }

    updateActiveConversation(conversationId) {
        // Update active class in sidebar
        const items = this.conversationList.querySelectorAll('.conversation-item');
        items.forEach(item => {
            if (item.getAttribute('data-conversation-id') === conversationId) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }

    saveMessage(message) {
        // Save to local messages array (no localStorage anymore)
        this.messages.push(message);
        
        // Auto-save to backend (async, don't wait)
        if (this.conversationId) {
            this.saveMessageToBackend(message);
        }
    }

    async saveMessageToBackend(message) {
        // This is already handled in the query endpoints
        // Messages are saved when queries are made
    }

    renderSavedMessage(msg) {
        console.log('renderSavedMessage called with:', msg.type, msg.content?.substring(0, 50));
        if (msg.type === 'user') {
            console.log('  Rendering as user message');
            this.addMessage(msg.content, 'user', false, msg.timestamp);
        } else if (msg.type === 'assistant') {
            console.log('  Rendering as assistant message');
            // Ensure we have a proper data object with answer field
            const data = msg.data || {};
            console.log('    Initial data keys:', Object.keys(data));
            if (!data.answer && msg.content) {
                console.log('    Setting answer from content');
                data.answer = msg.content;
            }
            data.sources = data.sources || [];
            console.log('    Final data keys:', Object.keys(data));
            console.log('    data.answer length:', data.answer?.length || 0);
            this.addAssistantMessage(data, false, msg.timestamp);
        } else {
            console.log('  Unknown message type:', msg.type);
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
    // Glucose Unit Settings
    // ============================================

    loadGlucoseUnit() {
        // Load glucose unit from localStorage, with fallback to API
        const saved = localStorage.getItem('diabuddy_glucose_unit');
        if (saved) {
            this.setGlucoseUnitUI(saved);
        } else {
            // Try to load from server
            this.loadGlucoseUnitFromServer();
        }
    }

    async loadGlucoseUnitFromServer() {
        try {
            const response = await fetch('/api/settings/glucose-unit');
            if (response.ok) {
                const data = await response.json();
                const unit = data.glucose_unit || 'mmol/L';
                localStorage.setItem('diabuddy_glucose_unit', unit);
                this.setGlucoseUnitUI(unit);
            }
        } catch (error) {
            console.warn('Failed to load glucose unit from server:', error);
            // Default to mmol/L
            this.setGlucoseUnitUI('mmol/L');
        }
    }

    setGlucoseUnitUI(unit) {
        if (unit === 'mmol/L') {
            document.getElementById('glucoseUnitMmol').checked = true;
        } else {
            document.getElementById('glucoseUnitMgdl').checked = true;
        }
    }

    setupGlucoseUnitSettings() {
        const glucoseUnitRadios = document.querySelectorAll('input[name="glucoseUnit"]');
        
        glucoseUnitRadios.forEach(radio => {
            radio.addEventListener('change', async (e) => {
                const unit = e.target.value;
                localStorage.setItem('diabuddy_glucose_unit', unit);
                
                try {
                    const response = await fetch('/api/settings/glucose-unit', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ glucose_unit: unit })
                    });
                    
                    if (!response.ok) {
                        console.error('Failed to save glucose unit:', response.statusText);
                        alert('Failed to save glucose unit preference');
                    }
                } catch (error) {
                    console.error('Error saving glucose unit:', error);
                    alert('Error saving glucose unit preference');
                }
            });
        });
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

        // New chat button (header)
        if (this.newChatBtn) {
            this.newChatBtn.addEventListener('click', () => {
                this.startFreshConversation();
            });
        }

        // New conversation button (sidebar)
        if (this.newConversationBtn) {
            this.newConversationBtn.addEventListener('click', () => {
                this.startFreshConversation();
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

        // Settings modal
        if (this.settingsBtn) {
            this.settingsBtn.addEventListener('click', () => this.openSettings());
        }

        const settingsClose = this.settingsModal?.querySelector('.modal-close');
        if (settingsClose) {
            settingsClose.addEventListener('click', () => this.closeSettings());
        }

        this.settingsModal?.addEventListener('click', (e) => {
            if (e.target === this.settingsModal) this.closeSettings();
        });

        // PDF upload handlers
        if (this.pdfUploadArea) {
            this.pdfUploadArea.addEventListener('click', () => this.pdfFileInput?.click());
            this.pdfUploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                this.pdfUploadArea.classList.add('dragover');
            });
            this.pdfUploadArea.addEventListener('dragleave', () => {
                this.pdfUploadArea.classList.remove('dragover');
            });
            this.pdfUploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                this.pdfUploadArea.classList.remove('dragover');
                if (e.dataTransfer.files.length > 0) {
                    this.uploadPDF(e.dataTransfer.files[0]);
                }
            });
        }

        if (this.pdfFileInput) {
            this.pdfFileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.uploadPDF(e.target.files[0]);
                }
            });
        }
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

    isGlookoDataQuery(query) {
        const q = query.toLowerCase();
        const keywords = [
            'my glucose', 'blood sugar', 'time in range', 'tir', 'tbr', 'tar',
            'glooko', 'cgm', 'readings', 'lows', 'low blood sugar', 'hypo',
            'hypoglycemia', 'highs', 'high blood sugar', 'hyper',
            'hyperglycemia', 'dawn', 'postmeal', 'post-meal', 'post meal',
            'spike', 'pattern', 'nocturnal', 'overnight'
        ];
        return keywords.some(keyword => q.includes(keyword));
    }

    async sendQuery() {
        console.log('sendQuery called');
        const query = this.queryInput.value.trim();
        console.log('Query:', query);

        // Validation
        if (!query) {
            console.log('Query is empty, showing error');
            this.showInputError('Please enter a question');
            return;
        }
        if (query.length < 3) {
            console.log('Query too short, showing error');
            this.showInputError('Please ask a complete question');
            return;
        }
        if (query.length > 2000) {
            console.log('Query too long, showing error');
            this.showInputError('Question is too long (max 2000 characters)');
            return;
        }

        console.log('Query validation passed, proceeding...');

        // Track if this is the first message in a new conversation
        const isNewConversation = !this.conversationId;

        // If no conversation exists, create one
        if (!this.conversationId) {
            console.log('No conversation exists, creating new one');
            this.conversationId = await this.createNewConversation();
            if (!this.conversationId) {
                console.error('Failed to create conversation');
                this.showInputError('Failed to start conversation. Please try again.');
                return;
            }
            // Clear any welcome message and prepare for chat
            this.chatMessages.innerHTML = '';
        }

        // Clear input and disable button
        this.queryInput.value = '';
        this.sendBtn.disabled = true;

        // Add user message
        console.log('Adding user message');
        this.addMessage(query, 'user');
        this.saveMessage({ 
            type: 'user', 
            content: query, 
            timestamp: new Date().toISOString() 
        });

        // Add assistant message placeholder with "Thinking..."
        console.log('Adding thinking message');
        const thinkingMessageDiv = this.addThinkingMessage();
        
        try {
            // All queries now use streaming for consistent progressive rendering
            // This ensures both Groq and Glooko data queries have smooth, character-by-character display
            console.log('Starting streaming query for all query types');
            const data = await this.sendStreamingQuery(query, thinkingMessageDiv);
            console.log('Streaming completed with data:', data);

            // Save the complete assistant message
            this.saveMessage({
                type: 'assistant',
                data: data,
                timestamp: new Date().toISOString()
            });

            // Refresh sidebar if this was a new conversation
            if (isNewConversation) {
                await this.loadConversationHistory();
                this.updateActiveConversation(this.conversationId);
            }

        } catch (error) {
            console.error('Error in sendQuery:', error);
            this.addMessage(`Error: ${error.message}`, 'system');
        } finally {
            this.sendBtn.disabled = false;
            this.queryInput.focus();
        }
    }

    async sendStreamingQuery(query, messageDiv) {
        return new Promise((resolve, reject) => {
            let fullResponse = '';
            let displayedResponse = '';
            let isFirstChunk = true;
            let autoScrollEnabled = true;
            let isStreamComplete = false;
            const startTime = Date.now();
            
            // Progressive rendering: display accumulated chunks smoothly
            const renderInterval = setInterval(() => {
                if (displayedResponse.length < fullResponse.length) {
                    // Add next chunk of characters (simulate typewriter effect)
                    const chunkSize = Math.min(5, fullResponse.length - displayedResponse.length);
                    displayedResponse = fullResponse.substring(0, displayedResponse.length + chunkSize);
                    
                    const contentDiv = messageDiv.querySelector('.answer');
                    if (contentDiv) {
                        // Render markdown in streaming content
                        const formatted = this.renderMarkdown(fullResponse);
                        contentDiv.innerHTML = formatted;
                        displayedResponse = fullResponse;
                        
                        if (autoScrollEnabled) {
                            this.scrollToBottom();
                        }
                    }
                } else if (isStreamComplete) {
                    // Stream is done and everything is displayed
                    clearInterval(renderInterval);
                }
            }, 30); // Update every 30ms for smooth animation

            console.log('Creating EventSource for query:', query);
            
            // Create EventSource for streaming (include conversation_id if available)
            let eventSourceUrl = `${window.location.origin}/api/query/stream?query=${encodeURIComponent(query)}`;
            if (this.conversationId) {
                eventSourceUrl += `&conversation_id=${encodeURIComponent(this.conversationId)}`;
            }
            console.log('EventSource URL:', eventSourceUrl);
            const eventSource = new EventSource(eventSourceUrl);

            // Handle connection open
            eventSource.onopen = (event) => {
                console.log('EventSource connection opened:', event);
            };

            // Handle incoming chunks
            eventSource.onmessage = (event) => {
                const elapsed = (Date.now() - startTime) / 1000;
                const chunk = event.data;
                console.log(`[FRONTEND] Chunk received at ${elapsed.toFixed(3)}s: ${chunk.substring(0, 50)}`);

                // Accumulate chunks (rendering happens in interval above)
                fullResponse += chunk;

                if (isFirstChunk) {
                    console.log('First chunk received, replacing content with proper structure');
                    // Clear thinking animation
                    if (messageDiv._thinkingAnimation) {
                        clearInterval(messageDiv._thinkingAnimation);
                        delete messageDiv._thinkingAnimation;
                    }
                    // Create message structure
                    messageDiv.innerHTML = `
                        <div class="message-header">
                            <span class="message-role">Diabetes Buddy</span>
                            <span class="message-timestamp">${new Date().toLocaleTimeString()}</span>
                        </div>
                        <div class="answer"></div>
                    `;
                    isFirstChunk = false;
                }
            };

            // Handle errors
            eventSource.onerror = (error) => {
                console.error('EventSource error:', error);
                console.error('EventSource readyState:', eventSource.readyState);
                clearInterval(renderInterval);
                // Clear thinking animation
                if (messageDiv._thinkingAnimation) {
                    clearInterval(messageDiv._thinkingAnimation);
                    delete messageDiv._thinkingAnimation;
                }
                eventSource.close();
                
                // If we got at least some response, consider it partial success
                if (fullResponse) {
                    console.log('Stream interrupted but got partial response, resolving with what we have');
                    isStreamComplete = true;
                    // Wait for render to finish
                    setTimeout(() => {
                        resolve({
                            query: query,
                            classification: 'unified',
                            confidence: 1.0,
                            severity: 'info',
                            answer: fullResponse,
                            sources: [],
                            disclaimer: 'Always consult your healthcare provider.'
                        });
                    }, 100);
                } else {
                    reject(new Error('Failed to get response from server'));
                }
            };

            // Handle stream end - this is the proper completion event
            eventSource.addEventListener('end', () => {
                console.log('Received end event, stream completed');
                // Clear thinking animation
                if (messageDiv._thinkingAnimation) {
                    clearInterval(messageDiv._thinkingAnimation);
                    delete messageDiv._thinkingAnimation;
                }
                eventSource.close();
                isStreamComplete = true;
                
                // Wait for progressive rendering to finish before resolving
                const waitForRender = setInterval(() => {
                    if (displayedResponse.length >= fullResponse.length) {
                        clearInterval(waitForRender);
                        clearInterval(renderInterval);
                        console.log(`Stream complete. Full response length: ${fullResponse.length}, displayed: ${displayedResponse.length}`);
                        resolve({
                            query: query,
                            classification: 'unified',
                            confidence: 1.0,
                            severity: 'info',
                            answer: fullResponse,
                            sources: [],
                            disclaimer: 'Always consult your healthcare provider.'
                        });
                    }
                }, 50);
                
                // Timeout after 5 seconds to prevent infinite wait
                setTimeout(() => {
                    clearInterval(waitForRender);
                    clearInterval(renderInterval);
                    console.log('Render timeout - resolving with current response');
                    resolve({
                        query: query,
                        classification: 'unified',
                        confidence: 1.0,
                        severity: 'info',
                        answer: fullResponse,
                        sources: [],
                        disclaimer: 'Always consult your healthcare provider.'
                    });
                }, 5000);
            });

            // Handle user scroll to disable auto-scroll
            const handleScroll = () => {
                const container = this.chatMessages;
                const isAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 100;
                autoScrollEnabled = isAtBottom;
            };

            this.chatMessages.addEventListener('scroll', handleScroll);

            // Clean up event listener when stream ends
            eventSource.addEventListener('end', () => {
                this.chatMessages.removeEventListener('scroll', handleScroll);
            });
        });
    }

    async sendRegularQuery(query) {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                conversation_id: this.conversationId
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Server error: ${response.status} - ${errorText}`);
        }

        return await response.json();
    }

    addThinkingMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant thinking';
        messageDiv.id = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-role">Diabetes Buddy</span>
                <span class="message-timestamp">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="answer">
                <div class="thinking-message">
                    <span class="thinking-text">Thinking</span>
                    <div class="typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            </div>
        `;

        // Animate the thinking text
        const thinkingText = messageDiv.querySelector('.thinking-text');
        let dots = 0;
        const animateThinking = () => {
            dots = (dots + 1) % 4;
            thinkingText.textContent = 'Thinking' + '.'.repeat(dots);
        };
        const animationInterval = setInterval(animateThinking, 500);
        
        // Store the interval on the message div so we can clear it later
        messageDiv._thinkingAnimation = animationInterval;

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        return messageDiv;
    }

    updateStreamingMessage(messageDiv, content) {
        const contentDiv = messageDiv.querySelector('.message-content');
        if (contentDiv) {
            // Render markdown for the content
            contentDiv.innerHTML = this.renderMarkdown(content);
        }
    }

    renderMarkdown(text) {
        let html = text;
        
        // Try to parse with marked.js
        if (window.marked) {
            try {
                html = marked.parse(text);
                console.log('[renderMarkdown] ✓ Marked.js successfully parsed markdown');
            } catch (e) {
                console.error('[renderMarkdown] Marked.js parse error, using fallback:', e);
                html = this.fallbackMarkdownToHTML(text);
            }
        } else {
            console.warn('[renderMarkdown] Marked.js not available, using fallback');
            html = this.fallbackMarkdownToHTML(text);
        }
        
        // Sanitize HTML to prevent XSS
        if (window.DOMPurify) {
            html = DOMPurify.sanitize(html, {
                ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                               'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'a', 'sup', 'sub', 'div', 'span'],
                ALLOWED_ATTR: ['class', 'id', 'title', 'data-ref', 'href'],
                ALLOW_DATA_ATTR: true
            });
            console.log('[renderMarkdown] ✓ HTML sanitized with DOMPurify');
        } else {
            console.warn('[renderMarkdown] DOMPurify not available - HTML not sanitized (potential XSS risk)');
        }
        
        return html;
    }

    scrollToBottom() {
        // Smooth scroll to bottom
        this.chatMessages.scrollTo({
            top: this.chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    }

    async sendQueryWithRetry(query, maxRetries = 2) {
        let lastError;

        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                const response = await fetch('/api/query/unified', {
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
                <p>Welcome to Diabetes Buddy! Ask me anything about diabetes management or your Glooko data.</p>
                <div class="suggested-questions">
                    <p class="suggestion-label">Try asking:</p>
                    <div class="suggestion-buttons">
                        <button class="suggestion-btn" data-query="What was my average glucose last week?">
                            📊 What was my average glucose last week?
                        </button>
                        <button class="suggestion-btn" data-query="What's my time in range for the past 2 weeks?">
                            📊 What's my time in range?
                        </button>
                        <button class="suggestion-btn" data-query="When do I typically experience lows?">
                            📊 When do I typically experience lows?
                        </button>
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

    addMessage(text, type = 'assistant', animate = true, timestamp = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        if (!animate) messageDiv.style.animation = 'none';

        // Add header for user messages
        if (type === 'user') {
            const header = document.createElement('div');
            header.className = 'message-header';
            const timeStr = timestamp
                ? new Date(timestamp).toLocaleTimeString()
                : new Date().toLocaleTimeString();
            header.innerHTML = `
                <span class="message-role">You</span>
                <span class="message-timestamp">${timeStr}</span>
            `;
            messageDiv.appendChild(header);
        }

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

    addAssistantMessage(data, animate = true, timestamp = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.id = `msg-${Date.now()}`;  // Unique ID for feedback
        if (!animate) messageDiv.style.animation = 'none';

        // Add message header with timestamp
        const header = document.createElement('div');
        header.className = 'message-header';
        const timeStr = timestamp
            ? new Date(timestamp).toLocaleTimeString()
            : new Date().toLocaleTimeString();
        header.innerHTML = `
            <span class="message-role">Diabetes Buddy</span>
            <span class="message-timestamp">${timeStr}</span>
        `;
        messageDiv.appendChild(header);

        // Ensure data.answer exists
        const answer = data.answer || '';
        const sources = data.sources || [];
        const { cleaned, refList } = this.extractAndFormatReferences(answer, sources);
        const answerContainer = this.formatText(cleaned, refList);

        // Add LLM provider badge (new)
        if (data.llm_info) {
            const llmBadge = this.createLLMProviderBadge(data.llm_info);
            answerContainer.insertBefore(llmBadge, answerContainer.firstChild);
        }

        // Add knowledge source badge (replaces old classification badge)
        if (data.primary_source_type || data.knowledge_breakdown) {
            const badge = this.createSourceBadge(data);
            answerContainer.insertBefore(badge, answerContainer.firstChild);
        } else if (data.classification === 'glooko_data') {
            // Fallback for old API responses
            const badge = document.createElement('div');
            badge.className = 'classification-badge glooko-data';
            badge.innerHTML = '📊 Your Glooko Data';
            answerContainer.insertBefore(badge, answerContainer.firstChild);
        }

        messageDiv.appendChild(answerContainer);

        // Add categorized sources section if sources available
        if (sources && sources.length > 0) {
            const sourcesSection = this.createCategorizedSources(
                sources,
                data.knowledge_breakdown
            );
            messageDiv.appendChild(sourcesSection);
        }

        // Add feedback buttons
        const feedbackSection = this.createFeedbackSection(messageDiv.id, data);
        messageDiv.appendChild(feedbackSection);

        // Update knowledge base display with actual breakdown from response
        if (data.knowledge_breakdown) {
            this.updateKnowledgeBreakdownDisplay(data.knowledge_breakdown);
        }

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    /**
     * Create LLM provider badge showing which model was used.
     * @param {Object} llmInfo - LLM info object with provider, model, cost, routing_reason
     * @returns {HTMLElement} Badge element
     */
    createLLMProviderBadge(llmInfo) {
        const badge = document.createElement('div');
        badge.className = 'llm-provider-badge';
        
        const provider = llmInfo.provider || 'unknown';
        const model = llmInfo.model || 'unknown';
        const cost = llmInfo.estimated_cost || 0;
        const routingReason = llmInfo.routing_reason || '';
        const fallbackUsed = llmInfo.fallback_used || false;
        
        let providerIcon, providerLabel;
        
        switch (provider.toLowerCase()) {
            case 'groq':
                providerIcon = '⚡';
                providerLabel = `Groq ${model.split('/').pop() || 'OSS'}`;
                break;
            case 'gemini':
                providerIcon = '✨';
                providerLabel = `Gemini ${model.split('-').pop() || 'Flash'}`;
                break;
            case 'openai':
                providerIcon = '🔷';
                providerLabel = `GPT ${model.split('-').pop() || '4'}`;
                break;
            case 'anthropic':
                providerIcon = '🧠';
                providerLabel = `Claude ${model.split('-')[1] || 'Sonnet'}`;
                break;
            default:
                providerIcon = '🤖';
                providerLabel = provider;
        }
        
        // Build tooltip with details
        let tooltip = `LLM Provider: ${providerLabel}`;
        if (routingReason) {
            tooltip += `\nRouting: ${routingReason}`;
        }
        if (cost > 0) {
            tooltip += `\nCost: $${cost.toFixed(6)}`;
        }
        if (fallbackUsed) {
            tooltip += '\n⚠️ Fallback used (primary provider failed)';
        }
        
        badge.setAttribute('data-tooltip', tooltip);
        badge.className = fallbackUsed ? 'llm-provider-badge fallback-used' : 'llm-provider-badge';
        badge.innerHTML = `${providerIcon} ${providerLabel}`;
        
        return badge;
    }

    /**
     * Create knowledge source badge based on response metadata.
     * @param {Object} data - Response data with knowledge_breakdown
     * @returns {HTMLElement} Badge element
     */
    createSourceBadge(data) {
        const badge = document.createElement('div');
        badge.className = 'source-badge';

        const primaryType = data.primary_source_type || 'unknown';
        let icon, label, tooltip, badgeClass;

        switch (primaryType) {
            case 'rag':
                icon = '🟢';
                label = 'Evidence-Based';
                badgeClass = 'evidence-based';
                tooltip = 'Response based on authoritative device documentation and clinical guidelines';
                break;
            case 'hybrid':
                icon = '🟡';
                label = 'Mixed Sources';
                badgeClass = 'mixed-sources';
                tooltip = 'Response combines device documentation with general medical knowledge';
                break;
            case 'parametric':
                icon = '🔵';
                label = 'General Guidance';
                badgeClass = 'general-guidance';
                tooltip = 'Response based primarily on general diabetes knowledge - verify device-specific info with your manual';
                break;
            case 'glooko':
                icon = '📊';
                label = 'Personal Data';
                badgeClass = 'personal-data';
                tooltip = 'Response includes analysis of your uploaded Glooko data';
                break;
            default:
                icon = '💬';
                label = 'Response';
                badgeClass = '';
                tooltip = '';
        }

        badge.classList.add(...badgeClass.split(' ').filter(c => c));
        badge.setAttribute('data-tooltip', tooltip);
        badge.setAttribute('role', 'status');
        badge.setAttribute('aria-label', label);

        badge.innerHTML = `
            <span class="badge-icon">${icon}</span>
            <span class="badge-label">${label}</span>
        `;

        return badge;
    }

    /**
     * Create categorized sources section.
     * @param {Array} sources - Source objects from API
     * @param {Object} breakdown - Knowledge breakdown object
     * @returns {HTMLElement} Sources section element
     */
    createCategorizedSources(sources, breakdown) {
        const container = document.createElement('div');
        container.className = 'sources-categorized';

        // Categorize sources
        const categories = {
            device: { icon: '📘', label: 'Device Documentation', items: [] },
            clinical: { icon: '🏥', label: 'Clinical Guidelines', items: [] },
            personal: { icon: '📊', label: 'Your Data', items: [] },
            general: { icon: '💭', label: 'General Knowledge', items: [] }
        };

        if (sources && sources.length > 0) {
            sources.forEach(source => {
                const sourceName = (source.source || '').toLowerCase();
                const item = {
                    name: source.source,
                    excerpt: source.excerpt
                };

                if (sourceName.includes('glooko') || sourceName.includes('your')) {
                    categories.personal.items.push(item);
                } else if (sourceName.includes('ada') || sourceName.includes('guidelines') || sourceName.includes('standards')) {
                    categories.clinical.items.push(item);
                } else if (sourceName.includes('general') || sourceName.includes('parametric')) {
                    categories.general.items.push(item);
                } else {
                    categories.device.items.push(item);
                }
            });
        }

        // Add parametric source if breakdown indicates it was used
        if (breakdown && breakdown.parametric_ratio > 0 && categories.general.items.length === 0) {
            categories.general.items.push({
                name: 'General Medical Knowledge',
                excerpt: 'Physiological and biochemical reasoning'
            });
        }

        // Render header
        const header = document.createElement('div');
        header.className = 'ref-title';
        header.textContent = '📚 Sources';
        container.appendChild(header);

        // Render non-empty categories
        Object.entries(categories).forEach(([key, cat]) => {
            if (cat.items.length === 0) return;

            const categoryDiv = document.createElement('div');
            categoryDiv.className = 'source-category';

            categoryDiv.innerHTML = `
                <div class="source-category-header">
                    <span class="source-category-icon">${cat.icon}</span>
                    <span>${cat.label}</span>
                </div>
                <div class="source-category-items">
                    ${cat.items.map(item => `
                        <div class="source-item">
                            <span>${item.name}</span>
                        </div>
                    `).join('')}
                </div>
            `;

            container.appendChild(categoryDiv);
        });

        return container;
    }

    /**
     * Create feedback buttons for response quality tracking.
     * @param {string} messageId - Unique message identifier
     * @param {Object} data - Response data for logging
     * @returns {HTMLElement} Feedback section element
     */
    createFeedbackSection(messageId, data) {
        const section = document.createElement('div');
        section.className = 'feedback-section';
        section.setAttribute('role', 'group');
        section.setAttribute('aria-label', 'Response feedback');

        section.innerHTML = `
            <span class="feedback-label">Was this helpful?</span>
            <button class="feedback-btn helpful" data-feedback="helpful" aria-label="Mark as helpful">
                👍 Helpful
            </button>
            <button class="feedback-btn not-helpful" data-feedback="not-helpful" aria-label="Mark as not helpful">
                👎 Not Helpful
            </button>
        `;

        // Add click handlers
        const self = this;
        section.querySelectorAll('.feedback-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                // Remove selected from siblings
                section.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');

                // Log feedback
                self.logResponseFeedback(messageId, btn.dataset.feedback, data);
            });
        });

        return section;
    }

    /**
     * Log user feedback on response quality.
     * @param {string} messageId - Message identifier
     * @param {string} feedback - 'helpful' or 'not-helpful'
     * @param {Object} data - Response metadata
     */
    async logResponseFeedback(messageId, feedback, data) {
        try {
            await fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message_id: messageId,
                    feedback: feedback,
                    primary_source_type: data.primary_source_type,
                    knowledge_breakdown: data.knowledge_breakdown,
                    timestamp: new Date().toISOString()
                })
            });
        } catch (error) {
            console.warn('Failed to log feedback:', error);
        }
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

    /**
     * Fallback markdown-to-HTML converter when marked.js is unavailable.
     * Handles basic markdown patterns: bold, italics, headers, lists.
     */
    fallbackMarkdownToHTML(text) {
        let html = text;
        
        // Headers (# - ######)
        html = html.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.*?)$/gm, '<h1>$1</h1>');
        html = html.replace(/^#### (.*?)$/gm, '<h4>$1</h4>');
        html = html.replace(/^##### (.*?)$/gm, '<h5>$1</h5>');
        html = html.replace(/^###### (.*?)$/gm, '<h6>$1</h6>');
        
        // Bold: **text** and __text__
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');
        
        // Italics: *text* and _text_
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        html = html.replace(/_(.*?)_/g, '<em>$1</em>');
        
        // Lists: numbered and unnumbered
        const lines = html.split('\n');
        const processedLines = [];
        let inList = false;
        let listType = null;
        
        for (let line of lines) {
            // Ordered list (1., 2., etc.)
            if (/^\d+\.\s/.test(line)) {
                if (!inList || listType !== 'ol') {
                    if (inList) processedLines.push(`</${listType}>`);
                    processedLines.push('<ol>');
                    inList = true;
                    listType = 'ol';
                }
                line = line.replace(/^\d+\.\s(.*)$/, '<li>$1</li>');
                processedLines.push(line);
            }
            // Unordered list (-, *, +)
            else if (/^[-*+]\s/.test(line)) {
                if (!inList || listType !== 'ul') {
                    if (inList) processedLines.push(`</${listType}>`);
                    processedLines.push('<ul>');
                    inList = true;
                    listType = 'ul';
                }
                line = line.replace(/^[-*+]\s(.*)$/, '<li>$1</li>');
                processedLines.push(line);
            }
            // Empty line or non-list line
            else {
                if (inList && line.trim()) {
                    processedLines.push(`</${listType}>`);
                    inList = false;
                    listType = null;
                }
                if (line.trim()) {
                    processedLines.push(`<p>${line}</p>`);
                }
            }
        }
        
        if (inList) {
            processedLines.push(`</${listType}>`);
        }
        
        html = processedLines.join('\n');
        
        // Line breaks: double newlines become paragraphs (already handled above)
        // Single newlines become <br>
        html = html.replace(/\n(?!<)/g, '<br>\n');
        
        return html;
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
        
        // Parse markdown with marked.js
        if (window.marked) {
            try {
                html = marked.parse(withRefs);
                console.log('[formatText] ✓ Marked.js successfully parsed markdown');
            } catch (e) {
                console.error('[formatText] Marked.js parse error, using fallback:', e);
                html = this.fallbackMarkdownToHTML(withRefs);
            }
        } else {
            console.warn('[formatText] Marked.js not available, using fallback HTML conversion');
            html = this.fallbackMarkdownToHTML(withRefs);
        }
        
        // Sanitize HTML to prevent XSS
        if (window.DOMPurify) {
            html = DOMPurify.sanitize(html, {
                ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                               'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'a', 'sup', 'sub', 'div', 'span'],
                ALLOWED_ATTR: ['class', 'id', 'title', 'data-ref', 'href'],
                ALLOW_DATA_ATTR: true
            });
            console.log('[formatText] ✓ HTML sanitized with DOMPurify');
        } else {
            console.warn('[formatText] DOMPurify not available - HTML not sanitized (potential XSS risk)');
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
        const excerpt = source.full_excerpt || source.excerpt || 'No excerpt available';

        this.modalBody.innerHTML = `
            <h2 id="modalTitle">Source Details</h2>
            <p><strong>Source:</strong> ${source.citation || source.source}</p>
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
            const response = await fetch('/api/sources/list');
            const data = await response.json();

            this.sourcesList.innerHTML = '';

            // Public Knowledge Section
            const publicSection = document.createElement('div');
            publicSection.className = 'sources-section';
            publicSection.innerHTML = '<h4>Public Knowledge</h4>';

            if (data.public_sources && data.public_sources.length > 0) {
                data.public_sources.forEach(source => {
                    const div = document.createElement('div');
                    div.className = 'source-item public';
                    div.innerHTML = `
                        <div class="source-info">
                            <strong>${source.name}</strong>
                            <small>${source.chunk_count} chunks</small>
                        </div>
                    `;
                    publicSection.appendChild(div);
                });
            } else {
                publicSection.innerHTML += '<div class="source-item muted">No public sources available</div>';
            }

            this.sourcesList.appendChild(publicSection);

            // User Guides Section
            const userSection = document.createElement('div');
            userSection.className = 'sources-section';
            userSection.innerHTML = '<h4>Your Product Guides</h4>';

            if (data.user_sources && data.user_sources.length > 0) {
                data.user_sources.forEach(source => {
                    const div = document.createElement('div');
                    div.className = 'source-item user';
                    div.innerHTML = `
                        <div class="source-info">
                            <strong>${source.display_name}</strong>
                            <small>${source.indexed ? source.chunk_count + ' chunks' : 'Indexing...'}</small>
                        </div>
                    `;
                    userSection.appendChild(div);
                });
            } else {
                userSection.innerHTML += `
                    <div class="source-item muted">
                        No guides uploaded. <a href="#" onclick="diabuddyChat.openSettings(); return false;">Add one</a>
                    </div>
                `;
            }

            this.sourcesList.appendChild(userSection);

        } catch (error) {
            console.error('Failed to load sources:', error);
            this.sourcesList.innerHTML = '<div class="source-item error">Failed to load sources</div>';
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
            this.uploadArea.addEventListener('click', () => {
                this.fileInput?.click();
            });
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
                if (e.target.files.length > 0) {
                    this.uploadFile(e.target.files[0]);
                }
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
        console.log('uploadFile called with:', file);
        
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

        console.log('File validation passed, starting upload...');
        
        // Show progress
        this.uploadProgress?.removeAttribute('hidden');
        this.uploadArea?.setAttribute('hidden', '');
        const progressFill = document.getElementById('progressFill');
        const uploadStatus = document.getElementById('uploadStatus');

        try {
            const formData = new FormData();
            formData.append('file', file);
            
            console.log('Uploading to /api/upload-glooko...');

            // Upload with progress simulation (fetch doesn't support progress)
            if (uploadStatus) uploadStatus.textContent = 'Uploading...';
            if (progressFill) progressFill.style.width = '30%';

            const response = await fetch('/api/upload-glooko', {
                method: 'POST',
                body: formData
            });

            console.log('Upload response status:', response.status);
            
            if (progressFill) progressFill.style.width = '60%';

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const result = await response.json();
            console.log('Upload result:', result);
            
            if (progressFill) progressFill.style.width = '80%';

            // Run analysis
            if (uploadStatus) uploadStatus.textContent = 'Analyzing data...';
            console.log('Running analysis on:', result.filename);
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
        const glucoseUnit = metrics.glucose_unit || 'mg/dL';

        // Update metric values with configured glucose unit
        const avgGlucoseDisplay = metrics.average_glucose 
            ? `${metrics.average_glucose} ${glucoseUnit}` 
            : '--';
        const stdDevDisplay = metrics.std_deviation 
            ? `${metrics.std_deviation} ${glucoseUnit}` 
            : '--';
        
        this.updateElement('avgGlucose', avgGlucoseDisplay);
        this.updateElement('stdDev', stdDevDisplay);
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
    
    // ============================================
    // Knowledge Base Status
    // ============================================
    
    async loadKnowledgeBaseStatus() {
        const kbStatus = document.getElementById('kbStatus');
        if (!kbStatus) return;
        
        try {
            const response = await fetch('/api/sources/list');
            const data = await response.json();
            
            const userSources = data.user_sources || [];
            const publicSources = data.public_sources || [];
            const allSources = [...userSources, ...publicSources];
            
            // Count by status
            const statusCounts = {
                current: allSources.filter(s => s.status === 'current').length,
                stale: allSources.filter(s => s.status === 'stale').length,
                outdated: allSources.filter(s => s.status === 'outdated').length,
                error: allSources.filter(s => s.status === 'error').length
            };
            
            // Build HTML
            let html = `
                <div class="kb-summary">
                    <div class="kb-summary-text">
                        <div class="kb-summary-count">${allSources.length}</div>
                        <div class="kb-summary-label">Knowledge Sources</div>
                    </div>
                </div>
            `;
            
            // Show source list (compact)
            allSources.slice(0, 5).forEach(source => {
                const statusClass = source.status || 'current';
                const statusLabel = statusClass.charAt(0).toUpperCase() + statusClass.slice(1);
                const displayName = this.getSourceDisplayName(source);

                html += `
                    <div class="kb-source-item">
                        <div class="kb-source-name" title="${displayName}">${displayName}</div>
                        <div class="kb-source-status">
                            <span class="kb-status-badge ${statusClass}">${statusLabel}</span>
                        </div>
                    </div>
                `;
            });
            
            if (allSources.length > 5) {
                html += `<div class="kb-last-check">+${allSources.length - 5} more sources</div>`;
            }
            
            // Actions - link to settings for managing sources
            html += `
                <div class="kb-actions">
                    <button class="kb-btn kb-btn-secondary" onclick="diabuddyChat.openSettings()">Manage Sources</button>
                </div>
            `;
            
            kbStatus.innerHTML = html;
            
        } catch (error) {
            console.error('Failed to load knowledge base status:', error);
            kbStatus.innerHTML = `
                <div class="kb-notification">
                    <div class="kb-notification-title">⚠️ Status Unavailable</div>
                    <div class="kb-notification-text">Could not load knowledge base status</div>
                </div>
            `;
        }
    }
    
    formatTimeAgo(date) {
        const seconds = Math.floor((new Date() - date) / 1000);

        if (seconds < 60) return 'just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
        if (seconds < 604800) return `${Math.floor(seconds / 86400)} days ago`;
        return date.toLocaleDateString();
    }

    openSettings() {
        this.settingsModal?.classList.add('active');
        this.loadSettingsSources();
        this.loadDeviceProfile();
    }

    closeSettings() {
        this.settingsModal?.classList.remove('active');
        this.loadSources(); // Refresh sidebar
    }

    async loadSettingsSources() {
        const userList = document.getElementById('userSourcesList');
        const publicList = document.getElementById('publicSourcesList');

        try {
            const response = await fetch('/api/sources/list');
            const data = await response.json();

            // Render user sources
            if (data.user_sources && data.user_sources.length > 0) {
                userList.innerHTML = data.user_sources.map(source => `
                    <div class="user-source-item">
                        <div class="user-source-info">
                            <div class="user-source-name">${source.display_name}</div>
                            <div class="user-source-meta">
                                ${source.indexed ? `${source.chunk_count} chunks indexed` : 'Indexing...'}
                                · Uploaded ${new Date(source.uploaded_at).toLocaleDateString()}
                            </div>
                        </div>
                        <button class="user-source-delete"
                                onclick="diabuddyChat.deleteUserSource('${source.filename}')">
                            Delete
                        </button>
                    </div>
                `).join('');
            } else {
                userList.innerHTML = '<div class="no-sources">No product guides uploaded yet</div>';
            }

            // Render public sources
            if (data.public_sources && data.public_sources.length > 0) {
                publicList.innerHTML = data.public_sources.map(source => `
                    <div class="public-source-item">
                        <span class="public-source-name">${source.name}</span>
                        <span class="public-source-status">${source.chunk_count} chunks</span>
                    </div>
                `).join('');
            } else {
                publicList.innerHTML = '<div class="no-sources">Loading...</div>';
            }

        } catch (error) {
            console.error('Failed to load settings sources:', error);
            userList.innerHTML = '<div class="error">Failed to load sources</div>';
        }
    }

    async uploadPDF(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('Please upload a PDF file');
            return;
        }

        if (file.size > 50 * 1024 * 1024) {
            alert('File too large. Maximum size is 50MB');
            return;
        }

        const progress = document.getElementById('pdfUploadProgress');
        const progressFill = document.getElementById('pdfProgressFill');
        const status = document.getElementById('pdfUploadStatus');
        const uploadArea = document.getElementById('pdfUploadArea');

        progress?.removeAttribute('hidden');
        uploadArea?.setAttribute('hidden', '');

        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('session_id', this.sessionId);

            status.textContent = 'Uploading...';
            progressFill.style.width = '30%';

            const response = await fetch('/api/sources/upload', {
                method: 'POST',
                body: formData
            });

            progressFill.style.width = '70%';

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const result = await response.json();

            progressFill.style.width = '100%';
            status.textContent = `Uploaded: ${result.display_name}`;

            await this.handleDevicePromptAfterUpload(result);

            // Refresh lists
            setTimeout(() => {
                progress?.setAttribute('hidden', '');
                uploadArea?.removeAttribute('hidden');
                progressFill.style.width = '0%';
                this.loadSettingsSources();
                this.loadSources();
            }, 1500);

        } catch (error) {
            console.error('Upload error:', error);
            status.textContent = `Error: ${error.message}`;
            setTimeout(() => {
                progress?.setAttribute('hidden', '');
                uploadArea?.removeAttribute('hidden');
            }, 3000);
        }
    }

    async handleDevicePromptAfterUpload(uploadResult) {
        const profileComplete = uploadResult?.device_profile_complete === true;

        if (profileComplete) {
            if (uploadResult.device_profile) {
                this.renderDeviceProfile(uploadResult.device_profile);
            }
            return;
        }

        let profile = null;
        try {
            profile = await this.getDeviceProfile();
        } catch (error) {
            console.warn('Failed to load device profile:', error);
        }

        if (profile?.is_complete) {
            this.renderDeviceProfile(profile);
            return;
        }

        let detectionResult = null;
        try {
            detectionResult = await this.detectDevicesFromPDF(uploadResult.filename);
        } catch (err) {
            console.warn('Device detection skipped:', err);
        }

        this.openSettings();

        if (!detectionResult || (!detectionResult.pump && !detectionResult.cgm)) {
            this.openDeviceEditor();
        }
    }

    async getDeviceProfile() {
        const response = await fetch(`/api/devices/profile?session_id=${encodeURIComponent(this.sessionId)}`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to load device profile');
        }
        return response.json();
    }

    async loadDeviceProfile() {
        try {
            const profile = await this.getDeviceProfile();
            if (profile?.exists) {
                this.renderDeviceProfile(profile);
            }
            // Always ensure form is hidden when loading profile
            const editForm = document.getElementById('deviceEditForm');
            if (editForm) editForm.setAttribute('hidden', '');
            const detectionResults = document.querySelector('.device-detection-results');
            if (detectionResults) detectionResults.removeAttribute('hidden');
        } catch (error) {
            console.warn('No device profile available:', error);
        }
    }

    renderDeviceProfile(profile) {
        if (!profile || (!profile.pump && !profile.cgm)) {
            return;
        }

        this.showDetectedDevices({
            pump: profile.pump || null,
            cgm: profile.cgm || null,
            pump_confidence: 1,
            cgm_confidence: 1
        });
    }

    openDeviceEditor(defaults = {}) {
        const editForm = document.getElementById('deviceEditForm');
        const pumpSelect = document.getElementById('pumpSelect');
        const cgmSelect = document.getElementById('cgmSelect');
        const detectionResults = document.querySelector('.device-detection-results');

        if (pumpSelect) pumpSelect.value = defaults.pump || '';
        if (cgmSelect) cgmSelect.value = defaults.cgm || '';

        editForm?.removeAttribute('hidden');
        detectionResults?.setAttribute('hidden', '');
        document.getElementById('deviceConfirmationArea')?.removeAttribute('hidden');
        document.getElementById('noDevicesMessage')?.setAttribute('hidden', '');
    }

    // ============================================
    // Device Confirmation
    // ============================================

    setupDeviceConfirmation() {
        // Get device confirmation elements
        const deviceConfirmArea = document.getElementById('deviceConfirmationArea');
        const confirmBtn = document.getElementById('confirmDevicesBtn');
        const editBtn = document.getElementById('editDevicesBtn');
        const settingsEditBtn = document.getElementById('editDevicesSettingsBtn');
        const saveBtn = document.getElementById('saveDevicesBtn');
        const cancelBtn = document.getElementById('cancelEditBtn');
        const editForm = document.getElementById('deviceEditForm');
        const pumpSelect = document.getElementById('pumpSelect');
        const cgmSelect = document.getElementById('cgmSelect');

        if (!confirmBtn || !editBtn || !saveBtn || !cancelBtn) {
            console.warn('Device confirmation buttons not found in DOM');
            return;
        }

        // Confirm devices button - call override API and close
        confirmBtn.addEventListener('click', async () => {
            const detectedDevices = this.getDetectedDevices();
            if (!detectedDevices.pump && !detectedDevices.cgm) {
                alert('No devices detected. Please edit or upload a device manual.');
                return;
            }

            try {
                const saved = await this.saveDeviceOverride(
                    detectedDevices.pump,
                    detectedDevices.cgm
                );
                this.renderDeviceProfile(saved);
                deviceConfirmArea?.removeAttribute('hidden');
                alert('Devices confirmed and saved!');
            } catch (error) {
                console.error('Error confirming devices:', error);
                alert(`Failed to confirm devices: ${error.message}`);
            }
        });

        // Edit devices button - show form
        editBtn.addEventListener('click', async () => {
            let defaults = this.getDetectedDevices();
            if (!defaults.pump && !defaults.cgm) {
                try {
                    const profile = await this.getDeviceProfile();
                    if (profile?.exists) {
                        defaults = { pump: profile.pump, cgm: profile.cgm };
                    }
                } catch (error) {
                    console.warn('Failed to load profile for edit:', error);
                }
            }
            this.openDeviceEditor(defaults);
        });

        if (settingsEditBtn) {
            settingsEditBtn.addEventListener('click', async () => {
                let defaults = {};
                try {
                    const profile = await this.getDeviceProfile();
                    if (profile?.exists) {
                        defaults = { pump: profile.pump, cgm: profile.cgm };
                    }
                } catch (error) {
                    console.warn('Failed to load profile for settings edit:', error);
                }
                this.openDeviceEditor(defaults);
            });
        }

        // Save devices button - call override API with form values
        saveBtn.addEventListener('click', async () => {
            const pump = pumpSelect?.value || '';
            const cgm = cgmSelect?.value || '';

            if (!pump && !cgm) {
                alert('Please select at least one device');
                return;
            }

            try {
                const saved = await this.saveDeviceOverride(pump, cgm);
                // Reset form and show saved devices
                editForm?.setAttribute('hidden', '');
                document.querySelector('.device-detection-results')?.removeAttribute('hidden');
                deviceConfirmArea?.removeAttribute('hidden');
                pumpSelect.value = '';
                cgmSelect.value = '';
                this.renderDeviceProfile(saved);
                alert('Devices saved successfully!');
            } catch (error) {
                console.error('Error saving devices:', error);
                alert(`Failed to save devices: ${error.message}`);
            }
        });

        // Cancel edit button - hide form
        cancelBtn.addEventListener('click', () => {
            editForm?.setAttribute('hidden', '');
            document.querySelector('.device-detection-results')?.removeAttribute('hidden');
            pumpSelect.value = '';
            cgmSelect.value = '';
        });
    }

    /**
     * Get currently selected devices from the detected devices grid
     */
    getDetectedDevices() {
        const detectedDevices = document.getElementById('detectedDevices');
        const cards = detectedDevices?.querySelectorAll('.device-card.selected') || [];
        
        let pump = '', cgm = '';
        cards.forEach(card => {
            const device = card.dataset.device;
            if (card.dataset.type === 'pump') pump = device;
            if (card.dataset.type === 'cgm') cgm = device;
        });

        return { pump, cgm };
    }

    /**
     * Save device override via API
     */
    async saveDeviceOverride(pump, cgm) {
        const response = await fetch('/api/devices/override', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: this.sessionId,
                pump: pump || null,
                cgm: cgm || null,
                override_source: 'user'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save device override');
        }

        return response.json();
    }

    /**
     * Show detected devices in confirmation area with confidence badges
     */
    showDetectedDevices(detectedDevices) {
        const deviceConfirmArea = document.getElementById('deviceConfirmationArea');
        const detectedDevicesGrid = document.getElementById('detectedDevices');
        const noDevicesMsg = document.getElementById('noDevicesMessage');

        if (!detectedDevices || (Object.keys(detectedDevices).length === 0)) {
            // No devices detected
            if (noDevicesMsg) noDevicesMsg.removeAttribute('hidden');
            if (deviceConfirmArea) deviceConfirmArea.setAttribute('hidden', '');
            return;
        }

        // Clear previous cards
        if (detectedDevicesGrid) {
            detectedDevicesGrid.innerHTML = '';

            // Add pump device card if detected
            if (detectedDevices.pump) {
                const pumpCard = this.createDeviceCard(
                    detectedDevices.pump,
                    'pump',
                    detectedDevices.pump_confidence || 0.8
                );
                detectedDevicesGrid.appendChild(pumpCard);
            }

            // Add CGM device card if detected
            if (detectedDevices.cgm) {
                const cgmCard = this.createDeviceCard(
                    detectedDevices.cgm,
                    'cgm',
                    detectedDevices.cgm_confidence || 0.8
                );
                detectedDevicesGrid.appendChild(cgmCard);
            }
        }

        // Show confirmation area, hide "no devices" message
        if (deviceConfirmArea) deviceConfirmArea.removeAttribute('hidden');
        if (noDevicesMsg) noDevicesMsg.setAttribute('hidden', '');

        // Reset edit form visibility
        const editForm = document.getElementById('deviceEditForm');
        if (editForm) editForm.setAttribute('hidden', '');
        const detectionResults = document.querySelector('.device-detection-results');
        if (detectionResults) detectionResults.removeAttribute('hidden');
    }

    /**
     * Create a device card element with confidence badge
     */
    createDeviceCard(device, type, confidence) {
        const card = document.createElement('div');
        card.className = 'device-card selected';
        card.dataset.device = device;
        card.dataset.type = type;

        const confidencePercent = Math.round(confidence * 100);
        const badgeLevel = confidence > 0.85 ? 'high' : confidence > 0.7 ? 'medium' : 'low';

        const typeLabel = type === 'pump' ? '💉 Pump' : '📊 CGM';
        const deviceLabel = this.formatDeviceLabel(device);

        card.innerHTML = `
            <div class="device-info">
                <span class="device-type">${typeLabel}</span>
                <span class="device-name">${deviceLabel}</span>
            </div>
            <span class="confidence-badge ${badgeLevel}">${confidencePercent}%</span>
        `;

        return card;
    }

    /**
     * Format device name for display
     */
    formatDeviceLabel(device) {
        const deviceLabels = {
            'tandem': 'Tandem',
            'medtronic': 'Medtronic',
            'omnipod': 'Omnipod',
            'ypsomed': 'Ypsomed',
            'roche': 'Roche',
            'sooil': 'SooIL',
            'dexcom': 'Dexcom',
            'libre': 'Freestyle Libre',
            'guardian': 'Medtronic Guardian'
        };
        return deviceLabels[device] || device;
    }

    /**
     * Detect devices from uploaded PDF and show confirmation UI
     */
    async detectDevicesFromPDF(filename) {
        try {
            const response = await fetch(`/api/detect-devices?filename=${encodeURIComponent(filename)}`, {
                method: 'POST'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Device detection failed');
            }

            const result = await response.json();
            console.log('Device detection result:', result);

            const detected = {
                pump: result.pump || null,
                cgm: result.cgm || null,
                pump_confidence: result.pump_confidence || 0,
                cgm_confidence: result.cgm_confidence || 0
            };

            // Show detected devices in confirmation area
            this.showDetectedDevices(detected);

            return detected;

        } catch (error) {
            console.error('Device detection error:', error);
            // Don't fail the upload, just skip device detection
            console.warn('Skipping device detection UI');
            return null;
        }
    }

    async deleteUserSource(filename) {
        if (!confirm(`Delete "${filename}"? This will remove it from your knowledge base.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/sources/${encodeURIComponent(filename)}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Delete failed');
            }

            // Refresh lists
            this.loadSettingsSources();
            this.loadSources();

        } catch (error) {
            console.error('Delete error:', error);
            alert(`Failed to delete: ${error.message}`);
        }
    }
}




// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.diabuddyChat = new DiabetesBuddyChat();

    // Load knowledge base status
    window.diabuddyChat.loadKnowledgeBaseStatus();

    // Load sources in sidebar
    window.diabuddyChat.loadSources();
});
