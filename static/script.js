/**
 * Frontend для AI Agent — чат с SSE, редактированием, стопом.
 */
(function() {
    'use strict';

    // ===== Состояние =====
    const state = {
        sessionId: null,
        isRunning: false,
        currentText: '',        // Накопленный текст AI за текущий запрос
        editMessageId: null,    // ID сообщения, которое редактируем
        abortController: null,  // Для прерывания fetch
    };

    // ===== DOM элементы =====
    const els = {
        messages: document.getElementById('messages'),
        input: document.getElementById('message-input'),
        btnSend: document.getElementById('btn-send'),
        btnStop: document.getElementById('btn-stop'),
        btnNewChat: document.getElementById('btn-new-chat'),
        btnClear: document.getElementById('btn-clear'),
        btnCopyDialog: document.getElementById('btn-copy-dialog'),
        btnSaveCredentials: document.getElementById('btn-save-credentials'),
        saveStatus: document.getElementById('save-status'),
        aiMode: document.getElementById('ai-mode'),
        apiKey: document.getElementById('api-key'),
        ibmApiKey: document.getElementById('ibm-api-key'),
        qiApiToken: document.getElementById('qi-api-token'),
        qiEmail: document.getElementById('qi-email'),
        qiPassword: document.getElementById('qi-password'),
        hfToken: document.getElementById('hf-token'),
        kaggleKey: document.getElementById('kaggle-key'),
        modalTokenId: document.getElementById('modal-token-id'),
        modalTokenSecret: document.getElementById('modal-token-secret'),
        sshHost: document.getElementById('ssh-host'),
        sshPort: document.getElementById('ssh-port'),
        sshUsername: document.getElementById('ssh-username'),
        sshKeyPath: document.getElementById('ssh-key-path'),
        sshPassword: document.getElementById('ssh-password'),
        bioProjectPath: document.getElementById('bio-project-path'),
        neuroPythonPath: document.getElementById('neuro-python-path'),
        modelName: document.getElementById('model-name'),
        connectionStatus: document.getElementById('connection-status'),
    };

    // ===== Инициализация =====
    async function init() {
        // Создаём сессию
        try {
            const res = await fetch('/api/session', { method: 'POST' });
            const data = await res.json();
            state.sessionId = data.session_id;
        } catch (e) {
            console.error('Failed to create session:', e);
        }

        // Загружаем сохранённые настройки
        loadSettings();

        // События
        els.btnSend.addEventListener('click', sendMessage);
        els.btnStop.addEventListener('click', stopChat);
        els.btnNewChat.addEventListener('click', newChat);
        els.btnClear.addEventListener('click', clearHistory);
        els.btnCopyDialog.addEventListener('click', copyFullDialog);
        els.btnSaveCredentials.addEventListener('click', saveCredentials);
        els.aiMode.addEventListener('change', saveSettings);
        els.apiKey.addEventListener('change', saveSettings);

        // Enter для отправки, Shift+Enter для новой строки
        els.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // Авто-высота textarea
        els.input.addEventListener('input', autoResizeTextarea);

        // Загружаем историю
        loadHistory();

        // Обновляем статус
        updateStatus();
    }

    // ===== Настройки =====
    function loadSettings() {
        const savedMode = localStorage.getItem('agent_ai_mode') || 'zen';
        const savedKey = localStorage.getItem('agent_api_key') || '';
        const savedIbmKey = localStorage.getItem('agent_ibm_api_key') || '';
        const savedQiToken = localStorage.getItem('agent_qi_api_token') || '';
        const savedQiEmail = localStorage.getItem('agent_qi_email') || '';
        const savedQiPass = localStorage.getItem('agent_qi_password') || '';
        const savedHfToken = localStorage.getItem('agent_hf_token') || '';
        const savedKaggleKey = localStorage.getItem('agent_kaggle_key') || '';
        const savedModalId = localStorage.getItem('agent_modal_token_id') || '';
        const savedModalSecret = localStorage.getItem('agent_modal_token_secret') || '';
        const savedSshHost = localStorage.getItem('agent_ssh_host') || '';
        const savedSshPort = localStorage.getItem('agent_ssh_port') || '22';
        const savedSshUser = localStorage.getItem('agent_ssh_username') || 'root';
        const savedSshKey = localStorage.getItem('agent_ssh_key_path') || '';
        const savedSshPass = localStorage.getItem('agent_ssh_password') || '';
        const savedBioPath = localStorage.getItem('agent_bio_project_path') || '';
        const savedNeuroPath = localStorage.getItem('agent_neuro_python_path') || '';
        if (els.sshHost) els.sshHost.value = savedSshHost;
        if (els.sshPort) els.sshPort.value = savedSshPort;
        if (els.sshUsername) els.sshUsername.value = savedSshUser;
        if (els.sshKeyPath) els.sshKeyPath.value = savedSshKey;
        if (els.sshPassword) els.sshPassword.value = savedSshPass;
        if (els.bioProjectPath) els.bioProjectPath.value = savedBioPath;
        if (els.neuroPythonPath) els.neuroPythonPath.value = savedNeuroPath;
        els.aiMode.value = savedMode;
        els.apiKey.value = savedKey;
        els.ibmApiKey.value = savedIbmKey;
        els.qiApiToken.value = savedQiToken;
        els.qiEmail.value = savedQiEmail;
        els.qiPassword.value = savedQiPass;
        if (els.hfToken) els.hfToken.value = savedHfToken;
        if (els.kaggleKey) els.kaggleKey.value = savedKaggleKey;
        if (els.modalTokenId) els.modalTokenId.value = savedModalId;
        if (els.modalTokenSecret) els.modalTokenSecret.value = savedModalSecret;
        updateCredStatus();
    }

    function saveSettings() {
        localStorage.setItem('agent_ai_mode', els.aiMode.value);
        localStorage.setItem('agent_api_key', els.apiKey.value);
    }

    function saveCredentials() {
        localStorage.setItem('agent_ibm_api_key', els.ibmApiKey.value);
        localStorage.setItem('agent_qi_api_token', els.qiApiToken.value);
        localStorage.setItem('agent_qi_email', els.qiEmail.value);
        localStorage.setItem('agent_qi_password', els.qiPassword.value);
        if (els.hfToken) localStorage.setItem('agent_hf_token', els.hfToken.value);
        if (els.kaggleKey) localStorage.setItem('agent_kaggle_key', els.kaggleKey.value);
        if (els.modalTokenId) localStorage.setItem('agent_modal_token_id', els.modalTokenId.value);
        if (els.modalTokenSecret) localStorage.setItem('agent_modal_token_secret', els.modalTokenSecret.value);
        if (els.sshHost) localStorage.setItem('agent_ssh_host', els.sshHost.value);
        if (els.sshPort) localStorage.setItem('agent_ssh_port', els.sshPort.value);
        if (els.sshUsername) localStorage.setItem('agent_ssh_username', els.sshUsername.value);
        if (els.sshKeyPath) localStorage.setItem('agent_ssh_key_path', els.sshKeyPath.value);
        if (els.sshPassword) localStorage.setItem('agent_ssh_password', els.sshPassword.value);
        if (els.bioProjectPath) localStorage.setItem('agent_bio_project_path', els.bioProjectPath.value);
        if (els.neuroPythonPath) localStorage.setItem('agent_neuro_python_path', els.neuroPythonPath.value);
        showSaveStatus('\u2705 Данные сохранены');
        updateCredStatus();
    }

    function updateCredStatus() {
        const parts = [];
        const ibm = localStorage.getItem('agent_ibm_api_key') || '';
        const qiToken = localStorage.getItem('agent_qi_api_token') || '';
        const qiEmail = localStorage.getItem('agent_qi_email') || '';
        const qiPass = localStorage.getItem('agent_qi_password') || '';
        const hfToken = localStorage.getItem('agent_hf_token') || '';
        const kaggleKey = localStorage.getItem('agent_kaggle_key') || '';
        const modalId = localStorage.getItem('agent_modal_token_id') || '';
        const modalSecret = localStorage.getItem('agent_modal_token_secret') || '';
        if (ibm) parts.push('\ud83d\udd11 IBM');
        if (qiToken) parts.push('\ud83d\udd10 QI Token');
        if (qiEmail && qiPass) parts.push('\ud83d\udd10 QI Email+Password');
        else if (qiEmail) parts.push('\ud83d\udd10 QI Email');
        if (hfToken) parts.push('\ud83e\udde0 HF');
        if (kaggleKey) parts.push('\ud83c\udfae Kaggle');
        if (modalId && modalSecret) parts.push('\u2601\ufe0f Modal');
        else if (modalId) parts.push('\u2601\ufe0f Modal (no secret)');
        const sshHost = localStorage.getItem('agent_ssh_host') || '';
        const sshUser = localStorage.getItem('agent_ssh_username') || '';
        if (sshHost && sshUser) parts.push('\ud83d\udda5\ufe0f SSH');
        if (parts.length > 0) {
            els.saveStatus.textContent = '\u2713 ' + parts.join(', ');
            els.saveStatus.style.color = 'var(--accent)';
        } else {
            els.saveStatus.textContent = 'Нет сохранённых ключей';
            els.saveStatus.style.color = 'var(--text-muted)';
        }
    }

    function showSaveStatus(msg) {
        els.saveStatus.textContent = msg;
        els.saveStatus.style.color = '#4caf50';
        setTimeout(() => updateCredStatus(), 3000);
    }

    // ===== История сообщений =====
    async function loadHistory() {
        try {
            const res = await fetch(`/api/messages?session_id=${state.sessionId}`);
            const data = await res.json();
            const messages = data.messages || [];

            // Очищаем welcome если есть сообщения
            const welcome = els.messages.querySelector('.welcome');
            if (messages.length > 0 && welcome) {
                welcome.remove();
            }

            messages.forEach(msg => {
                if (msg.role === 'user') {
                    appendUserMessage(msg.content, msg.timestamp);
                } else if (msg.role === 'assistant') {
                    appendAssistantMessage(msg.content, msg.timestamp);
                } else if (msg.role === 'tool') {
                    appendToolResult(msg.content, msg.timestamp);
                }
            });

            scrollToBottom();
        } catch (e) {
            console.error('Failed to load history:', e);
        }
    }

    // ===== Отправка сообщения =====
    async function sendMessage() {
        const text = els.input.value.trim();
        if (!text || state.isRunning) return;

        // Если редактируем — удаляем старое сообщение
        if (state.editMessageId) {
            const editMsg = document.getElementById(state.editMessageId);
            if (editMsg) editMsg.remove();
            state.editMessageId = null;
        }

        // Показываем сообщение пользователя
        appendUserMessage(text);
        els.input.value = '';
        autoResizeTextarea();

        // Убираем welcome
        const welcome = els.messages.querySelector('.welcome');
        if (welcome) welcome.remove();

        // Показываем индикатор "думает"
        const thinkingId = showThinking();

        // Меняем UI
        state.isRunning = true;
        els.btnSend.style.display = 'none';
        els.btnStop.style.display = 'flex';
        els.input.disabled = true;
        state.currentText = '';

        // Создаём AbortController
        state.abortController = new AbortController();

        try {
            const mode = els.aiMode.value;
            const apiKey = els.apiKey.value.trim();

            // Если указан ключ — передаём в теле запроса, не в заголовке (безопаснее)
            const headers = { 'Content-Type': 'application/json' };

            // Для Zen API ключ не нужен — использует "Bearer public".
            // Отправляем ключ только для других режимов, где он обязателен.
            const body = {
                session_id: state.sessionId,
                message: text,
                mode: mode,
            };
            if (mode !== 'zen' && apiKey) {
                body.api_key = apiKey;
            }
            const ibmApiKey = els.ibmApiKey.value.trim();
            const qiApiToken = els.qiApiToken.value.trim();
            const qiEmail = els.qiEmail.value.trim();
            const qiPassword = els.qiPassword.value.trim();
            if (ibmApiKey) {
                body.ibm_api_key = ibmApiKey;
            }
            if (qiApiToken) {
                body.qi_api_token = qiApiToken;
            }
            if (qiEmail) {
                body.qi_email = qiEmail;
            }
            if (qiPassword) {
                body.qi_password = qiPassword;
            }
            if (els.hfToken) {
                const hfToken = els.hfToken.value.trim();
                if (hfToken) body.hf_token = hfToken;
            }
            if (els.kaggleKey) {
                const kaggleKey = els.kaggleKey.value.trim();
                if (kaggleKey) body.kaggle_key = kaggleKey;
            }
            if (els.modalTokenId) {
                const modalTokenId = els.modalTokenId.value.trim();
                if (modalTokenId) body.modal_token_id = modalTokenId;
            }
            if (els.modalTokenSecret) {
                const modalTokenSecret = els.modalTokenSecret.value.trim();
                if (modalTokenSecret) body.modal_token_secret = modalTokenSecret;
            }
            if (els.sshHost) {
                const sshHost = els.sshHost.value.trim();
                if (sshHost) body.ssh_host = sshHost;
            }
            if (els.sshPort) {
                const sshPort = els.sshPort.value.trim();
                if (sshPort) body.ssh_port = parseInt(sshPort, 10) || 22;
            }
            if (els.sshUsername) {
                const sshUser = els.sshUsername.value.trim();
                if (sshUser) body.ssh_username = sshUser;
            }
            if (els.sshKeyPath) {
                const sshKeyPath = els.sshKeyPath.value.trim();
                if (sshKeyPath) body.ssh_key_path = sshKeyPath;
            }
            if (els.sshPassword) {
                const sshPassword = els.sshPassword.value.trim();
                if (sshPassword) body.ssh_password = sshPassword;
            }
            if (els.bioProjectPath) {
                const bioPath = els.bioProjectPath.value.trim();
                if (bioPath) body.bio_project_path = bioPath;
            }
            if (els.neuroPythonPath) {
                const neuroPath = els.neuroPythonPath.value.trim();
                if (neuroPath) body.neuro_python_path = neuroPath;
            }

            const res = await fetch('/api/chat', {
                method: 'POST',
                headers,
                signal: state.abortController.signal,
                body: JSON.stringify(body),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: 'Unknown error' }));
                showError(err.error || `HTTP ${res.status}`);
                removeThinking(thinkingId);
                state.isRunning = false;
                resetUI();
                return;
            }

            // Читаем SSE поток
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let assistantMsgId = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const event = JSON.parse(line.slice(6));
                            assistantMsgId = handleSSEEvent(event, thinkingId, assistantMsgId);
                            if (event.type === 'done') {
                                assistantMsgId = null;
                            }
                        } catch (e) {
                            console.warn('SSE parse error:', e);
                        }
                    }
                }
            }

            if (buffer.startsWith('data: ')) {
                try {
                    const event = JSON.parse(buffer.slice(6));
                    handleSSEEvent(event, thinkingId, null);
                } catch (e) {}
            }

        } catch (e) {
            if (e.name === 'AbortError') {
                // Пользователь остановил
                appendAssistantMessage('⏹️ **Запрос остановлен пользователем.**\n\nМожешь продолжить — напиши новое сообщение.');
            } else {
                console.error('Chat error:', e);
                showError(`Ошибка соединения: ${e.message}`);
            }
        } finally {
            removeThinking(thinkingId);
            state.isRunning = false;
            state.abortController = null;
            resetUI();
        }
    }

    // ===== Обработка SSE событий =====
    function handleSSEEvent(event, thinkingId, assistantMsgId) {
        switch (event.type) {
            case 'user_text':
                removeThinking(thinkingId);
                if (!assistantMsgId) {
                    assistantMsgId = appendAssistantMessage(event.content);
                    state.currentText = event.content;
                } else {
                    state.currentText += event.content;
                    updateAssistantMessage(assistantMsgId, state.currentText);
                }
                scrollToBottom();
                break;

            case 'thinking':
                updateThinkingContent(thinkingId, event.content);
                break;

            case 'tool_start':
                removeThinking(thinkingId);
                showToolExecution(event.tool, 'running');
                break;

            case 'tool_result':
                updateToolResult(event.tool, event.result, event.formatted);
                break;

            case 'done':
                break;

            case 'error':
                removeThinking(thinkingId);
                showError(event.content);
                break;
        }
        return assistantMsgId;
    }

    // ===== Остановка =====
    function stopChat() {
        if (state.abortController) {
            state.abortController.abort();
        }

        // Также отправляем сигнал на сервер
        fetch('/api/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: state.sessionId }),
        }).catch(() => {});
    }

    // ===== Новый чат =====
    async function newChat() {
        try {
            const res = await fetch('/api/session', { method: 'POST' });
            const data = await res.json();
            state.sessionId = data.session_id;
            els.messages.innerHTML = `
                <div class="welcome">
                    <div class="welcome-icon">🤖</div>
                    <h2>Привет! Я — AI Agent</h2>
                    <p>Новый чат создан. Напиши мне задачу!</p>
                </div>
            `;
        } catch (e) {
            console.error('Failed to create new session:', e);
        }
    }

    // ===== Очистить историю =====
    async function clearHistory() {
        try {
            await fetch('/api/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: state.sessionId }),
            });
            els.messages.innerHTML = `
                <div class="welcome">
                    <div class="welcome-icon">🤖</div>
                    <h2>История очищена</h2>
                    <p>Напиши новый запрос!</p>
                </div>
            `;
        } catch (e) {
            console.error('Failed to clear history:', e);
        }
    }

    // ===== Редактирование сообщения =====
    function editMessage(msgId, text) {
        if (state.isRunning) return;

        // Удаляем исходное сообщение
        const msgEl = document.getElementById(msgId);
        if (msgEl) msgEl.remove();

        // Ставим текст в input
        els.input.value = text;
        autoResizeTextarea();
        els.input.focus();

        state.editMessageId = msgId;
    }

    // ===== Вспомогательные функции =====

    function appendUserMessage(text, timestamp) {
        const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
        const time = timestamp ? formatTime(timestamp) : formatTime(new Date().toISOString());
        const textEscaped = JSON.stringify(text).replace(/"/g, '&quot;');

        const html = `
            <div id="${id}" class="message message-user">
                <div class="message-avatar">👤</div>
                <div class="message-body">
                    <div class="message-header">
                        <span class="message-role">Ты</span>
                        <span class="message-time">${time}</span>
                        <span class="msg-buttons">
                            <button class="btn-icon" onclick="window.__agentCopy('${textEscaped}')" title="Копировать промт">📋</button>
                            <button class="btn-icon" onclick="window.__agentRerun('${id}', '${textEscaped}')" title="Перезапустить">🔄</button>
                            <button class="btn-icon" onclick="window.__agentEdit('${id}', '${textEscaped}')" title="Редактировать">✏️</button>
                        </span>
                    </div>
                    <div class="message-content">${escapeHtml(text)}</div>
                </div>
            </div>
        `;

        els.messages.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
        return id;
    }

    function appendAssistantMessage(text, timestamp) {
        const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
        const time = timestamp ? formatTime(timestamp) : formatTime(new Date().toISOString());

        const html = `
            <div id="${id}" class="message message-assistant">
                <div class="message-avatar">🤖</div>
                <div class="message-body">
                    <div class="message-header">
                        <span class="message-role">Agent</span>
                        <span class="message-time">${time}</span>
                    </div>
                    <div class="message-content">${renderMarkdown(text)}</div>
                </div>
            </div>
        `;

        els.messages.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
        return id;
    }

    function updateAssistantMessage(id, text) {
        const el = document.getElementById(id);
        if (!el) return;
        const contentEl = el.querySelector('.message-content');
        if (contentEl) {
            contentEl.innerHTML = renderMarkdown(text);
        }
    }

    function appendToolResult(text, timestamp) {
        const id = 'tool-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
        const time = timestamp ? formatTime(timestamp) : formatTime(new Date().toISOString());

        const html = `
            <div id="${id}" class="message message-tool">
                <div class="message-avatar">🔧</div>
                <div class="message-body">
                    <div class="message-header">
                        <span class="message-role">Инструмент</span>
                        <span class="message-time">${time}</span>
                    </div>
                    <div class="message-content">${escapeHtml(text)}</div>
                </div>
            </div>
        `;

        els.messages.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
        return id;
    }

    function showThinking() {
        const id = 'thinking-' + Date.now();
        const html = `
            <div id="${id}" class="thinking-indicator">
                <div class="thinking-dots">
                    <span></span><span></span><span></span>
                </div>
                <span class="thinking-text">Думаю...</span>
            </div>
        `;
        els.messages.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
        return id;
    }

    function updateThinkingContent(id, text) {
        const el = document.getElementById(id);
        if (!el) return;
        const textEl = el.querySelector('.thinking-text');
        if (textEl) {
            const short = text.replace(/<[^>]*>/g, '').slice(0, 80);
            textEl.textContent = 'Думаю: ' + short + '...';
        }
    }

    function removeThinking(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function showToolExecution(tool, status) {
        const action = tool.action || '?';
        const params = tool.command || tool.path || JSON.stringify(tool);
        const id = 'tool-exec-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);

        const html = `
            <div id="${id}" class="tool-exec">
                <div class="tool-exec-header" onclick="toggleToolOutput('${id}')">
                    <span class="icon">⚡</span>
                    <span class="tool-action">${escapeHtml(action)}</span>
                    <code class="tool-params">${escapeHtml(String(params).slice(0, 200))}</code>
                    <span class="status running">⏳</span>
                    <span class="copy-btn" onclick="event.stopPropagation();copyToolResult('${id}')" title="Copy output">📋</span>
                </div>
                <div class="tool-exec-body" style="display:none;"></div>
            </div>
        `;

        els.messages.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
        return id;
    }

    window.toggleToolOutput = function(id) {
        const el = document.getElementById(id);
        if (!el) return;
        const body = el.querySelector('.tool-exec-body');
        if (body) {
            body.style.display = body.style.display === 'none' ? 'block' : 'none';
        }
    };

    function updateToolResult(tool, result, formatted) {
        // Ищем последний tool-exec блок
        const blocks = els.messages.querySelectorAll('.tool-exec');
        const block = blocks[blocks.length - 1];
        if (!block) return;

        const header = block.querySelector('.tool-exec-header');
        const body = block.querySelector('.tool-exec-body');
        const statusEl = header ? header.querySelector('.status') : null;

        if (result.success) {
            if (statusEl) {
                statusEl.className = 'status success';
                statusEl.textContent = '✅';
            }
        } else {
            if (statusEl) {
                statusEl.className = 'status error';
                statusEl.textContent = '❌';
            }
            block.style.borderColor = 'var(--danger)';
        }

        if (body) {
            const stdout = result.stdout || '';
            const stderr = result.stderr || '';
            const exitCode = result.returncode !== undefined ? `[Exit: ${result.returncode}]` : '';
            let display = '';
            if (exitCode) display += exitCode + '\n';
            if (stdout) display += stdout;
            if (stderr) display += (display ? '\n--- stderr ---\n' : '') + stderr;
            body.textContent = display || (result.success ? '(пустой вывод)' : '(без вывода)');
            // Always show body when there's content (for copyability)
            if (display.length > 0) {
                body.style.display = 'block';
            }
        }

        scrollToBottom();
    }

    window.copyToolResult = function(id) {
        const el = document.getElementById(id);
        if (!el) return;
        const body = el.querySelector('.tool-exec-body');
        if (!body) return;
        const text = body.textContent || '';
        copyToClipboard(text, el);
    };

    function copyToClipboard(text, contextEl) {
        navigator.clipboard.writeText(text).then(() => {
            const btn = contextEl ? contextEl.querySelector('.copy-btn') : null;
            if (btn) {
                btn.textContent = '\u2705';
                setTimeout(() => btn.textContent = '\uD83D\uDCCB', 2000);
            }
        }).catch(() => {
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        });
    }

    function copyFullDialog() {
        const blocks = els.messages.querySelectorAll('.message, .tool-exec, .error-message');
        if (!blocks.length) return;

        let lines = [];
        blocks.forEach(block => {
            const roleEl = block.querySelector('.message-role');
            const contentEl = block.querySelector('.message-content');
            const toolHeader = block.querySelector('.tool-exec-header');
            const toolBody = block.querySelector('.tool-exec-body');
            const errorEl = block.querySelector('.error-message');

            if (roleEl && contentEl) {
                const role = roleEl.textContent.trim();
                const text = block.querySelector('.message-content')?.textContent?.trim() || '';
                lines.push(`[${role}]`);
                lines.push(text);
                lines.push('');
            } else if (toolHeader) {
                const headerText = toolHeader.textContent?.trim() || '';
                // Get body text even if hidden
                let bodyText = toolBody?.textContent?.trim() || '';
                // Also get from any pre/code inside tool-exec
                if (!bodyText) {
                    const codeBlocks = block.querySelectorAll('pre, code');
                    bodyText = Array.from(codeBlocks).map(el => el.textContent).join('\n').trim();
                }
                lines.push(`[TOOL] ${headerText}`);
                if (bodyText) {
                    lines.push(bodyText);
                }
                lines.push('');
            } else if (errorEl) {
                lines.push(`[ERROR] ${errorEl.textContent?.trim() || ''}`);
                lines.push('');
            }
        });

        const fullText = lines.join('\n');
        copyToClipboard(fullText, null);
        // Visual feedback
        const btn = els.btnCopyDialog;
        const originalText = btn.textContent;
        btn.textContent = '✅ Скопировано!';
        setTimeout(() => btn.textContent = originalText, 2000);
    }

    function showError(text) {
        const id = 'error-' + Date.now();
        const html = `
            <div id="${id}" class="error-message">
                ❌ ${escapeHtml(text)}
            </div>
        `;
        els.messages.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
    }

    function resetUI() {
        els.btnSend.style.display = 'flex';
        els.btnStop.style.display = 'none';
        els.input.disabled = false;
        els.input.focus();
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            els.messages.scrollTop = els.messages.scrollHeight;
        });
    }

    function autoResizeTextarea() {
        els.input.style.height = 'auto';
        els.input.style.height = Math.min(els.input.scrollHeight, 200) + 'px';
    }

    function updateStatus() {
        const mode = els.aiMode.value;
        const labels = {
            'zen': 'DeepSeek V4 Flash Free (Zen)',
            'gemini': 'Google Gemini',
            'deepseek_free': 'DeepSeek Free (OpenRouter)',
            'deepseek_api': 'DeepSeek API',
            'qwen': 'Qwen',
        };
        els.modelName.textContent = labels[mode] || mode;
        els.connectionStatus.textContent = '🟢 Готов';
    }

    els.aiMode.addEventListener('change', updateStatus);

    // ===== Форматирование Markdown (упрощённое) =====
    function renderMarkdown(text) {
        if (!text) return '';

        let html = escapeHtml(text);

        // Код-блоки ``` ... ```
        html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
            return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
        });

        // Инлайн-код `...`
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // **жирный**
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

        // *курсив*
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

        // Ссылки [text](url)
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

        // Заголовки ##
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');

        // Списки
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

        // Новые строки
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatTime(iso) {
        try {
            const d = new Date(iso);
            return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    }

    // ===== Экспорт для inline onclick =====
    window.__agentEdit = editMessage;

    window.__agentCopy = function(text) {
        copyToClipboard(text, null);
        // visual feedback
        const btn = event?.target;
        if (btn) {
            const orig = btn.textContent;
            btn.textContent = '✅';
            setTimeout(() => btn.textContent = orig, 1500);
        }
    };

    window.__agentRerun = function(id, text) {
        // Remove old message
        const oldMsg = document.getElementById(id);
        if (oldMsg) oldMsg.remove();
        // Set text in input and send
        els.input.value = text;
        autoResizeTextarea();
        sendMessage();
    };

    // ===== Запуск =====
    document.addEventListener('DOMContentLoaded', init);
})();
