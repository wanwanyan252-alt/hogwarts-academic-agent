from __future__ import annotations

import ast
import json
import operator
import re
from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.tools import BaseTool, tool


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


@dataclass(frozen=True)
class ToolRegistry:
    """集中管理工具对象，方便后续继续扩展选课助手能力。"""

    tools: dict[str, BaseTool]

    def as_list(self) -> list[BaseTool]:
        return list(self.tools.values())

    def get(self, name: str) -> BaseTool | None:
        return self.tools.get(name)


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("只支持数字和基础四则运算表达式")


def calculator(expression: str) -> str:
    """安全计算基础数学表达式。"""
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval_node(tree))
    except Exception as exc:
        return f"计算失败：{exc}"


def course_planner(request: str) -> str:
    """根据学生目标和偏好生成初步课程规划建议。"""
    data = _parse_json_or_text(request)
    text = request if isinstance(data, str) else json.dumps(data, ensure_ascii=False)

    interests = _pick(data, "interests", "兴趣方向", default="暂未明确")
    career = _pick(data, "career_goal", "职业规划", default="暂未明确")
    goals = _pick(data, "training_goal", "培养目标", default="能力均衡发展")
    preferences = _pick(data, "preferences", "选课偏好", default="负担适中")

    direction = _infer_direction(text)
    workload = _infer_workload(text)

    suggestions = [
        "课程规划建议：",
        f"- 兴趣方向：{interests}",
        f"- 职业规划：{career}",
        f"- 培养目标：{goals}",
        f"- 选课偏好：{preferences}",
        f"- 推荐路线：{direction}",
        f"- 负担控制：{workload}",
        "- 执行顺序：先补齐基础课和先修要求，再选择方向课，最后用项目课或实践课验证兴趣。",
        "- 风险提示：如果目标课程依赖较强，建议不要在同一学期堆叠过多高强度理论课。",
    ]
    return "\n".join(suggestions)


def schedule_analyzer(schedule_text: str) -> str:
    """分析课表文本中的时间冲突、负担和学分分布。"""
    courses = _extract_courses(schedule_text)
    conflicts = _find_time_conflicts(courses)
    total_credits = sum(course["credits"] for course in courses)
    heavy_days = _count_day_load(courses)

    lines = [
        "课表分析结果：",
        f"- 识别课程数：{len(courses)}",
        f"- 估算总学分：{total_credits if total_credits else '未识别到学分信息'}",
    ]

    if conflicts:
        lines.append("- 时间冲突：发现以下可能冲突")
        lines.extend(f"  - {item}" for item in conflicts)
    else:
        lines.append("- 时间冲突：未发现明显冲突；如果输入未包含星期和节次，建议补充完整课表。")

    if heavy_days:
        busiest = max(heavy_days.items(), key=lambda item: item[1])
        lines.append(f"- 集中程度：{busiest[0]} 课程最集中，识别到 {busiest[1]} 个时间段。")
    else:
        lines.append("- 集中程度：暂无法判断，需要包含星期和节次。")

    if total_credits >= 26:
        lines.append("- 负担评估：学分偏高，建议减少一门高强度课程或实践课。")
    elif total_credits >= 20:
        lines.append("- 负担评估：负担中等偏高，需要关注作业量和考试周压力。")
    elif total_credits > 0:
        lines.append("- 负担评估：学分负担较稳，但仍需结合课程难度判断。")
    else:
        lines.append("- 负担评估：缺少学分信息，无法可靠评估总负担。")

    lines.append("- 建议：补充课程名称、星期、节次、学分和课程类型后，可以得到更准确的分析。")
    return "\n".join(lines)


def build_tool_registry(rag_search: Callable[[str], str]) -> ToolRegistry:
    """构建当前 Agent 可用工具集合。"""

    @tool
    def calculator_tool(expression: str) -> str:
        """计算数学表达式。输入应是纯数学表达式，例如：(3 + 5) * 2。"""
        return calculator(expression)

    @tool
    def course_pdf_rag(query: str) -> str:
        """检索外部 PDF 知识库《选课小本本 2024-2025学年秋季刊》。"""
        return rag_search(query)

    @tool
    def course_planner_tool(request: str) -> str:
        """根据兴趣方向、职业规划、培养目标和选课偏好生成课程建议与学习路线。"""
        return course_planner(request)

    @tool
    def schedule_analyzer_tool(schedule_text: str) -> str:
        """分析用户输入的课表，评估时间冲突、课程负担、学分分布和课程集中程度。"""
        return schedule_analyzer(schedule_text)

    tools = {
        "calculator_tool": calculator_tool,
        "course_pdf_rag": course_pdf_rag,
        "course_planner_tool": course_planner_tool,
        "schedule_analyzer_tool": schedule_analyzer_tool,
    }
    return ToolRegistry(tools=tools)


def _parse_json_or_text(value: str) -> dict[str, Any] | str:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else value
    except json.JSONDecodeError:
        return value


def _pick(data: dict[str, Any] | str, english_key: str, chinese_key: str, default: str) -> str:
    if not isinstance(data, dict):
        return default
    value = data.get(english_key, data.get(chinese_key, default))
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def _infer_direction(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("ai", "人工智能", "机器学习", "深度学习")):
        return "数学基础与编程基础 -> 数据结构/算法 -> 机器学习/人工智能方向课 -> 项目实践"
    if any(word in lowered for word in ("后端", "开发", "工程", "软件")):
        return "程序设计 -> 数据结构 -> 数据库/操作系统/计算机网络 -> 软件工程实践"
    if any(word in lowered for word in ("数据", "分析", "可视化", "商业")):
        return "统计基础 -> 数据库 -> 数据分析/可视化 -> 行业项目或竞赛实践"
    return "通识与专业基础 -> 核心专业课 -> 方向选修课 -> 实践项目"


def _infer_workload(text: str) -> str:
    if any(word in text for word in ("轻松", "保绩点", "压力小", "少作业")):
        return "建议每学期控制高强度课程数量，优先选择评价稳定且先修关系清晰的课程。"
    if any(word in text for word in ("挑战", "多学", "冲刺", "科研")):
        return "可以适度增加方向课，但应保留项目、复习和自学时间。"
    return "建议采用中等负担，避免同一学期集中安排多门考试压力大的课程。"


def _extract_courses(schedule_text: str) -> list[dict[str, Any]]:
    courses = []
    for line in schedule_text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        credits = _extract_credits(clean)
        slots = _extract_time_slots(clean)
        courses.append({"name": clean, "credits": credits, "slots": slots})
    if not courses and schedule_text.strip():
        courses.append({"name": schedule_text.strip(), "credits": _extract_credits(schedule_text), "slots": _extract_time_slots(schedule_text)})
    return courses


def _extract_credits(text: str) -> int:
    match = re.search(r"(\d+)\s*学分", text)
    return int(match.group(1)) if match else 0


def _extract_time_slots(text: str) -> list[str]:
    day_pattern = r"(周[一二三四五六日天]|星期[一二三四五六日天])"
    section_pattern = r"第?\s*(\d{1,2})(?:[-到至~](\d{1,2}))?\s*节"
    day_match = re.search(day_pattern, text)
    section_match = re.search(section_pattern, text)
    if not day_match or not section_match:
        return []
    day = day_match.group(1)
    start = int(section_match.group(1))
    end = int(section_match.group(2) or start)
    return [f"{day}-{section}" for section in range(start, end + 1)]


def _find_time_conflicts(courses: list[dict[str, Any]]) -> list[str]:
    occupied: dict[str, str] = {}
    conflicts = []
    for course in courses:
        for slot in course["slots"]:
            if slot in occupied:
                conflicts.append(f"{course['name']} 与 {occupied[slot]} 在 {slot} 冲突")
            else:
                occupied[slot] = course["name"]
    return conflicts


def _count_day_load(courses: list[dict[str, Any]]) -> dict[str, int]:
    day_load: dict[str, int] = {}
    for course in courses:
        for slot in course["slots"]:
            day = slot.split("-")[0]
            day_load[day] = day_load.get(day, 0) + 1
    return day_load
