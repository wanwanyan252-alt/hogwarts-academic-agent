import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PDF_PATH = Path(r"C:\Users\王梓蕊\Desktop\选课小本本 2024-2025学年秋季刊.pdf")
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    chat_model: str
    embedding_model: str
    pdf_path: Path
    index_dir: Path


def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")

    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not deepseek_api_key:
        raise RuntimeError(
            "缺少 DEEPSEEK_API_KEY。请复制 .env.example 为 .env，并填写 DeepSeek API Key。"
        )

    pdf_path = Path(os.getenv("RAG_PDF_PATH", str(DEFAULT_PDF_PATH))).expanduser()
    index_dir = Path(os.getenv("RAG_INDEX_DIR", str(PROJECT_ROOT / "data" / "faiss_index")))

    return Settings(
        deepseek_api_key=deepseek_api_key,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).strip(),
        chat_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
        embedding_model=os.getenv("LOCAL_EMBEDDING_MODEL", DEFAULT_LOCAL_EMBEDDING_MODEL).strip(),
        pdf_path=pdf_path,
        index_dir=index_dir,
    )
