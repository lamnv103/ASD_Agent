"""Chat thử NỘI BỘ: hỏi đáp trên terminal bằng pipeline hiện hành (v0.5), mỗi câu hỏi xử lý độc lập.

    .\\tasks.ps1 chat
    (hoặc) .venv-embedding\\Scripts\\python.exe -B scripts/dev/chat_thu.py

Không phải sản phẩm: đầu ra mang nhãn "NGUYÊN MẪU NỘI BỘ", chua_duyet, không dùng cho người dùng thật.
Chỉ dùng câu hỏi GIẢ ĐỊNH, không có thông tin thật của trẻ hay gia đình.

Khóa: NVIDIA từ secrets/nvidia.env; Cohere từ secrets/cohere.env (COHERE_API_KEY=...), nếu trống thì nhập ẩn
một lần cho cả phiên (chỉ giữ trong bộ nhớ). Không in, không ghi khóa ra đâu.
Mỗi câu hỏi được lưu (trace + kết quả) vào reports/chat_thu/<phiên>/ (git bỏ qua thư mục này).
Không sửa gì trong rag/: dùng đúng GuardedEvidencePipeline + answer_from_trace như rag.answer.
"""
import getpass
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values  # noqa: E402

from rag.answer_client import AnswerNimClient, read_answer_key  # noqa: E402
from rag.answer_layer import answer_from_trace, emergency_result  # noqa: E402
from rag.answer_policy import detect_emergency, load_config  # noqa: E402
from rag.retriever import atomic_json  # noqa: E402

NVIDIA_KEY_FILE = ROOT / "secrets/nvidia.env"
COHERE_KEY_FILE = ROOT / "secrets/cohere.env"
OUT_ROOT = ROOT / "reports/chat_thu"

BANNER = """==================================================================
 CHAT THỬ NỘI BỘ - ASD_AGENT (pipeline v0.5, chua_duyet)
 - Chỉ dùng câu hỏi GIẢ ĐỊNH, không nhập thông tin thật của trẻ/gia đình.
 - Mỗi câu hỏi độc lập: chat KHÔNG nhớ câu trước.
 - Mỗi câu tốn khoảng 1 lượt Cohere + 3-6 lượt NVIDIA, mất vài chục giây.
 Lệnh: /chitiet = xem nhận định bị loại của câu vừa rồi | /thoat = kết thúc
=================================================================="""


def has_value(path, name):
    return path.exists() and bool((dotenv_values(path, interpolate=False).get(name) or "").strip())


def build():
    """Retriever + reader + client, checked once. Returns (pipe, client_factory, cohere_secret_holder) or exits."""
    if not has_value(NVIDIA_KEY_FILE, "NVIDIA_API_KEY"):
        sys.exit(f"Thiếu khóa NVIDIA trong {NVIDIA_KEY_FILE.relative_to(ROOT)} (dòng NVIDIA_API_KEY=...).")
    from rag.guarded_pipeline import GuardedEvidencePipeline
    from rag.retriever import PostgresRetriever
    from rag.semantic_reader_v3 import AtomicNeedsReader
    retriever = PostgresRetriever(key_file=str(COHERE_KEY_FILE) if has_value(COHERE_KEY_FILE, "COHERE_API_KEY") else None)
    try:
        retriever.health()
    except Exception as exc:
        sys.exit("Không kết nối được database (" + (getattr(exc, "code", None) or type(exc).__name__) + ").\n"
                 "  1) Mở Docker Desktop, đợi 'Engine running'\n  2) docker start deployments-rag-db-1\n"
                 "  3) .\\tasks.ps1 db-health  -> phải báo status ok, rồi chạy lại chat.")
    if not has_value(COHERE_KEY_FILE, "COHERE_API_KEY"):
        print(f"Chưa có khóa Cohere trong {COHERE_KEY_FILE.relative_to(ROOT)}. Nhập ẩn một lần cho phiên này.")
        secret = getpass.getpass("Cohere API key (ẩn): ").strip()
        if not secret:
            sys.exit("Không có khóa Cohere: không truy xuất được tài liệu.")
        retriever.embedder.key_supplier = lambda: secret
    pipe = GuardedEvidencePipeline(retriever)
    pipe.semantic_reader = AtomicNeedsReader(counter=pipe.counter, key_supplier=lambda: read_answer_key(str(NVIDIA_KEY_FILE)))
    return pipe


def removed_text(result):
    lines = []
    for c in result.get("claims_removed", []):
        lines.append(f"  - [{c.get('round')}/{c.get('disposition')}] {c.get('text', '')}\n      lý do: {', '.join(c.get('reasons', [])) or '-'}")
    return "\n".join(lines) or "  (không có nhận định nào bị loại)"


def ask(pipe, cfg, question, n, folder):
    hits = detect_emergency(question, cfg)
    if hits:  # before any provider call, as in rag.answer
        return emergency_result(question, cfg, hits), 0
    trace = pipe.prepare(question, trace_path=str(folder / f"q{n:02d}.trace.json"))
    client = AnswerNimClient(pipe.counter, key_file=str(NVIDIA_KEY_FILE))
    result = answer_from_trace(trace, client=client)
    result["reader_calls"] = trace.get("semantic_reader", {}).get("calls", [])
    fresh = sum(not c.get("cache_hit") for c in result.get("calls", []) + result["reader_calls"])
    return result, fresh


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    print(BANNER)
    cfg = load_config()
    pipe = build()
    folder = OUT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Sẵn sàng. Lưu phiên tại {folder.relative_to(ROOT)}\n")
    last, n = None, 0
    while True:
        try:
            q = input("Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q in ("/thoat", "/exit", "/quit"):
            break
        if q in ("/chitiet", "/details"):
            print(removed_text(last) if last else "  (chưa có câu trả lời nào)")
            continue
        n += 1
        print("  ... đang truy xuất tài liệu, đọc bằng chứng và kiểm tra câu trả lời ...", flush=True)
        try:
            result, fresh = ask(pipe, cfg, q, n, folder)
        except Exception as exc:
            print(f"Lỗi hệ thống: {getattr(exc, 'code', None) or type(exc).__name__}. Câu hỏi không được trả lời.\n")
            continue
        atomic_json(folder / f"q{n:02d}.result.json", dict(question=q, **result))
        last = result
        print("\nTrợ lý:\n" + result["render"]["text"])
        print(f"\n  [trạng thái: {result.get('status')} | route: {result.get('route')} | sửa: {result.get('repairs')} "
              f"| bị loại: {len(result.get('claims_removed', []))} | lượt gọi mới: {fresh}"
              + (f" | lỗi: {result.get('error')}" if result.get("error") else "") + "]\n")
    print(f"Kết thúc. {n} câu hỏi đã lưu tại {folder.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
