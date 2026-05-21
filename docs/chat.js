requireAuth();

const messagesContainer = document.getElementById("messages");
const input = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");

const userId = localStorage.getItem("user_id");

// Добавление сообщения
function addMessage(role, text) {
    const message = document.createElement("div");
    message.classList.add("message", role);
    message.textContent = text;
    messagesContainer.appendChild(message);
    scrollToBottom();
    return message;
}

// Скролл вниз
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Индикатор печати
function createTypingIndicator() {
    const wrapper = document.createElement("div");
    wrapper.classList.add("message", "ai");
    wrapper.innerHTML = `
        <div class="typing">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;
    messagesContainer.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
}

// Загрузка истории
async function loadHistory() {
    try {
        const response = await fetch(`${API_URL}/history?user_id=${userId}`);
        const history = await response.json();
        history.forEach((msg) => {
            addMessage(msg.role, msg.content);
        });
    } catch (error) {
        addMessage("ai", "Не удалось загрузить историю чата.");
    }
}

// Отправка сообщения
async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    addMessage("user", text);
    input.value = "";

    const typing = createTypingIndicator();

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: userId, message: text })
        });

        typing.remove();

        if (!response.ok) {
            const data = await response.json();
            addMessage("ai", data.error || "Ошибка при получении ответа.");
            return;
        }

        const aiMessage = addMessage("ai", "");

        // Читаем поток
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            // Парсим SSE-формат: "data: текст\n\n"
            const lines = chunk.split("\n");
            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const text = line.substring(6);
                    aiMessage.textContent += text;
                    scrollToBottom();
                }
            }
        }
    } catch (error) {
        typing.remove();
        addMessage("ai", "Сервер недоступен. Попробуйте позже.");
    }
}

// Enter для отправки
input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Кнопка отправки
sendBtn.addEventListener("click", sendMessage);

// Загрузка истории
loadHistory();