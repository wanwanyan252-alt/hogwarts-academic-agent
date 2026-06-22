from __future__ import annotations

import base64
import html
import re
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from agent import CourseAgent
from personas import get_persona_profile, list_persona_names


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_VERSION = "persona-ui-stable-v3"
TECH_TAGS = ("DeepSeek", "LangChain", "FAISS", "BGE", "RAG", "Agent", "Multi-Persona")


def asset_path(*parts: str) -> Path:
    """按文件名大小写做一次兼容查找。"""
    direct = PROJECT_ROOT.joinpath(*parts)
    if direct.exists():
        return direct

    parent = PROJECT_ROOT.joinpath(*parts[:-1])
    target = parts[-1].lower()
    if parent.exists():
        for item in parent.iterdir():
            if item.name.lower() == target:
                return item
    return direct


PERSONA_UI = {
    "Harry Potter": {
        "title": "Harry Potter",
        "role": "成长型选课顾问",
        "motto": "勇敢并不意味着不害怕，而是在害怕时依然前进。",
        "badges": ("成长导向", "鼓励探索", "兴趣优先"),
        "status": (("成长指数", "92%"), ("探索倾向", "高")),
        "thinking": "⚡ Harry 正在规划你的成长路线...",
        "emotion": "⚡",
        "suggestions": (
            "我想选一门有挑战但有收获的课，怎么判断值不值得？",
            "我怕绩点受影响，但又想试试感兴趣的课，你怎么看？",
            "帮我在兴趣和课程压力之间做个取舍。",
        ),
        "avatar": asset_path("assets", "personas_cutout", "harry.png"),
        "background": asset_path("assets", "backgrouds", "Harry_bg.png"),
        "primary": "#a93a32",
        "secondary": "#df9f28",
    },
    "Hermione Granger": {
        "title": "Hermione Granger",
        "role": "理性分析顾问",
        "motto": "先查资料，再下结论。",
        "badges": ("证据优先", "信息导向", "理性分析"),
        "status": (("知识可信度", "A"), ("资料完整度", "较高")),
        "thinking": "📚 Hermione 正在查阅相关资料...",
        "emotion": "📚",
        "suggestions": (
            "帮我比较几门通识课的工作量、给分和学习价值。",
            "我想做一个稳妥的选课规划，应该先看哪些指标？",
            "如何判断一门课的评价是否信息充分？",
        ),
        "avatar": asset_path("assets", "personas_cutout", "hermione.png"),
        "background": asset_path("assets", "backgrouds", "Hermione_bg.png"),
        "primary": "#7b4b28",
        "secondary": "#c99255",
    },
    "Severus Snape": {
        "title": "Severus Snape",
        "role": "风险控制顾问",
        "motto": "情绪不能代替判断。",
        "badges": ("风险评估", "冷静判断", "避免踩雷"),
        "status": (("风险评估等级", "严格"), ("踩雷预警指数", "高敏")),
        "thinking": "⚗️ Snape 正在评估潜在风险...",
        "emotion": "⚗️",
        "suggestions": (
            "这门热门课到底是不是坑？帮我冷静判断一下。",
            "我这学期课表会不会太满，哪里最容易炸？",
            "怎么识别所谓水课评价里的样本偏差？",
        ),
        "avatar": asset_path("assets", "personas_cutout", "snape.png"),
        "background": asset_path("assets", "backgrouds", "Snape_bg.png"),
        "primary": "#173b2f",
        "secondary": "#5c3d78",
    },
}


TOOL_DESCRIPTIONS = {
    "calculator_tool": "计算学分、比例和简单数值。",
    "course_pdf_rag": "检索《选课小本本》课程评价。",
    "course_planner_tool": "生成选课路线和学习规划。",
    "schedule_analyzer_tool": "分析课表冲突与课程负担。",
}


WORKFLOW_STEPS = (
    ("理解用户问题", "识别课程、老师、课表或规划意图", "🧭"),
    ("知识库检索", "需要课程依据时调用 PDF RAG", "📚"),
    ("工具调用分析", "按场景选择规划、课表或计算工具", "🛠️"),
    ("生成最终建议", "结合人格风格给出可执行回答", "✓"),
)


def image_to_data_uri(path: Path) -> str:
    """把本地图片转为 data URI。"""
    if not path.exists():
        return ""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def get_agent() -> CourseAgent:
    return st.session_state.agent


def current_ui(agent: CourseAgent) -> dict[str, object]:
    return PERSONA_UI.get(agent.persona_name, PERSONA_UI["Harry Potter"])


def init_session_state() -> None:
    """初始化 Streamlit 会话状态。"""
    if "agent" not in st.session_state:
        with st.spinner("正在初始化 Agent..."):
            st.session_state.agent = CourseAgent()

    if st.session_state.get("frontend_version") != FRONTEND_VERSION:
        st.session_state.frontend_version = FRONTEND_VERSION
        st.session_state.sessions = {}
        st.session_state.session_order = []
        st.session_state.active_session_id = ""

    st.session_state.setdefault("sessions", {})
    st.session_state.setdefault("session_order", [])
    st.session_state.setdefault("active_session_id", "")
    st.session_state.setdefault("last_rebuild_result", "")

    if not st.session_state.session_order:
        create_session()
    prune_sessions()


def create_session() -> str:
    """创建一个仅保存在本次运行期间的会话。"""
    session_id = f"chat-{int(time.time() * 1000)}"
    persona = st.session_state.agent.persona_name if "agent" in st.session_state else "Harry Potter"
    st.session_state.sessions[session_id] = {
        "title": "新的选课咨询",
        "persona": persona,
        "messages": [],
        "created_at": time.time(),
    }
    st.session_state.session_order.insert(0, session_id)
    st.session_state.active_session_id = session_id
    return session_id


def prune_sessions(max_sessions: int = 10) -> None:
    """清理重复空会话，避免左侧历史无限堆积。"""
    seen: set[str] = set()
    cleaned_order = []
    for session_id in st.session_state.session_order:
        if session_id in seen or session_id not in st.session_state.sessions:
            continue
        seen.add(session_id)
        cleaned_order.append(session_id)

    empty_ids = [
        session_id
        for session_id in cleaned_order
        if not st.session_state.sessions[session_id].get("messages")
        and st.session_state.sessions[session_id].get("title") == "新的选课咨询"
    ]
    keep_empty = empty_ids[:1]
    for session_id in empty_ids[1:]:
        if session_id != st.session_state.active_session_id:
            st.session_state.sessions.pop(session_id, None)

    filtered = []
    for session_id in cleaned_order:
        if session_id not in st.session_state.sessions:
            continue
        if session_id in empty_ids and session_id not in keep_empty and session_id != st.session_state.active_session_id:
            continue
        filtered.append(session_id)

    st.session_state.session_order = filtered[:max_sessions]
    for session_id in list(st.session_state.sessions.keys()):
        if session_id not in st.session_state.session_order:
            st.session_state.sessions.pop(session_id, None)

    if st.session_state.active_session_id not in st.session_state.sessions:
        if st.session_state.session_order:
            st.session_state.active_session_id = st.session_state.session_order[0]
        else:
            create_session()


def active_session() -> dict:
    session_id = st.session_state.active_session_id
    if not session_id or session_id not in st.session_state.sessions:
        session_id = create_session()
    return st.session_state.sessions[session_id]


def active_messages() -> list[dict[str, str]]:
    return active_session()["messages"]


def update_session_title(prompt: str) -> None:
    session = active_session()
    if session["title"] == "新的选课咨询":
        title = prompt.strip().replace("\n", " ")
        session["title"] = title[:18] + ("..." if len(title) > 18 else "")


def knowledge_base_status(agent: CourseAgent) -> str:
    index_dir = agent.settings.index_dir
    if (index_dir / "index.faiss").exists() and (index_dir / "index.pkl").exists():
        return "已构建"
    return "未构建"


def extract_chunk_count(message: str) -> str | None:
    match = re.search(r"(\d+)", message)
    return match.group(1) if match else None


def inject_page_style(ui: dict[str, object]) -> None:
    """注入全局样式。"""
    bg_uri = image_to_data_uri(Path(ui["background"]))
    bg_css = f"url('{bg_uri}')" if bg_uri else "linear-gradient(135deg, #111, #222)"

    st.markdown(
        f"""
        <style>
        :root {{
            --persona-primary: {ui["primary"]};
            --persona-secondary: {ui["secondary"]};
        }}

        header[data-testid="stHeader"] {{ display: none; }}

        .stApp,
        [data-testid="stAppViewContainer"] {{
            background-image:
                linear-gradient(rgba(0,0,0,.45), rgba(0,0,0,.58)),
                {bg_css} !important;
            background-size: cover !important;
            background-position: center !important;
            background-attachment: fixed !important;
            color: #fff;
        }}

        .block-container {{
            max-width: 1480px;
            padding-top: 1.55rem;
            padding-bottom: 1rem;
        }}

        .hero-title {{
            color: #fff;
            font-size: 2.15rem;
            font-weight: 800;
            line-height: 1.15;
            margin: 0 0 .25rem;
            text-shadow: 0 10px 28px rgba(0,0,0,.45);
        }}

        .hero-subtitle {{
            color: rgba(255,255,255,.90);
            margin-bottom: .7rem;
            font-size: .95rem;
            text-shadow: 0 8px 22px rgba(0,0,0,.38);
        }}

        .tech-row {{
            display: flex;
            flex-wrap: wrap;
            gap: .45rem;
            margin-bottom: .85rem;
        }}

        .tag {{
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: .32rem .68rem;
            font-size: .75rem;
            font-weight: 700;
            color: #fff;
            background: linear-gradient(135deg, var(--persona-primary), var(--persona-secondary));
            border: 1px solid rgba(255,255,255,.18);
            box-shadow: 0 10px 24px rgba(0,0,0,.18);
        }}

        .section-title {{
            color: #fff;
            font-size: 1rem;
            font-weight: 760;
            margin: .62rem 0 .42rem;
            text-shadow: 0 8px 22px rgba(0,0,0,.34);
        }}

        div[data-testid="stSelectbox"] > div {{
            background: rgba(255,255,255,.92);
            border-radius: 14px;
        }}

        .stButton > button {{
            border: 0;
            color: #fff;
            background: linear-gradient(135deg, var(--persona-primary), var(--persona-secondary));
            border-radius: 999px;
            font-weight: 760;
            box-shadow: 0 10px 26px rgba(0,0,0,.18);
        }}

        div[data-testid="stChatInput"] textarea {{
            color: #111827;
            background: rgba(255,255,255,.98);
            border-color: var(--persona-secondary);
        }}

        .side-info-grid {{
            display: grid;
            grid-template-columns: minmax(180px, .75fr) minmax(620px, 2.2fr) minmax(220px, .9fr);
            gap: .75rem;
            margin-top: .35rem;
        }}

        .st-key-side_info_panel {{
            margin-top: -3.2rem;
        }}

        .side-info-card {{
            min-height: 112px;
            padding: .85rem;
            border: 1px solid rgba(255,255,255,.26);
            border-radius: 16px;
            background: rgba(255,255,255,.22);
            backdrop-filter: blur(14px);
            box-shadow: 0 16px 42px rgba(0,0,0,.18);
            color: #fff;
        }}

        .side-info-title {{
            font-size: .88rem;
            font-weight: 800;
            margin-bottom: .55rem;
            text-shadow: 0 8px 20px rgba(0,0,0,.32);
        }}

        .side-info-line {{
            font-size: .94rem;
            line-height: 1.75;
            color: rgba(255,255,255,.92);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .side-tool-list {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: .45rem .75rem;
        }}

        .side-tool {{
            display: inline-flex;
            max-width: 100%;
            border-radius: 999px;
            padding: .24rem .5rem;
            font-size: .72rem;
            font-weight: 760;
            color: #fff;
            background: linear-gradient(135deg, var(--persona-primary), var(--persona-secondary));
            margin-bottom: .18rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .side-tool-desc {{
            color: rgba(255,255,255,.84);
            font-size: .7rem;
            line-height: 1.35;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .footer-note {{
            color: rgba(255,255,255,.78);
            font-size: .8rem;
            margin-top: .85rem;
            text-shadow: 0 6px 16px rgba(0,0,0,.35);
        }}

        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    tags = "".join(f"<span class='tag'>{tag}</span>" for tag in TECH_TAGS)
    st.markdown(
        f"""
        <div class="hero-title">人格化 AI 选课助手</div>
        <div class="hero-subtitle">基于 DeepSeek、RAG 与多人格 Agent 的智能选课系统</div>
        <div class="tech-row">{tags}</div>
        """,
        unsafe_allow_html=True,
    )


def render_sessions(agent: CourseAgent) -> None:
    st.markdown("<div class='section-title'>会话历史</div>", unsafe_allow_html=True)
    if st.button("新建聊天", use_container_width=True):
        create_session()
        agent.history.clear()
        st.rerun()

    options = st.session_state.session_order
    labels = {
        session_id: (
            ("● " if session_id == st.session_state.active_session_id else "")
            + st.session_state.sessions[session_id]["title"]
        )
        for session_id in options
    }
    current_index = options.index(st.session_state.active_session_id) if st.session_state.active_session_id in options else 0
    selected = st.selectbox(
        "选择历史会话",
        options,
        index=current_index,
        format_func=lambda session_id: labels[session_id],
        label_visibility="collapsed",
    )
    if selected != st.session_state.active_session_id:
        st.session_state.active_session_id = selected
        session_persona = st.session_state.sessions[selected].get("persona", agent.persona_name)
        if session_persona != agent.persona_name:
            agent.change_persona(session_persona)
        else:
            agent.history.clear()
        st.rerun()


def render_character_card(agent: CourseAgent, ui: dict[str, object]) -> None:
    st.markdown("<div class='section-title'>人格档案</div>", unsafe_allow_html=True)
    persona_names = list_persona_names()
    current_index = persona_names.index(agent.persona_name) if agent.persona_name in persona_names else 0
    selected_persona = st.selectbox("切换人格", persona_names, index=current_index, label_visibility="collapsed")

    if selected_persona != agent.persona_name:
        agent.change_persona(selected_persona)
        active_session()["persona"] = selected_persona
        st.rerun()

    avatar_uri = image_to_data_uri(Path(ui["avatar"]))
    badges = "".join(f"<span class='badge'>{html.escape(badge)}</span>" for badge in ui["badges"])
    components.html(
        f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <style>
                body {{
                    margin: 0;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                    color: #fff;
                }}
                .card {{
                    cursor: pointer;
                    border-radius: 22px;
                    padding: 14px;
                    background: rgba(255,255,255,.28);
                    backdrop-filter: blur(12px);
                    border: 1px solid rgba(255,255,255,.30);
                    box-shadow: 0 18px 48px rgba(0,0,0,.22);
                    overflow: hidden;
                }}
                .stage {{
                    height: 188px;
                    display: flex;
                    align-items: end;
                    justify-content: center;
                    position: relative;
                    margin-bottom: 10px;
                }}
                .stage::after {{
                    content: "";
                    position: absolute;
                    bottom: 0;
                    width: 72%;
                    height: 24px;
                    border-radius: 50%;
                    background: radial-gradient(ellipse, {ui["secondary"]}, rgba(0,0,0,.1) 66%, transparent 72%);
                    opacity: .75;
                }}
                .avatar {{
                    position: relative;
                    z-index: 2;
                    width: 180px;
                    height: 184px;
                    background: url("{avatar_uri}") center bottom / contain no-repeat;
                    filter: drop-shadow(0 16px 15px rgba(0,0,0,.38));
                    transform-origin: center bottom;
                    animation: idle 3.5s ease-in-out infinite;
                }}
                .card.active .avatar {{ animation: react .65s ease both; }}
                .name {{
                    font-size: 19px;
                    font-weight: 800;
                    text-shadow: 0 8px 22px rgba(0,0,0,.36);
                    margin-bottom: 8px;
                }}
                .motto {{
                    color: rgba(255,255,255,.86);
                    font-size: 14px;
                    line-height: 1.5;
                    margin-bottom: 10px;
                }}
                .badge-row {{ display: flex; flex-wrap: wrap; gap: 7px; }}
                .badge {{
                    display: inline-flex;
                    border-radius: 999px;
                    padding: 5px 9px;
                    font-size: 12px;
                    font-weight: 800;
                    color: #fff;
                    background: linear-gradient(135deg, {ui["primary"]}, {ui["secondary"]});
                    border: 1px solid rgba(255,255,255,.18);
                    box-shadow: 0 8px 20px rgba(0,0,0,.18);
                }}
                @keyframes idle {{
                    0%, 100% {{ transform: translateY(0); }}
                    50% {{ transform: translateY(-5px); }}
                }}
                @keyframes react {{
                    0% {{ transform: translateY(0) scale(1); }}
                    35% {{ transform: translateY(-13px) scale(1.05); }}
                    100% {{ transform: translateY(0) scale(1); }}
                }}
            </style>
        </head>
        <body>
            <div id="card" class="card" onclick="react()">
                <div class="stage"><div class="avatar"></div></div>
                <div class="name">{html.escape(ui["title"])}</div>
                <div class="motto">{html.escape(ui["motto"])}</div>
                <div class="badge-row">{badges}</div>
            </div>
            <script>
                function react() {{
                    const card = document.getElementById("card");
                    card.classList.remove("active");
                    void card.offsetWidth;
                    card.classList.add("active");
                    setTimeout(() => card.classList.remove("active"), 700);
                }}
            </script>
        </body>
        </html>
        """,
        height=320,
        scrolling=False,
    )


def render_status_cards_html(ui: dict[str, object]) -> str:
    return "".join(
        f"<div class='persona-status-card'><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"
        for label, value in ui["status"]
    )


def render_message_html(role: str, content: str, ui: dict[str, object]) -> str:
    safe_content = html.escape(content)
    if role == "user":
        return f"""
        <div class="message-row user">
            <div class="bubble user">{safe_content}</div>
        </div>
        """
    return f"""
    <div class="message-row agent">
        <div class="chat-avatar"></div>
        <div class="agent-message">
            <div class="message-meta">{html.escape(ui["emotion"])} {html.escape(ui["title"])}</div>
            <div class="bubble agent">{safe_content}</div>
        </div>
    </div>
    """


def render_recommendations_html(ui: dict[str, object]) -> str:
    cards = "".join(
        f"""
        <div class="suggestion-card">
            <span>{idx}</span>
            <p>{html.escape(question)}</p>
        </div>
        """
        for idx, question in enumerate(ui["suggestions"], start=1)
    )
    return f"""
    <div class="empty-chat">
        <strong>可以从这些问题开始</strong>
        <small>这是示例问题，请在下方输入框中提问。</small>
        <div class="suggestion-grid">{cards}</div>
    </div>
    """


def render_workflow_html(status_text: str | None = None) -> str:
    if status_text:
        return f"""
        <div class="workflow thinking-status">
            <span>{html.escape(status_text)}</span>
            <i></i><i></i><i></i>
        </div>
        """

    steps = "".join(
        f"""
        <div class="workflow-step">
            <span>{html.escape(icon)}</span>
            <strong>{html.escape(title)}</strong>
            <p>{html.escape(desc)}</p>
        </div>
        """
        for title, desc, icon in WORKFLOW_STEPS
    )
    return f"""
    <details class="workflow">
        <summary>Agent 工作过程</summary>
        <div class="workflow-grid">{steps}</div>
    </details>
    """


def render_chat_panel(ui: dict[str, object], messages: list[dict[str, str]], workflow_status: str | None = None) -> None:
    avatar_uri = image_to_data_uri(Path(ui["avatar"]))
    avatar_css = f"url('{avatar_uri}')" if avatar_uri else "none"
    status = f"{ui['title']} | {ui['role']}"
    messages_html = (
        "".join(render_message_html(message["role"], message.get("content", ""), ui) for message in messages)
        if messages
        else render_recommendations_html(ui)
    )

    components.html(
        f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <style>
                :root {{
                    --persona-primary: {ui["primary"]};
                    --persona-secondary: {ui["secondary"]};
                    --avatar: {avatar_css};
                }}
                html, body {{
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                }}
                .chat-panel {{
                    height: 610px;
                    border-radius: 22px;
                    overflow: hidden;
                    border: 1px solid rgba(255,255,255,.26);
                    box-shadow: 0 24px 70px rgba(0,0,0,.24);
                    background: rgba(5, 15, 12, .62);
                    backdrop-filter: blur(16px);
                    box-sizing: border-box;
                }}
                .chat-content {{
                    height: 100%;
                    padding: 16px;
                    background: linear-gradient(135deg, rgba(255,255,255,.05), rgba(0,0,0,.18));
                    display: flex;
                    flex-direction: column;
                    box-sizing: border-box;
                }}
                .top-bar {{
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 12px;
                    margin-bottom: 12px;
                }}
                .status-pill,
                .persona-status-card {{
                    color: #fff;
                    border-radius: 999px;
                    border: 1px solid rgba(255,255,255,.20);
                    background: linear-gradient(135deg, var(--persona-primary), var(--persona-secondary));
                    box-shadow: 0 14px 34px rgba(0,0,0,.22);
                    font-weight: 760;
                }}
                .status-pill {{ padding: 8px 16px; }}
                .persona-status-row {{
                    display: flex;
                    gap: 8px;
                    flex-wrap: wrap;
                    justify-content: flex-end;
                }}
                .persona-status-card {{ padding: 6px 10px; }}
                .persona-status-card span {{
                    opacity: .78;
                    margin-right: 6px;
                    font-size: 12px;
                }}
                .persona-status-card strong {{ font-size: 13px; }}
                .chat-scroll {{
                    flex: 1 1 auto;
                    min-height: 0;
                    overflow-y: auto;
                    overflow-x: hidden;
                    padding: 2px 10px 10px 0;
                }}
                .chat-scroll::-webkit-scrollbar {{ width: 8px; }}
                .chat-scroll::-webkit-scrollbar-thumb {{
                    background: rgba(255,255,255,.42);
                    border-radius: 999px;
                }}
                .message-row {{
                    display: flex;
                    gap: 10px;
                    margin: 13px 0;
                    align-items: flex-start;
                }}
                .message-row.user {{ justify-content: flex-end; }}
                .message-row.agent {{ justify-content: flex-start; }}
                .chat-avatar {{
                    width: 40px;
                    height: 40px;
                    flex: 0 0 40px;
                    border-radius: 50%;
                    background: var(--avatar) center / contain no-repeat, rgba(255,255,255,.84);
                    border: 1px solid rgba(255,255,255,.42);
                    box-shadow: 0 8px 18px rgba(0,0,0,.24);
                }}
                .agent-message {{ max-width: min(760px, 80%); }}
                .message-meta {{
                    color: rgba(255,255,255,.90);
                    font-size: 12px;
                    font-weight: 700;
                    margin: 0 0 5px 4px;
                    text-shadow: 0 8px 20px rgba(0,0,0,.35);
                }}
                .bubble {{
                    border-radius: 16px;
                    padding: 12px 15px;
                    line-height: 1.62;
                    white-space: pre-wrap;
                    overflow-wrap: anywhere;
                    box-shadow: 0 12px 28px rgba(0,0,0,.18);
                    font-size: 15px;
                    box-sizing: border-box;
                }}
                .bubble.agent {{
                    color: #1c1c1c;
                    background: #fffdf8;
                    border-top-left-radius: 6px;
                }}
                .bubble.user {{
                    max-width: min(720px, 78%);
                    color: #fff;
                    background: linear-gradient(135deg, var(--persona-primary), var(--persona-secondary));
                    border-top-right-radius: 6px;
                }}
                .empty-chat {{
                    min-height: 390px;
                    display: grid;
                    place-items: center;
                    color: rgba(255,255,255,.94);
                    text-align: center;
                }}
                .empty-chat strong {{
                    display: block;
                    font-size: 22px;
                    margin-bottom: 6px;
                    text-shadow: 0 10px 26px rgba(0,0,0,.38);
                }}
                .empty-chat small {{
                    display: block;
                    margin-bottom: 16px;
                    color: rgba(255,255,255,.78);
                    font-size: 13px;
                }}
                .suggestion-grid {{
                    display: grid;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                    gap: 12px;
                    width: min(860px, 100%);
                }}
                .suggestion-card {{
                    text-align: left;
                    border-radius: 16px;
                    padding: 14px;
                    color: #fff;
                    border: 1px solid rgba(255,255,255,.22);
                    background: rgba(255,255,255,.12);
                    box-shadow: 0 16px 40px rgba(0,0,0,.18);
                }}
                .suggestion-card span {{
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    width: 24px;
                    height: 24px;
                    margin-bottom: 10px;
                    border-radius: 999px;
                    background: linear-gradient(135deg, var(--persona-primary), var(--persona-secondary));
                    font-weight: 800;
                }}
                .suggestion-card p {{
                    margin: 0;
                    line-height: 1.5;
                    font-size: 14px;
                }}
                .workflow {{
                    color: rgba(255,255,255,.92);
                    border-top: 1px solid rgba(255,255,255,.18);
                    padding-top: 10px;
                    font-size: 13px;
                }}
                .thinking-status {{
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    font-weight: 760;
                }}
                .thinking-status span {{
                    padding: 6px 12px;
                    border-radius: 999px;
                    background: linear-gradient(135deg, var(--persona-primary), var(--persona-secondary));
                    box-shadow: 0 10px 24px rgba(0,0,0,.18);
                }}
                .thinking-status i {{
                    width: 6px;
                    height: 6px;
                    border-radius: 50%;
                    background: var(--persona-secondary);
                    animation: dotPulse 1.1s ease-in-out infinite;
                }}
                .thinking-status i:nth-child(3) {{ animation-delay: .16s; }}
                .thinking-status i:nth-child(4) {{ animation-delay: .32s; }}
                @keyframes dotPulse {{
                    0%, 80%, 100% {{ transform: translateY(0); opacity: .35; }}
                    40% {{ transform: translateY(-5px); opacity: 1; }}
                }}
                .workflow summary {{
                    cursor: pointer;
                    font-weight: 760;
                    margin-bottom: 8px;
                }}
                .workflow-grid {{
                    display: grid;
                    grid-template-columns: repeat(4, minmax(0, 1fr));
                    gap: 8px;
                }}
                .workflow-step {{
                    border-radius: 14px;
                    padding: 10px;
                    background: rgba(255,255,255,.10);
                    border: 1px solid rgba(255,255,255,.18);
                }}
                .workflow-step strong {{
                    display: block;
                    color: #fff;
                    margin-bottom: 4px;
                }}
                .workflow-step p {{
                    margin: 0;
                    font-size: 12px;
                    line-height: 1.45;
                    opacity: .82;
                }}
            </style>
        </head>
        <body>
            <div class="chat-panel">
                <div class="chat-content">
                    <div class="top-bar">
                        <div class="status-pill">{html.escape(status)}</div>
                        <div class="persona-status-row">{render_status_cards_html(ui)}</div>
                    </div>
                    <div id="chat-scroll" class="chat-scroll">{messages_html}</div>
                    {render_workflow_html(workflow_status)}
                </div>
            </div>
            <script>
                const chat = document.getElementById("chat-scroll");
                if (chat) {{ chat.scrollTop = chat.scrollHeight; }}
            </script>
        </body>
        </html>
        """,
        height=610,
        scrolling=False,
    )


def render_side_info(agent: CourseAgent) -> None:
    profile = get_persona_profile(agent.persona_name)
    tool_cards = "".join(
        f"""
        <div>
            <span class="side-tool" title="{html.escape(name)}">{html.escape(name)}</span>
            <div class="side-tool-desc">{html.escape(TOOL_DESCRIPTIONS.get(name, "可由 Agent 按需调用。"))}</div>
        </div>
        """
        for name in agent.tool_registry.tools.keys()
    )

    action_col, _ = st.columns([0.24, 0.76])
    with action_col:
        if st.button("重建知识库", use_container_width=True):
            with st.spinner("正在重建知识库索引，这可能需要一点时间..."):
                result = agent.rebuild_rag()
            st.session_state.last_rebuild_result = result
            chunk_count = extract_chunk_count(result)
            st.success("知识库重建完成")
            if chunk_count:
                st.info(f"本次生成文本切分块：{chunk_count}")

    st.markdown(
        f"""
        <div class="side-info-grid">
            <div class="side-info-card">
                <div class="side-info-title">系统状态</div>
                <div class="side-info-line" title="{html.escape(agent.settings.chat_model)}">模型：{html.escape(agent.settings.chat_model)}</div>
                <div class="side-info-line">人格：{html.escape(profile.short_name)}</div>
                <div class="side-info-line">工具：{len(agent.tool_registry.tools)}</div>
            </div>
            <div class="side-info-card">
                <div class="side-info-title">工具能力</div>
                <div class="side-tool-list">{tool_cards}</div>
            </div>
            <div class="side-info-card">
                <div class="side-info-title">知识库</div>
                <div class="side-info-line">来源：选课小本本 PDF</div>
                <div class="side-info-line">索引：FAISS 本地</div>
                <div class="side-info-line">状态：{knowledge_base_status(agent)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.last_rebuild_result:
        st.caption(st.session_state.last_rebuild_result)


def render_footer() -> None:
    st.markdown(
        """
        <div class="footer-note">
            人格化 AI 选课助手：课程项目展示版本。整体架构包含 DeepSeek 对话模型、本地 BGE Embedding、
            FAISS 向量库、PDF RAG 知识库、多工具 Agent 与多人格系统。
        </div>
        """,
        unsafe_allow_html=True,
    )


def append_agent_answer(agent: CourseAgent, prompt: str) -> None:
    messages = active_messages()
    messages.append({"role": "user", "content": prompt})
    update_session_title(prompt)
    try:
        answer = agent.chat(prompt)
    except Exception as exc:
        answer = f"调用 Agent 时出现错误：{exc}"
    messages.append({"role": "assistant", "content": answer})


def main() -> None:
    st.set_page_config(page_title="人格化 AI 选课助手", layout="wide")
    init_session_state()
    agent = get_agent()
    ui = current_ui(agent)
    inject_page_style(ui)

    render_header()

    left_col, right_col = st.columns([0.28, 0.72], gap="large")
    with left_col:
        render_sessions(agent)
        render_character_card(agent, ui)

    with right_col:
        chat_slot = st.empty()
        with chat_slot.container():
            render_chat_panel(ui, active_messages())

        prompt = st.chat_input("询问课程评价、选课规划、课表压力或具体老师...")
        if prompt:
            prompt = prompt.strip()
            if prompt:
                pending_messages = active_messages() + [{"role": "user", "content": prompt}]
                with chat_slot.container():
                    render_chat_panel(ui, pending_messages, workflow_status=ui["thinking"])
                append_agent_answer(agent, prompt)
                with chat_slot.container():
                    render_chat_panel(ui, active_messages())

    with st.container(key="side_info_panel"):
        render_side_info(agent)
    render_footer()


if __name__ == "__main__":
    main()
