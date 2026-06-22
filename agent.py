from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from personas import PERSONAS, get_persona_profile, list_persona_names, resolve_persona_name
from prompt import build_system_prompt
from rag import PdfRagStore
from tools import ToolRegistry, build_tool_registry


class CourseAgent:
    def __init__(self, persona_name: str = "Harry Potter", temperature: float = 0.3):
        self.settings = get_settings()
        resolved_name = resolve_persona_name(persona_name)
        self.persona_name = resolved_name if resolved_name in PERSONAS else "Harry Potter"
        self.temperature = temperature
        self.rag = PdfRagStore(self.settings)
        self.history = []
        self.max_history_messages = 8
        self._build_agent()

    def _make_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.settings.chat_model,
            temperature=self.temperature,
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
        )

    def _build_agent(self) -> None:
        self.tool_registry: ToolRegistry = build_tool_registry(self.rag.search)
        self.llm = self._make_llm()
        self.llm_with_tools = self.llm.bind_tools(self.tool_registry.as_list())

    def _base_messages(self, message: str):
        system = SystemMessage(content=build_system_prompt(self.persona_name))
        recent_history = self.history[-self.max_history_messages :]
        return [system, *recent_history, HumanMessage(content=message)]

    def chat(self, message: str) -> str:
        messages = self._base_messages(message)
        ai_message = self.llm_with_tools.invoke(messages)
        messages.append(ai_message)

        if getattr(ai_message, "tool_calls", None):
            for tool_call in ai_message.tool_calls:
                messages.append(self._run_tool_call(tool_call))
            ai_message = self.llm.invoke(messages)

        answer = ai_message.content if isinstance(ai_message, AIMessage) else str(ai_message)
        answer = self._ensure_persona_signature(answer)
        self._save_history(message, answer)
        return answer

    def _run_tool_call(self, tool_call) -> ToolMessage:
        tool_name = tool_call["name"]
        selected_tool = self.tool_registry.get(tool_name)
        if selected_tool is None:
            tool_output = f"未知工具：{tool_name}"
        else:
            try:
                tool_output = selected_tool.invoke(tool_call["args"])
            except Exception as exc:
                tool_output = f"工具 {tool_name} 调用失败：{exc}"
        return ToolMessage(content=str(tool_output), tool_call_id=tool_call["id"])

    def _save_history(self, user_message: str, answer: str) -> None:
        self.history.append(HumanMessage(content=user_message))
        self.history.append(AIMessage(content=answer))
        self.history = self.history[-self.max_history_messages :]

    def _ensure_persona_signature(self, answer: str) -> str:
        """保证模型回答末尾带有人格签名，便于展示不同人格效果。"""
        signature = get_persona_profile(self.persona_name).signature
        if signature in answer:
            return answer
        return f"{answer.rstrip()}\n\n{signature}"

    def change_persona(self, persona_name: str) -> str:
        resolved_name = resolve_persona_name(persona_name)
        if resolved_name not in PERSONAS:
            return f"可选人格：{', '.join(list_persona_names())}"
        self.persona_name = resolved_name
        self.history.clear()
        return f"已切换人格：{get_persona_profile(self.persona_name).display_name}"

    def describe_persona(self) -> str:
        """返回当前人格的展示说明，供 /persona 命令使用。"""
        return get_persona_profile(self.persona_name).describe()

    def rebuild_rag(self) -> str:
        count = self.rag.build()
        return f"RAG 索引已重建，共切分 {count} 个文本片段。"

    def status(self) -> str:
        return (
            f"人格：{get_persona_profile(self.persona_name).display_name}\n"
            f"聊天模型：{self.settings.chat_model}\n"
            f"聊天服务：DeepSeek ({self.settings.deepseek_base_url})\n"
            f"Embedding：{self.settings.embedding_model}\n"
            f"PDF：{self.settings.pdf_path}\n"
            f"索引目录：{self.settings.index_dir}\n"
            f"工具：{', '.join(self.tool_registry.tools.keys())}"
        )
