from agent import CourseAgent
from personas import list_persona_names


HELP_TEXT = """
命令：
  /help              查看帮助
  /status            查看模型、PDF、索引配置
  /persona            查看当前人格介绍
  /persona 名称       切换人格：Harry Potter / Hermione Granger / Severus Snape
  /rebuild-rag        重新读取 PDF 并构建向量索引
  /exit              退出

示例：
  这本选课小本本里有没有推荐的通识课？
  帮我比较一下高数和线代该怎么安排
  23 * (17 + 5) 等于多少？
""".strip()


def main() -> None:
    print("=== 人格化选课助手：Persona + Memory + Tools + PDF RAG ===")
    print(f"可选人格：{', '.join(list_persona_names())}")
    print("首次问到 PDF 内容时会自动构建索引，也可以先输入 /rebuild-rag。")
    print("输入 /help 查看命令。\n")

    try:
        agent = CourseAgent("Harry Potter")
    except Exception as exc:
        print(f"启动失败：{exc}")
        return

    while True:
        user_input = input("你：").strip()
        if not user_input:
            continue
        if user_input.lower() in {"/exit", "exit", "quit"}:
            print("Agent：再见，项目展示顺利。")
            break
        if user_input == "/help":
            print(HELP_TEXT)
            continue
        if user_input == "/status":
            print(agent.status())
            continue
        if user_input == "/persona":
            print(agent.describe_persona())
            continue
        if user_input == "/rebuild-rag":
            try:
                print(agent.rebuild_rag())
            except Exception as exc:
                print(f"重建失败：{exc}")
            continue
        if user_input.startswith("/persona "):
            print(agent.change_persona(user_input.split(maxsplit=1)[1].strip()))
            continue

        try:
            print(f"Agent：{agent.chat(user_input)}")
        except Exception as exc:
            print(f"Agent 调用失败：{exc}")


if __name__ == "__main__":
    main()
