# 人格化 AI 选课助手
![Uploading image.png…]()

这是一个课程项目展示版 AI Agent 系统。项目目前已经完成第一版：支持 DeepSeek 对话模型、本地 BGE Embedding、FAISS 向量检索、PDF RAG 知识库、多工具调用、三人格对话系统，并提供 CLI 与 Streamlit 前端两个入口。

项目目标不是做一个普通聊天机器人，而是做一个“人格化选课助手”：同一个选课问题，在 Harry Potter、Hermione Granger、Severus Snape 三种人格下会呈现不同的表达风格、判断倾向和咨询体验。

## 当前能力

- DeepSeek 对话模型：聊天模型统一使用 DeepSeek。
- 本地 Embedding：使用 `BAAI/bge-small-zh-v1.5`，不需要额外 Embedding API Key。
- PDF RAG 知识库：基于《选课小本本》构建课程评价检索能力。
- FAISS 向量库：本地保存和加载向量索引。
- 多工具 Agent：支持课程知识库检索、课程规划、课表分析和计算器工具。
- 多人格系统：支持 Harry、Hermione、Snape 三种人格切换。
- 对话记忆：保留多轮上下文，让咨询过程更连续。
- Streamlit 前端：提供像素角色、人格切换、会话历史、聊天窗口和知识库管理。
- CLI 入口：保留命令行版本，便于调试和课堂演示。

## 人格设定

### Harry Potter

真诚、同伴感强，更关注兴趣、成长和尝试价值。回答自然，不说教，适合用户犹豫、纠结、缺少信心时咨询。

### Hermione Granger

优等生风格，信息掌握充分，重视证据、结构和学术收益。适合比较课程、规划学习路线、分析评价可信度。

### Severus Snape

毒舌、挑剔、风险意识强，会直接指出选课幻想、热门评价偏差和潜在代价。适合避坑、判断课程风险、分析给分波动。

## 工具能力

- `course_pdf_rag`：检索《选课小本本》中的课程评价和相关信息。
- `course_planner_tool`：根据兴趣方向、职业规划、培养目标和偏好生成选课路线。
- `schedule_analyzer_tool`：分析课表冲突、课程负担、学分分布和课程集中程度。
- `calculator_tool`：处理简单数学计算。

## 技术栈

- Python
- DeepSeek API
- LangChain
- FAISS
- HuggingFace Embeddings
- BAAI/bge-small-zh-v1.5
- PyMuPDFLoader
- Streamlit

## 环境准备

进入项目目录：

```powershell
cd D:\CODE\Agent-Demo
```

创建虚拟环境：

```powershell
python -m venv .venv
```

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

复制环境变量文件：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，至少填写：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
```

常用配置示例：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
LOCAL_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_PDF_PATH=你的选课小本本 PDF 路径
RAG_INDEX_DIR=data\faiss_index
```

说明：Embedding 使用本地 BGE 模型，不需要配置第二个 API Key。首次构建知识库时会下载模型到本地缓存，之后可复用。

## 启动方式

### Streamlit 前端

推荐用于展示：

```powershell
.\.venv\Scripts\streamlit.exe run frontend.py
```

也可以使用：

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend.py
```

### CLI 命令行

用于调试：

```powershell
.\.venv\Scripts\python.exe main.py
```

CLI 常用命令：

```text
/help          查看帮助
/status        查看当前配置和工具状态
/persona       查看当前人格
/persona Harry Potter
/persona Hermione Granger
/persona Severus Snape
/rebuild-rag   重建知识库索引
/exit          退出
```

## RAG 知识库说明

当前 RAG 流程：

```text
PDF -> PyMuPDFLoader -> 文本清洗 -> 文本切块 -> BGE Embedding -> FAISS -> Agent 工具调用
```

项目曾测试过 `PyPDFLoader`，但它对《选课小本本》部分页面会提取出乱码。因此第一版正式使用 `PyMuPDFLoader`。

`rag.py` 中已经加入文本清洗逻辑，用于减少重复页眉、页脚、水印、页码和异常短行对向量库的污染。

如果需要重新生成向量库，可以在前端点击“重建知识库”，或在 CLI 中输入：

```text
/rebuild-rag
```

## 调试 PDF 文本

项目提供 `debug_pdf.py`，用于直接查看 PDF 原始文本提取结果，不经过切块、Embedding、FAISS 或 Agent。

默认查看测试页：

```powershell
.\.venv\Scripts\python.exe debug_pdf.py
```

查看指定页：

```powershell
.\.venv\Scripts\python.exe debug_pdf.py 77
```

## 项目结构

```text
Agent-Demo/
├── agent.py          # CourseAgent 主流程，负责模型调用、工具调用、记忆和人格切换
├── config.py         # 配置读取，统一从 .env 加载 DeepSeek、PDF 和索引路径
├── debug_pdf.py      # PDF 原始文本提取调试脚本
├── frontend.py       # Streamlit 前端入口
├── main.py           # CLI 命令行入口
├── personas.py       # 三人格结构化配置和风格规则
├── prompt.py         # Prompt 构造逻辑
├── rag.py            # PDF RAG、文本清洗、BGE Embedding 和 FAISS 索引
├── tools.py          # Agent 工具定义
├── requirements.txt  # Python 依赖
├── assets/           # 前端角色和背景资源
└── data/faiss_index/ # 本地 FAISS 索引目录
```

## 第一版状态

第一版已经完成：

- 课程 Agent 基础闭环；
- DeepSeek 聊天模型接入；
- 本地 BGE Embedding；
- PDF RAG 知识库；
- FAISS 本地向量索引；
- 多工具调用；
- Harry、Hermione、Snape 三人格；
- CLI 和 Streamlit 双入口；
- 前端像素角色展示、人格切换、会话历史和知识库重建。

## 后续可扩展方向

- 增加真实工具调用 Trace 展示；
- 优化 Streamlit 前端的响应式布局；
- 引入更多课程数据格式，例如 Markdown、CSV 或 DOCX；
- 为每个人格增加更细的表情、动作和视觉状态；
- 加入课程收藏、选课方案保存和多会话持久化；
- 优化 RAG 的检索评估和引用展示。

## 注意事项

- 不要提交 `.env`，其中包含 API Key。
- `data/faiss_index` 是本地向量索引，可删除后重新构建。
- 如果更换 PDF 或清洗逻辑，建议重新执行知识库构建。
- 首次运行本地 Embedding 可能较慢，属于正常现象。
# hogwarts-academic-agent
# hogwarts-academic-agent
