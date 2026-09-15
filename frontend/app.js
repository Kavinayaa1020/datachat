const API_BASE =
  window.DATACHAT_API_BASE || "http://localhost:8000";

let sessionId =
  localStorage.getItem("datachat_session_id") || null;

const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chatForm");
const inputEl = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const backendStatusEl = document.getElementById("backendStatus");
const schemaListEl = document.getElementById("schemaList");
const suggestionListEl = document.getElementById("suggestionList");
const newChatBtn = document.getElementById("newChatBtn");
const historyListEl = document.getElementById("historyList");

let chatHistory = JSON.parse(
  localStorage.getItem("datachat_chat_history") || "[]"
);

function saveChatHistory() {
  localStorage.setItem(
    "datachat_chat_history",
    JSON.stringify(chatHistory)
  );
}

function renderChatHistory() {
  historyListEl.innerHTML = "";

  if (chatHistory.length === 0) {
    historyListEl.innerHTML =
      '<li class="history-empty">No conversations yet</li>';
    return;
  }

  chatHistory.forEach((chat) => {
    const li = document.createElement("li");

    li.className = "history-item";
    li.textContent = chat.title || "Untitled conversation";
    li.title = chat.title || "Untitled conversation";

    li.addEventListener("click", function () {
      loadChat(chat);
    });

    historyListEl.appendChild(li);
  });
}

function saveCurrentChat(message) {
  if (!sessionId) return;

  let chat = chatHistory.find(function (item) {
    return item.sessionId === sessionId;
  });

  if (!chat) {
    chat = {
      sessionId: sessionId,
      title: message,
      messages: []
    };

    chatHistory.unshift(chat);
  }

  if (!chat.title) {
    chat.title = message;
  }

  if (!chat.messages) {
    chat.messages = [];
  }

  chatHistory = chatHistory.slice(0, 20);

  saveChatHistory();
  renderChatHistory();
}

function saveMessageToCurrentChat(role, content) {
  if (!sessionId) return;

  const chat = chatHistory.find(function (item) {
    return item.sessionId === sessionId;
  });

  if (!chat) return;

  if (!chat.messages) {
    chat.messages = [];
  }

  chat.messages.push({
    role: role,
    content: content
  });

  saveChatHistory();
}

async function loadChat(chat) {
  sessionId = chat.sessionId;

  localStorage.setItem(
    "datachat_session_id",
    sessionId
  );

  messagesEl.innerHTML = "";

  if (chat.messages && chat.messages.length > 0) {
    for (const item of chat.messages) {
      if (item.role === "user") {
        appendUserMessage(item.content, false);
      }

      if (item.role === "assistant") {
        await appendAssistantMessage(
          item.content,
          [],
          [],
          false,
          false
        );
      }
    }

    scrollToBottom();
    inputEl.value = "";
    autoResizeTextarea();
    return;
  }

  try {
    const res = await fetch(
      API_BASE +
        "/api/session/history?session_id=" +
        encodeURIComponent(sessionId)
    );

    if (!res.ok) {
      throw new Error(
        "Failed to load conversation (" +
          res.status +
          ")"
      );
    }

    const data = await res.json();

    if (!data.history || data.history.length === 0) {
      showEmptyState();
      return;
    }

    chat.messages = data.history.map(function (item) {
      return {
        role: item.role,
        content: item.content
      };
    });

    saveChatHistory();

    for (const item of data.history) {
      if (item.role === "user") {
        appendUserMessage(item.content, false);
      }

      if (item.role === "assistant") {
        await appendAssistantMessage(
          item.content,
          [],
          [],
          false,
          false
        );
      }
    }

    scrollToBottom();
  } catch (err) {
    messagesEl.innerHTML = "";

    await appendAssistantMessage(
      "Could not load this conversation: " +
        err.message,
      [],
      [],
      true,
      false
    );
  }

  inputEl.value = "";
  autoResizeTextarea();
}

if (typeof mermaid !== "undefined") {
  mermaid.initialize({
    startOnLoad: false,
    theme: "default",
    securityLevel: "loose"
  });
}

function showEmptyState() {
  messagesEl.innerHTML =
    '<div class="empty-state">' +
    "<h2>Ask your database anything</h2>" +
    "<p>e.g. \"Show the top 5 products by revenue this quarter\" " +
    'or "Draw the ER diagram for this database".</p>' +
    "</div>";
}

function autoResizeTextarea() {
  inputEl.style.height = "auto";
  inputEl.style.height =
    Math.min(inputEl.scrollHeight, 160) + "px";
}

inputEl.addEventListener("input", autoResizeTextarea);

inputEl.addEventListener("keydown", function (e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

suggestionListEl.addEventListener("click", function (e) {
  const li = e.target.closest("li");

  if (!li) return;

  inputEl.value = li.textContent;
  autoResizeTextarea();
  inputEl.focus();
});

newChatBtn.addEventListener("click", async function () {
  if (sessionId) {
    try {
      await fetch(
        API_BASE +
          "/api/session/reset?session_id=" +
          encodeURIComponent(sessionId),
        {
          method: "POST"
        }
      );
    } catch (_) {}
  }

  sessionId = null;

  localStorage.removeItem("datachat_session_id");

  showEmptyState();

  inputEl.value = "";

  autoResizeTextarea();
});

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function el(tag, className, html) {
  const element = document.createElement(tag);

  if (className) {
    element.className = className;
  }

  if (html !== undefined) {
    element.innerHTML = html;
  }

  return element;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderMarkdownLite(text) {
  let safe = escapeHtml(text);

  safe = safe.replace(
    /\*\*(.+?)\*\*/g,
    "<strong>$1</strong>"
  );

  safe = safe.replace(
    /^- (.+)$/gm,
    "&bull; $1"
  );

  safe = safe.replace(/\n/g, "<br>");

  return safe;
}

let artifactCounter = 0;

function appendUserMessage(text, save) {
  if (save === undefined) {
    save = true;
  }

  if (messagesEl.querySelector(".empty-state")) {
    messagesEl.innerHTML = "";
  }

  const wrap = el("div", "msg user");

  wrap.appendChild(
    el("div", "msg-role", "You")
  );

  wrap.appendChild(
    el("div", "bubble", escapeHtml(text))
  );

  messagesEl.appendChild(wrap);

  if (save) {
    saveMessageToCurrentChat("user", text);
  }

  scrollToBottom();
}

function appendThinking() {
  if (messagesEl.querySelector(".empty-state")) {
    messagesEl.innerHTML = "";
  }

  const wrap = el("div", "msg assistant");

  wrap.id = "thinkingMsg";

  wrap.appendChild(
    el("div", "msg-role", "DataChat agent")
  );

  const bubble = el(
    "div",
    "bubble thinking",
    '<span class="pulse"></span> Querying &amp; analyzing…'
  );

  wrap.appendChild(bubble);

  messagesEl.appendChild(wrap);

  scrollToBottom();
}

function removeThinking() {
  const thinking = document.getElementById("thinkingMsg");

  if (thinking) {
    thinking.remove();
  }
}

function buildToolTrace(toolTrace) {
  if (!toolTrace || toolTrace.length === 0) {
    return null;
  }

  const container = el("div", "tool-trace");

  const bar = el(
    "div",
    "tool-trace-bar",
    '<span class="dots">' +
      "<span></span><span></span><span></span>" +
      "</span>" +
      '<span class="tool-trace-label">' +
      toolTrace.length +
      " tool call(s) — click to inspect (SQL, args, results)" +
      "</span>"
  );

  const body = el("div", "tool-trace-body");

  toolTrace.forEach(function (step) {
    const stepEl = el(
      "div",
      "tool-trace-step"
    );

    let resultPreview = "";

    try {
      resultPreview = JSON.stringify(
        step.result,
        null,
        2
      );
    } catch (_) {
      resultPreview = String(step.result);
    }

    if (
      resultPreview &&
      resultPreview.length > 800
    ) {
      resultPreview =
        resultPreview.substring(0, 800) +
        "\n… (truncated)";
    }

    stepEl.innerHTML =
      "<div>" +
      '<span class="fn">' +
      escapeHtml(step.tool) +
      "(</span>" +
      escapeHtml(JSON.stringify(step.args)) +
      '<span class="fn">)</span>' +
      "</div>" +
      "<pre>" +
      escapeHtml(resultPreview) +
      "</pre>";

    body.appendChild(stepEl);
  });

  container.appendChild(bar);
  container.appendChild(body);

  bar.addEventListener("click", function () {
    container.classList.toggle("open");
  });

  return container;
}

async function buildArtifactCard(artifact) {
  artifactCounter++;

  const card = el(
    "div",
    "artifact-card"
  );

  const title =
    artifact.title ||
    (
      artifact.artifact_type === "image"
        ? "Chart"
        : "Diagram"
    );

  const titleEl = el(
    "div",
    "artifact-card-title",
    "<span>" +
      escapeHtml(title) +
      "</span>" +
      "<span>" +
      escapeHtml(
        artifact.chart_type ||
          artifact.diagram_type ||
          ""
      ) +
      "</span>"
  );

  card.appendChild(titleEl);

  if (artifact.artifact_type === "image") {
    const img = document.createElement("img");

    img.src =
      "data:image/png;base64," +
      artifact.data_base64;

    img.alt = title;

    card.appendChild(img);
  }

  if (
    artifact.artifact_type === "mermaid" &&
    typeof mermaid !== "undefined"
  ) {
    const wrap = el(
      "div",
      "mermaid-wrap"
    );

    const graphId =
      "mermaid-" +
      Date.now() +
      "-" +
      artifactCounter;

    wrap.id = graphId;

    card.appendChild(wrap);

    try {
      const result = await mermaid.render(
        graphId + "-svg",
        artifact.mermaid_code
      );

      wrap.innerHTML = result.svg;
    } catch (err) {
      wrap.innerHTML =
        "<pre style=\"color:#c0392b;\">" +
        "Failed to render diagram:\n" +
        escapeHtml(String(err)) +
        "\n\nRaw definition:\n" +
        escapeHtml(artifact.mermaid_code) +
        "</pre>";
    }
  }

  return card;
}

async function appendAssistantMessage(
  reply,
  artifacts,
  toolTrace,
  isError,
  save
) {
  if (isError === undefined) {
    isError = false;
  }

  if (save === undefined) {
    save = true;
  }

  const wrap = el(
    "div",
    "msg assistant"
  );

  wrap.appendChild(
    el(
      "div",
      "msg-role",
      "DataChat agent"
    )
  );

  const bubble = el(
    "div",
    isError
      ? "bubble error-bubble"
      : "bubble",
    renderMarkdownLite(reply)
  );

  wrap.appendChild(bubble);

  const trace = buildToolTrace(toolTrace);

  if (trace) {
    wrap.appendChild(trace);
  }

  for (const artifact of artifacts || []) {
    const card =
      await buildArtifactCard(artifact);

    wrap.appendChild(card);
  }

  messagesEl.appendChild(wrap);

  if (save && !isError) {
    saveMessageToCurrentChat(
      "assistant",
      reply
    );
  }

  scrollToBottom();
}

async function sendMessage(message) {
  sendBtn.disabled = true;

  appendUserMessage(message);

  appendThinking();

  try {
    const res = await fetch(
      API_BASE + "/api/chat",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          session_id: sessionId,
          message: message
        })
      }
    );

    if (!res.ok) {
      const errBody =
        await res.json().catch(function () {
          return {};
        });

      throw new Error(
        errBody.detail ||
          "Request failed (" +
            res.status +
            ")"
      );
    }

    const data = await res.json();

    sessionId = data.session_id;

    localStorage.setItem(
      "datachat_session_id",
      sessionId
    );

    saveCurrentChat(message);

    removeThinking();

    await appendAssistantMessage(
      data.reply,
      data.artifacts || [],
      data.tool_trace || [],
      false,
      true
    );
  } catch (err) {
    removeThinking();

    await appendAssistantMessage(
      "Something went wrong talking to the backend: " +
        err.message,
      [],
      [],
      true,
      false
    );
  } finally {
    sendBtn.disabled = false;
  }
}

formEl.addEventListener("submit", function (e) {
  e.preventDefault();

  const text = inputEl.value.trim();

  if (!text) return;

  inputEl.value = "";

  autoResizeTextarea();

  sendMessage(text);
});

async function checkHealth() {
  try {
    const res = await fetch(
      API_BASE + "/api/health"
    );

    if (!res.ok) {
      throw new Error();
    }

    backendStatusEl.textContent =
      "connected";

    backendStatusEl.className =
      "status-dot status-ok";
  } catch (_) {
    backendStatusEl.textContent =
      "unreachable";

    backendStatusEl.className =
      "status-dot status-error";
  }
}

async function loadSchema() {
  try {
    const res = await fetch(
      API_BASE + "/api/schema"
    );

    if (!res.ok) {
      throw new Error();
    }

    const data = await res.json();

    schemaListEl.innerHTML = "";

    Object.entries(data.tables).forEach(
      function ([tableName, info]) {
        const tableEl = el(
          "div",
          "schema-table"
        );

        const head = el(
          "div",
          "schema-table-head",
          "<span>" +
            escapeHtml(tableName) +
            "</span>" +
            "<span>" +
            info.row_count +
            " rows</span>"
        );

        const cols = el(
          "div",
          "schema-table-cols",
          info.columns
            .map(function (c) {
              return (
                "<div>" +
                escapeHtml(c.name) +
                ' <span style="opacity:.6">' +
                escapeHtml(c.type || "") +
                "</span></div>"
              );
            })
            .join("")
        );

        head.addEventListener(
          "click",
          function () {
            tableEl.classList.toggle("open");
          }
        );

        tableEl.appendChild(head);
        tableEl.appendChild(cols);

        schemaListEl.appendChild(tableEl);
      }
    );
  } catch (_) {
    schemaListEl.textContent =
      "Could not load schema. Is the backend running?";
  }
}

showEmptyState();
checkHealth();
loadSchema();
renderChatHistory();