import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.db.session import get_db
from app.schemas.agent import AgentAskRequest, AgentAskResponse
from app.services.agent_service import ask_agent
from app.services.profile_service import get_profile_by_user_id

load_dotenv()

router = APIRouter()

DEMO_USER_ID = os.getenv("DEMO_USER_ID", "demo_user")


@router.post("/ask", response_model=AgentAskResponse)
def ask_house_agent(
    request: AgentAskRequest,
    db: Session = Depends(get_db)
):
    profile = get_profile_by_user_id(db, DEMO_USER_ID)

    return ask_agent(
        db=db,
        profile=profile,
        message=request.message,
        user_id=DEMO_USER_ID
    )

@router.post("/ask/text", response_class=PlainTextResponse)
def ask_house_agent_text(
    request: AgentAskRequest,
    db: Session = Depends(get_db),
):
    response = ask_agent(
        db=db,
        message=request.message,
        user_id=DEMO_USER_ID,
    )

    return response.answer

@router.get("/demo", response_class=HTMLResponse)
def agent_demo_page():
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <title>AI-агент по дому</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f7f5;
            margin: 0;
            padding: 32px;
            color: #1f2933;
        }

        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 18px;
            padding: 28px;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.08);
        }

        h1 {
            margin-top: 0;
            font-size: 28px;
        }

        .subtitle {
            color: #64748b;
            margin-bottom: 24px;
        }

        textarea {
            width: 100%;
            min-height: 90px;
            box-sizing: border-box;
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            padding: 14px;
            font-size: 16px;
            resize: vertical;
            outline: none;
        }

        button {
            margin-top: 12px;
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 12px;
            padding: 12px 18px;
            font-size: 16px;
            cursor: pointer;
        }

        button:disabled {
            opacity: 0.6;
            cursor: wait;
        }

        .answer {
            margin-top: 28px;
            padding: 24px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 16px;
            line-height: 1.55;
            font-size: 16px;
        }

        .answer h3 {
            margin-top: 22px;
            margin-bottom: 8px;
            font-size: 20px;
        }

        .answer h3:first-child {
            margin-top: 0;
        }

        .answer p {
            margin: 8px 0;
        }

        .answer .item {
            margin: 8px 0;
            padding-left: 10px;
        }

        .answer .muted {
            color: #64748b;
        }

        .error {
            margin-top: 18px;
            color: #b91c1c;
        }

        .examples {
            margin-top: 18px;
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .example {
            background: #eef2ff;
            color: #3730a3;
            padding: 8px 10px;
            border-radius: 999px;
            font-size: 14px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AI-агент по обслуживанию дома</h1>
        <div class="subtitle">
            Демонстрационная страница. Показывает только пользовательский ответ агента без технических полей.
        </div>

        <textarea id="message" placeholder="Например: Что делать если вода идёт рывками?"></textarea>

        <button id="sendButton" onclick="sendMessage()">Спросить агента</button>

        <div class="examples">
            <span class="example" onclick="setExample('Что мне надо делать в этом месяце?')">Чек-лист месяца</span>
            <span class="example" onclick="setExample('Покажи память дома')">Память дома</span>
            <span class="example" onclick="setExample('Что делать если вода идёт рывками?')">Проблема с водой</span>
            <span class="example" onclick="setExample('Покажи профиль дома')">Профиль дома</span>
        </div>

        <div id="error" class="error"></div>
        <div id="answer" class="answer" style="display: none;"></div>
    </div>

    <script>
        function escapeHtml(text) {
            return String(text || "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        }

        function renderAnswer(text) {
            const lines = String(text || "").split("\\n");
            let html = "";

            for (const rawLine of lines) {
                const line = rawLine.trim();

                if (!line) {
                    html += "<br>";
                    continue;
                }

                if (line.startsWith("### ")) {
                    html += "<h3>" + escapeHtml(line.slice(4)) + "</h3>";
                    continue;
                }

                if (/^\\d+\\.\\s+/.test(line)) {
                    html += "<div class='item'>" + escapeHtml(line) + "</div>";
                    continue;
                }

                if (line.startsWith("- ")) {
                    html += "<div class='item'>• " + escapeHtml(line.slice(2)) + "</div>";
                    continue;
                }

                html += "<p>" + escapeHtml(line) + "</p>";
            }

            return html;
        }

        function setExample(text) {
            document.getElementById("message").value = text;
        }

        async function sendMessage() {
            const messageEl = document.getElementById("message");
            const answerEl = document.getElementById("answer");
            const errorEl = document.getElementById("error");
            const button = document.getElementById("sendButton");

            const message = messageEl.value.trim();

            if (!message) {
                errorEl.textContent = "Введите вопрос.";
                return;
            }

            errorEl.textContent = "";
            answerEl.style.display = "block";
            answerEl.innerHTML = "<p class='muted'>Агент думает...</p>";
            button.disabled = true;

            try {
                const response = await fetch("/agent/ask", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ message })
                });

                if (!response.ok) {
                    throw new Error("Ошибка сервера: " + response.status);
                }

                const data = await response.json();
                answerEl.innerHTML = renderAnswer(data.answer || "Пустой ответ.");
            } catch (error) {
                answerEl.style.display = "none";
                errorEl.textContent = "Не удалось получить ответ: " + error.message;
            } finally {
                button.disabled = false;
            }
        }
    </script>
</body>
</html>
"""