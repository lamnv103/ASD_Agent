# Retriever và công cụ agent — bộ 33 tài liệu

Đây là bước 1: agent có thể gọi trực tiếp Python để tìm nguồn và đọc toàn văn từ PostgreSQL. Không phải chatbot trả lời hoàn chỉnh; không gọi mô hình sinh câu trả lời.

## Luồng hoạt động

Câu hỏi tiếng Việt → Cohere `embed-v4.0`, `input_type=search_query` → một vector câu hỏi → PostgreSQL/pgvector xếp hạng cosine → source ID, tên, link, tác giả, ngày, phạm vi và toàn văn gốc.

- Collection: `asd_fulltext_33_20261030_26eb017efca5`.
- Space: `cohere4_whole_1536_e83c596b9070`.
- Mỗi tài liệu vẫn có đúng một vector 1536 chiều, `truncate=NONE`.
- Không chia đoạn, đọc `index_preview.jsonl`, nhúng lại tài liệu hoặc sửa database.
- Với 33 vector, tìm kiếm cosine chính xác; chưa cần chỉ mục ANN.
- Nội dung khi tìm/đọc lấy từ PostgreSQL, không quét Markdown/`documents.json` mỗi câu hỏi.

## Chạy từ PowerShell

Mở terminal ở `E:\AI4LIFE\ASD_AGENT`.

Kiểm tra kết nối, toàn văn, metadata và vector; không cần khóa API:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag health
```

Đọc nguyên một tài liệu từ database; không cần khóa API:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag source ASD-NEW-003
```

Tìm top 5. Dùng tệp riêng `deployments/cohere.env` có dòng `COHERE_API_KEY=...`; có mẫu `deployments/cohere.env.example`. Tệp `.env` hiện tại là YAML của NVIDIA, không phải cấu hình Cohere.

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag --key-file deployments/cohere.env search "Trẻ tự kỷ kén ăn cần được đánh giá thế nào?"
```

Hoặc nhập khóa ẩn, không ghi khóa vào lệnh/lịch sử terminal:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag --prompt-key search "AAC có hỗ trợ trẻ chưa nói không?"
```

Mặc định CLI search chỉ in metadata để dễ đọc. Thêm `--full-content` sau câu hỏi để nhận toàn văn top 5. Nội dung không bị cắt ngầm. Cần dự trù cửa sổ ngữ cảnh ở tầng LLM sau này; không đưa năm tài liệu dài vào một prompt một cách máy móc.

## Agent gọi Python

```python
from rag.tools import RAGTools, TOOL_SCHEMAS

tools = RAGTools(key_file="deployments/cohere.env")
# Đăng ký TOOL_SCHEMAS với framework agent bạn chọn.
found = tools.dispatch("search_sources", {"query": "AAC là gì?", "top_k": 5})
if found["status"] == "ok" and found["results"]:
    source = tools.dispatch("read_source", {
        "source_id": found["results"][0]["source_id"]
    })
    # source["document"]["content"] là toàn văn nguyên bản từ PostgreSQL.
```

Hoặc gọi `PostgresRetriever().retrieve(query, top_k=5)` để lấy cả toàn văn trong một lần. `search_sources` trả danh mục có dẫn nguồn; `read_source` đọc đủ nội dung khi agent cần. `TOOL_SCHEMAS` là schema trung lập để tích hợp, chưa tự cấu hình hay chạy LLM.

## Tệp nào dùng làm gì

| Tệp | Vai trò |
|---|---|
| `rag/retriever.py` | Kết nối chỉ đọc, kiểm tra collection/profile/hash, nhúng câu hỏi, cache và SQL cosine. |
| `rag/tools.py` | Hai công cụ agent và bộ điều phối tên/tham số có kiểm tra. |
| `rag/__main__.py` | CLI `health`, `search`, `source`. |
| `deployments/retriever.json` | Collection/space/profile cố định, hash toàn văn, metadata và vector của 33 tài liệu. Không chứa mật khẩu. |
| `deployments/database.env` | Kết nối PostgreSQL hiện có; không in/chia sẻ nội dung tệp. |
| `reports/retriever/query_cache/` | Vector câu hỏi thật và provenance; giúp chạy lại cùng câu mà không gọi API. Không phải vector tài liệu mới. |
| `tests/test_retriever.py` | Kiểm thử đầu vào, provider/cache, toàn văn và database thật chỉ đọc. |

Runtime dùng `psycopg2-binary`, `python-dotenv`, `certifi` đã có trong `.venv-embedding`. Không cần chạy mã agent hoặc trỏ đường dẫn sang thư mục Carobud cũ. PostgreSQL `asd_rag` đang chứa collection mới vẫn phải chạy.

## Các giới hạn được giữ rõ

Mỗi lần đọc/tìm đều xác minh đúng 33 nguồn, hash toàn văn/metadata/vector và profile Cohere. Transaction là `READ ONLY`, `REPEATABLE READ`, tham số SQL được truyền riêng. Nguồn chờ duyệt và nguồn thuộc collection cũ không được nhập vào kết quả. Khi nguồn/profile sai, runtime báo lỗi thay vì tìm sang collection khác. Cấu hình/manifest là mốc kiểm tra, không phải chữ ký chống sửa bởi người có quyền quản trị.

Khóa chỉ lấy từ `COHERE_API_KEY`, tệp Cohere dotenv được chỉ định hoặc nhập ẩn. Không dùng khóa NVIDIA cho Cohere; không ghi khóa vào báo cáo/cache. Khóa đã lộ trong hội thoại trước đây nên được thay bằng khóa mới trước khi vận hành lâu dài.

Cache câu hỏi gắn đúng query, space và profile, có checksum. Cache hỏng được báo lỗi; không tự gọi lại API. HTTP 401/429/timeout được phân biệt và không tự lặp request. Khi đã xử lý lỗi, chạy lại sẽ dùng cache cho các câu đã thành công.

`status=not_found` khác với `status=error`. Khoảng cách cosine không phải độ tin cậy lâm sàng. Vector search luôn trả các tài liệu gần nhất ngay cả khi không có nguồn đủ trả lời; `evidence_sufficiency=not_assessed` được giữ nguyên. Agent vẫn cần đọc nguồn, giữ giới hạn tuổi/quần thể/quốc gia, đối chiếu và từ chối khi thiếu căn cứ.

Bộ này phục vụ nghiên cứu, **chưa có thẩm định lâm sàng độc lập**. Chưa nối chatbot cũ, chưa sinh câu trả lời, chưa đánh giá độ đúng của câu trả lời/trích dẫn.

Bước 2 và kết quả thật được hướng dẫn ở [evaluation/retrieval_v1/README.md](../evaluation/retrieval_v1/README.md).

Tham chiếu API chính thức về `search_query`, kích thước vector và `truncate`: [Cohere Embed API](https://docs.cohere.com/v2/reference/embed).
