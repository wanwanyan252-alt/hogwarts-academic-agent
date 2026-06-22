from __future__ import annotations

import random
import re
import pickle
from pathlib import Path

from langchain_core.documents import Document
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import Settings


HEADER_FOOTER_PATTERNS = (
    "选课小本本项目组出品",
    "选课小本本项目组出",
    "选课小本本项目",
    "选课小本本项",
    "小本本项目组出品",
    "小本本项目组",
    "项目组出品",
    "组出品",
    "出品",
    "选课",
)
DEBUG_SAMPLE_PAGES = 4
DEBUG_SAMPLE_CHARS = 500
KEYWORD_INDEX_FILE = "keyword_index.pkl"
VECTOR_CANDIDATES = 12
KEYWORD_CANDIDATES = 12


def _make_embeddings(settings: Settings) -> HuggingFaceEmbeddings:
    """创建本地中文向量模型，不再依赖在线 Embedding API。"""
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


class PdfRagStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embeddings: HuggingFaceEmbeddings | None = None
        self.vectorstore: FAISS | None = None
        self.keyword_documents: list[Document] = []

    def _get_embeddings(self) -> HuggingFaceEmbeddings:
        """延迟加载本地向量模型，避免程序启动时就下载或初始化模型。"""
        if self.embeddings is None:
            self.embeddings = _make_embeddings(self.settings)
        return self.embeddings

    def build(self) -> int:
        pdf_path = self.settings.pdf_path
        if not pdf_path.exists():
            raise FileNotFoundError(f"找不到 RAG PDF：{pdf_path}")

        loader = PyMuPDFLoader(str(pdf_path))
        documents = loader.load()
        cleaned_documents = self._clean_documents(documents)
        self._print_cleaning_debug(documents, cleaned_documents)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=900,
            chunk_overlap=150,
            separators=["\n\n", "\n", "。", "！", "？", ".", " ", ""],
        )
        raw_chunks = splitter.split_documents(documents)
        chunks = splitter.split_documents(cleaned_documents)
        self._print_chunk_debug(raw_chunks, chunks)

        self.settings.index_dir.mkdir(parents=True, exist_ok=True)
        self.vectorstore = FAISS.from_documents(chunks, self._get_embeddings())
        self.vectorstore.save_local(str(self.settings.index_dir))
        self._save_keyword_index(chunks)
        return len(chunks)

    def clean_text(self, text: str) -> str:
        """清洗 PDF 页文本，减少页眉页脚、水印和异常换行对向量库的污染。"""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = self._merge_single_char_lines(text)

        cleaned_lines = []
        previous_line = ""
        repeat_count = 0

        for raw_line in text.splitlines():
            line = _normalize_spaces(raw_line)
            if not line:
                continue
            if _is_table_of_contents_line(line):
                continue
            if _is_header_or_footer(line):
                continue
            if _is_page_number(line):
                continue
            if _is_noise_short_line(line):
                continue

            if line == previous_line:
                repeat_count += 1
                if repeat_count >= 2:
                    continue
            else:
                previous_line = line
                repeat_count = 0

            cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines).strip()
        if _looks_like_table_of_contents(cleaned_text):
            return ""
        return cleaned_text

    def _clean_documents(self, documents: list[Document]) -> list[Document]:
        cleaned_documents = []
        for document in documents:
            cleaned_text = self.clean_text(document.page_content or "")
            if not cleaned_text:
                continue
            cleaned_documents.append(
                Document(page_content=cleaned_text, metadata=dict(document.metadata))
            )
        return cleaned_documents

    def _merge_single_char_lines(self, text: str) -> str:
        """合并连续单字换行，修复 PDF 抽取时把一句话拆成多行的问题。"""
        lines = text.splitlines()
        merged_lines = []
        buffer = []

        for line in lines:
            stripped = _normalize_spaces(line)
            if _is_mergeable_single_char(stripped):
                buffer.append(stripped)
                continue

            if buffer:
                if len(buffer) >= 2:
                    merged_lines.append("".join(buffer))
                else:
                    merged_lines.extend(buffer)
                buffer = []
            merged_lines.append(line)

        if buffer:
            if len(buffer) >= 2:
                merged_lines.append("".join(buffer))
            else:
                merged_lines.extend(buffer)

        return "\n".join(merged_lines)

    def _print_cleaning_debug(
        self,
        raw_documents: list[Document],
        cleaned_documents: list[Document],
    ) -> None:
        """构建索引前输出清洗样例，方便观察清洗效果。"""
        if not raw_documents:
            print("RAG 清洗调试：没有读取到 PDF 文档。")
            return

        cleaned_by_page = {
            document.metadata.get("page"): document for document in cleaned_documents
        }
        sample_size = min(DEBUG_SAMPLE_PAGES, len(raw_documents))
        random.seed(2026)
        sample_indexes = sorted(random.sample(range(len(raw_documents)), sample_size))

        print("RAG 清洗调试：")
        print("=" * 80)
        for index in sample_indexes:
            raw_document = raw_documents[index]
            page = raw_document.metadata.get("page")
            cleaned_document = cleaned_by_page.get(page)
            raw_text = raw_document.page_content or ""
            cleaned_text = cleaned_document.page_content if cleaned_document else ""
            page_number = int(page) + 1 if isinstance(page, int) else index + 1

            print(f"第 {page_number} 页")
            print(f"原始长度：{len(raw_text)}")
            print(f"清洗后长度：{len(cleaned_text)}")
            print("清洗前样例：")
            print(_preview(raw_text))
            print("清洗后样例：")
            print(_preview(cleaned_text))
            print("-" * 80)

    def _print_chunk_debug(self, raw_chunks: list[Document], cleaned_chunks: list[Document]) -> None:
        """输出切块统计，观察清洗后 chunk 数量和平均长度。"""
        if not cleaned_chunks:
            print("RAG 切块调试：没有生成 chunk。")
            return

        raw_lengths = [len(chunk.page_content) for chunk in raw_chunks]
        cleaned_lengths = [len(chunk.page_content) for chunk in cleaned_chunks]
        raw_average = sum(raw_lengths) / len(raw_lengths) if raw_lengths else 0
        cleaned_average = sum(cleaned_lengths) / len(cleaned_lengths)
        print("RAG 切块调试：")
        print(f"清洗前 chunk 数量：{len(raw_chunks)}")
        print(f"清洗后 chunk 数量：{len(cleaned_chunks)}")
        print(f"清洗前平均 chunk 长度：{raw_average:.1f}")
        print(f"清洗后平均 chunk 长度：{cleaned_average:.1f}")
        print(f"清洗后最短 chunk 长度：{min(cleaned_lengths)}")
        print(f"清洗后最长 chunk 长度：{max(cleaned_lengths)}")
        print("=" * 80)

    def load(self) -> bool:
        index_dir = self.settings.index_dir
        if not (index_dir / "index.faiss").exists():
            return False

        self.vectorstore = FAISS.load_local(
            str(index_dir),
            self._get_embeddings(),
            allow_dangerous_deserialization=True,
        )
        self._load_keyword_index()
        return True

    def ensure_loaded(self) -> None:
        if self.vectorstore is not None:
            return
        if not self.load():
            self.build()

    def search(self, query: str, k: int = 4) -> str:
        self.ensure_loaded()
        assert self.vectorstore is not None

        docs = self._hybrid_search(query, k=k)
        if not docs:
            return "没有检索到相关资料。"

        lines = []
        for idx, doc in enumerate(docs, start=1):
            source = Path(doc.metadata.get("source", "PDF")).name
            page = doc.metadata.get("page")
            page_text = f"第 {int(page) + 1} 页" if isinstance(page, int) else "未知页码"
            content = " ".join(doc.page_content.split())
            lines.append(f"[{idx}] 来源：{source}，{page_text}\n{content}")
        return "\n\n".join(lines)

    def _hybrid_search(self, query: str, k: int) -> list[Document]:
        """混合检索：向量召回负责语义，关键词召回负责课程名、教师名和编号。"""
        assert self.vectorstore is not None

        vector_docs = self.vectorstore.similarity_search(query, k=max(k, VECTOR_CANDIDATES))
        keyword_docs = self._keyword_search(query, limit=KEYWORD_CANDIDATES)

        scored_docs: dict[tuple[int | None, str], tuple[float, Document]] = {}
        for rank, doc in enumerate(vector_docs):
            key = _document_key(doc)
            score = 1.0 / (rank + 1)
            scored_docs[key] = (score, doc)

        for rank, doc_score in enumerate(keyword_docs):
            doc, keyword_score = doc_score
            key = _document_key(doc)
            score = 2.0 + keyword_score + 1.0 / (rank + 1)
            if key in scored_docs:
                score += scored_docs[key][0]
            scored_docs[key] = (score, doc)

        ranked = sorted(scored_docs.values(), key=lambda item: item[0], reverse=True)
        return [doc for _, doc in ranked[:k]]

    def _keyword_search(self, query: str, limit: int) -> list[tuple[Document, float]]:
        """基于关键词重叠的轻量检索，不替代向量检索，只用于补强精确匹配。"""
        if not self.keyword_documents:
            return []

        query_terms = _extract_query_terms(query)
        if not query_terms:
            return []

        results = []
        for doc in self.keyword_documents:
            content = doc.page_content
            score = 0.0
            for term in query_terms:
                if term in content:
                    score += _term_weight(term) * min(content.count(term), 3)
            matched_terms = sum(1 for term in query_terms if term in content)
            if matched_terms >= 2:
                score += matched_terms * 3.0
            if score > 0:
                results.append((doc, score))

        results.sort(key=lambda item: item[1], reverse=True)
        return results[:limit]

    def _save_keyword_index(self, chunks: list[Document]) -> None:
        """保存关键词索引使用的清洗后 chunk，便于下次启动时混合检索。"""
        index_path = self.settings.index_dir / KEYWORD_INDEX_FILE
        with index_path.open("wb") as file:
            pickle.dump(chunks, file)
        self.keyword_documents = chunks

    def _load_keyword_index(self) -> None:
        """加载关键词索引；旧索引不存在时仍保持向量检索可用。"""
        index_path = self.settings.index_dir / KEYWORD_INDEX_FILE
        if not index_path.exists():
            self.keyword_documents = []
            return
        with index_path.open("rb") as file:
            self.keyword_documents = pickle.load(file)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_header_or_footer(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    if compact in HEADER_FOOTER_PATTERNS:
        return True
    project_chars = set("选课小本本项目组出品")
    if len(compact) <= 12 and compact and all(char in project_chars for char in compact):
        return True
    return any(compact.count(pattern) >= 1 and len(compact) <= len(pattern) + 4 for pattern in HEADER_FOOTER_PATTERNS)


def _is_page_number(line: str) -> bool:
    return bool(re.fullmatch(r"\d{1,4}", line))


def _is_table_of_contents_line(line: str) -> bool:
    compact = line.replace(" ", "")
    if compact == "目录":
        return True
    return ". ." in line and bool(re.search(r"\d+\.\d+", line))


def _looks_like_table_of_contents(text: str) -> bool:
    if not text:
        return False
    lines = text.splitlines()
    dot_leader_lines = sum(1 for line in lines if ". ." in line)
    return dot_leader_lines >= 5


def _is_noise_short_line(line: str) -> bool:
    if len(line) >= 2:
        return False
    return not re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]", line)


def _is_mergeable_single_char(line: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]", line))


def _preview(text: str) -> str:
    preview = text.strip()[:DEBUG_SAMPLE_CHARS]
    return preview if preview else "（空）"


def _document_key(document: Document) -> tuple[int | None, str]:
    page = document.metadata.get("page")
    return page, document.page_content[:120]


def _extract_query_terms(query: str) -> list[str]:
    """抽取用于关键词检索的中文、英文、编号和教师名片段。"""
    compact_query = _normalize_spaces(query)
    terms = []

    terms.extend(re.findall(r"\d+(?:\.\d+)+", compact_query))
    terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_+-]{1,}", compact_query))
    terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}", compact_query))

    # 对较长中文短语增加滑动窗口，提升“课程名 + 教师名”精确检索命中率。
    for term in list(terms):
        if re.fullmatch(r"[\u4e00-\u9fff]{5,}", term):
            terms.extend(_chinese_ngrams(term, size=4))
            terms.extend(_chinese_ngrams(term, size=3))

    deduped_terms = []
    seen = set()
    for term in terms:
        if term not in seen:
            deduped_terms.append(term)
            seen.add(term)
    return deduped_terms


def _chinese_ngrams(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    return [text[index : index + size] for index in range(len(text) - size + 1)]


def _term_weight(term: str) -> float:
    if re.fullmatch(r"\d+(?:\.\d+)+", term):
        return 8.0
    if len(term) >= 5:
        return 4.0
    if len(term) >= 3:
        return 2.0
    return 1.0
