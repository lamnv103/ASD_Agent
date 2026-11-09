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
# Prepared questions: retrieval and evidence selection already done (trace), so only NVIDIA is needed.
TRACE_DIR = ROOT / "reports/reader_refinement_20261101_232742/run_20261102_004612_154953/traces"

BANNER = """==================================================================
 CHAT THỬ NỘI BỘ - ASD_AGENT (pipeline v0.5, chua_duyet)
 - Chỉ dùng câu hỏi GIẢ ĐỊNH, không nhập thông tin thật của trẻ/gia đình.
 - Mỗi câu hỏi độc lập: chat KHÔNG nhớ câu trước.
 - Mỗi câu tốn khoảng 1 lượt Cohere + 3-6 lượt NVIDIA, mất vài chục giây.
 Lệnh: /mau = danh sách câu mẫu | /mau H04 = hỏi câu mẫu (chỉ cần khóa NVIDIA)
       /chitiet = nhận định bị loại của câu vừa rồi | /thulai = hỏi lại câu vừa lỗi (lượt gọi mới)
       /thoat = kết thúc
=================================================================="""


def has_value(path, name):
    return path.exists() and bool((dotenv_values(path, interpolate=False).get(name) or "").strip())


def prepared():
    import json as _json
    return {f.stem: _json.loads(f.read_text(encoding="utf-8")) for f in sorted(TRACE_DIR.glob("*.json"))}


def build():
    """Retriever + reader for FREE questions, or None when no Cohere key is given (prepared questions still work).
    Query embeddings must come from the same Cohere model as the stored vectors: an NVIDIA key cannot replace it."""
    from rag.guarded_pipeline import GuardedEvidencePipeline
    from rag.retriever import PostgresRetriever
    from rag.semantic_reader_v3 import AtomicNeedsReader
    retriever = PostgresRetriever(key_file=str(COHERE_KEY_FILE) if has_value(COHERE_KEY_FILE, "COHERE_API_KEY") else None)
    try:
        retriever.health()
    except Exception as exc:
        print("Không kết nối được database (" + (getattr(exc, "code", None) or type(exc).__name__) + "): "
              "chỉ dùng được câu mẫu (/mau).\n  Muốn hỏi tự do: mở Docker Desktop, chạy docker start deployments-rag-db-1, "
              "rồi mở lại chat.")
        return None
    if not has_value(COHERE_KEY_FILE, "COHERE_API_KEY"):
        print(f"Chưa có khóa Cohere trong {COHERE_KEY_FILE.relative_to(ROOT)}.")
        secret = getpass.getpass("Nhập khóa Cohere (ẩn), hoặc Enter để chỉ dùng câu mẫu: ").strip()
        if not secret:
            print("-> Chế độ câu mẫu: gõ /mau để xem 6 câu hỏi đã chuẩn bị. Câu hỏi tự do cần khóa Cohere.")
            return None
        retriever.embedder.key_supplier = lambda: secret
    pipe = GuardedEvidencePipeline(retriever)
    pipe.semantic_reader = AtomicNeedsReader(counter=pipe.counter, key_supplier=lambda: read_answer_key(str(NVIDIA_KEY_FILE)))
    return pipe


HINTS = {
    "v3_selection_schema": "bộ đọc chọn sai mã đoạn tài liệu (ví dụ chép nhầm mã); hệ thống từ chối thay vì đoán gần đúng. "
                           "Gõ /thulai để hỏi lại với lượt gọi mới.",
    "v3_plan_schema": "bộ đọc phân tích câu hỏi sai cấu trúc. Gõ /thulai để thử lại, hoặc diễn đạt câu hỏi rõ hơn.",
    "reader_no_context": "không có đoạn tài liệu phù hợp để đọc cho câu hỏi này.",
    "nim_rate_limit": "NVIDIA đang giới hạn tốc độ (HTTP 429). Đợi một lúc rồi /thulai.",
    "nim_network": "lỗi mạng hoặc hết thời gian chờ. Kiểm tra mạng rồi /thulai.",
    "database_error": "mất kết nối database: kiểm tra Docker Desktop và deployments-rag-db-1.",
}


def error_text(exc):
    code = getattr(exc, "code", None) or type(exc).__name__
    detail = str(exc).split(": ", 1)[-1] if ": " in str(exc) else ""
    return f"{code}" + (f" ({detail})" if detail and detail != code else "") + (f"\n  -> {HINTS[code]}" if code in HINTS else "")


def removed_text(result):
    lines = []
    for c in result.get("claims_removed", []):
        lines.append(f"  - [{c.get('round')}/{c.get('disposition')}] {c.get('text', '')}\n      lý do: {', '.join(c.get('reasons', [])) or '-'}")
    return "\n".join(lines) or "  (không có nhận định nào bị loại)"


def fresh_reader_client(pipe, folder, n):
    """A reader client whose cache is new for this one attempt: the shared reader cache would replay the same
    rejected output forever. The reader itself (pinned) is unchanged."""
    from rag.semantic_reader import NimClient
    return NimClient(pipe.semantic_reader.config, pipe.counter, key_supplier=lambda: read_answer_key(str(NVIDIA_KEY_FILE)),
                     cache_dir=folder / f"reader_retry_q{n:02d}")


def ask(pipe, cfg, question, n, folder, trace=None, fresh=False):
    hits = detect_emergency(question, cfg)
    if hits:  # before any provider call, as in rag.answer
        return emergency_result(question, cfg, hits), 0
    sample = trace is not None
    if not sample:
        old = pipe.semantic_reader.client
        if fresh:
            pipe.semantic_reader.client = fresh_reader_client(pipe, folder, n)
        try:
            trace = pipe.prepare(question, trace_path=str(folder / f"q{n:02d}.trace.json"))
        finally:
            pipe.semantic_reader.client = old
        counter = pipe.counter
    else:  # prepared question: the answer layer only, as rag.answer --from-trace
        from rag.tokenization import load_counter
        counter = load_counter(json.loads((ROOT / "deployments/evidence_context.json").read_text(encoding="utf-8")))
    client = AnswerNimClient(counter, key_file=str(NVIDIA_KEY_FILE))
    result = answer_from_trace(trace, client=client)
    # a prepared trace carries the reader calls of its original run: they are not new calls of this session
    result["reader_calls"] = [] if sample else trace.get("semantic_reader", {}).get("calls", [])
    fresh = sum(not c.get("cache_hit") for c in result.get("calls", []) + result["reader_calls"])
    return result, fresh


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    print(BANNER)
    cfg = load_config()
    if not has_value(NVIDIA_KEY_FILE, "NVIDIA_API_KEY"):
        sys.exit(f"Thiếu khóa NVIDIA trong {NVIDIA_KEY_FILE.relative_to(ROOT)} (dòng NVIDIA_API_KEY=...).")
    pipe = build()
    samples = prepared()
    folder = OUT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Sẵn sàng. Lưu phiên tại {folder.relative_to(ROOT)}\n")
    last, n, failed = None, 0, None
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
        trace, fresh = None, False
        if q in ("/thulai", "/retry"):
            if not failed:
                print("  (không có câu nào vừa lỗi)")
                continue
            q, trace, fresh = failed
            print(f"  Hỏi lại: {q}")
        elif q.startswith("/mau"):
            code = q[4:].strip().upper()
            if code not in samples:
                for k, t in samples.items():
                    print(f"  {k}: {t['question']}")
                print("  Gõ ví dụ: /mau H04")
                continue
            trace = samples[code]
            q = trace["question"]
            print(f"  Câu mẫu {code}: {q}")
        elif pipe is None:
            print("  Câu hỏi tự do cần khóa Cohere (secrets/cohere.env). Hiện chỉ dùng được /mau.")
            continue
        if fresh is False and trace is None and q == (failed or (None,))[0]:
            fresh = True  # the same question asked again right after a failure: do not replay the cached rejection
        n += 1
        print("  ... đang truy xuất tài liệu, đọc bằng chứng và kiểm tra câu trả lời ...", flush=True)
        try:
            result, calls = ask(pipe, cfg, q, n, folder, trace, fresh=bool(fresh))
        except Exception as exc:
            failed = (q, trace, True)
            atomic_json(folder / f"q{n:02d}.error.json", dict(question=q, error=str(exc), code=getattr(exc, "code", None)))
            print("Lỗi: " + error_text(exc) + "\n  Câu hỏi không được trả lời.\n")
            continue
        failed = None
        atomic_json(folder / f"q{n:02d}.result.json", dict(question=q, **result))
        last = result
        print("\nTrợ lý:\n" + result["render"]["text"])
        print(f"\n  [trạng thái: {result.get('status')} | route: {result.get('route')} | sửa: {result.get('repairs')} "
              f"| bị loại: {len(result.get('claims_removed', []))} | lượt gọi mới: {calls}"
              + (f" | lỗi: {result.get('error')}" if result.get("error") else "") + "]\n")
    print(f"Kết thúc. {n} câu hỏi đã lưu tại {folder.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
