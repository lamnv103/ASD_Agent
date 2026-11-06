# Dựng môi trường và kiểm tra ASD_AGENT

Dành cho người phát triển hoặc người nghiệm thu muốn chạy lại dự án trên một máy Windows khác. Mọi lệnh kiểm tra chỉ đọc database và dùng cache: **không gọi Cohere/NVIDIA, không tốn phí API.**

Đã kiểm chứng ngày 07/11/2026 trên một bản clone sạch: venv mới từ lockfile, `.\tasks.ps1 all` đạt toàn bộ (157 test, 4 verifier, quét bí mật).

## 1. Yêu cầu

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| Python | **3.13** (đã kiểm 3.13.9) | Nếu `py -3.13` không có, đặt `$env:ASD_PYTHON` tới python.exe 3.13 |
| Docker Desktop | bất kỳ bản hỗ trợ compose v2 | Chạy PostgreSQL 16 + pgvector 0.8.6 |
| Git | ≥ 2.40 | Bắt buộc bật đường dẫn dài (xem bước 2) |

## 2. Lấy mã nguồn

```powershell
git clone -c core.longpaths=true <đường-dẫn-repo> ASD_AGENT
cd ASD_AGENT
git config core.longpaths true
```

`core.longpaths` cần vì một số thư mục bằng chứng (`reports/whole_document_embedding_20261030/vectors/...`) vượt giới hạn 260 ký tự của Windows. Repo có `.gitattributes` (`* -text`): file được lưu nguyên byte để các hash nghiệm thu không bị đổi bởi chuyển CRLF/LF.

## 3. Cài môi trường Python

```powershell
$env:ASD_PYTHON = 'C:\Users\<bạn>\miniconda3\python.exe'   # chỉ khi py -3.13 không có
.\tasks.ps1 setup
```

Tạo `.venv-embedding` và cài đúng phiên bản trong `requirements.lock.txt`. Danh sách phụ thuộc trực tiếp nằm ở `pyproject.toml`.

## 4. Cấu hình bí mật (không bao giờ commit)

| Tệp / biến | Dùng cho | Tạo từ |
|---|---|---|
| `deployments/database.env` | Retriever đọc PostgreSQL (`RAG_DATABASE_URL`, collection, embedding space) | `deployments/database.env.example` |
| `deployments/rag-db.env` | Mật khẩu khi compose **tạo mới** volume (`RAG_DB_PASSWORD`) | `deployments/rag-db.env.example` |
| `COHERE_API_KEY` (biến môi trường) hoặc `--cohere-key-file <dotenv>` | Nhúng câu hỏi **mới** | — |
| `NVIDIA_API_KEY` (biến môi trường) hoặc `--nvidia-key-file <dotenv>` | Reader NIM cho câu hỏi **mới** | — |

- Câu hỏi đã có trong cache và mọi lệnh kiểm tra **không cần khóa**.
- Không dùng tệp `.env` ở thư mục gốc cho NVIDIA: tệp đó là cấu hình YAML của Continue, không phải dotenv. Ưu tiên biến môi trường cho phiên làm việc.
- `.gitignore` chặn `*.env`, `.env*`, `continue*.yaml`. Chạy `.\tasks.ps1 secrets` trước khi commit hoặc chia sẻ repo.
- **Cần làm ngay:** khóa NVIDIA trong `.env` cũ đã từng hiện trong log rà soát ngày 06/11/2026. Hãy thu hồi và tạo khóa mới trên trang quản lý của NVIDIA, rồi đặt khóa mới vào `NVIDIA_API_KEY`.

## 5. Database

```powershell
.\tasks.ps1 db-up            # khởi động container sẵn có, hoặc tạo bằng deployments/compose.rag.yml
.\tasks.ps1 db-health        # phải thấy 33 documents, 33 vectors, 1536 dims, read_only
.\tasks.ps1 db-backup        # backups\asd_rag_<thời điểm>.dump + .sha256 (thư mục bị git bỏ qua)
.\tasks.ps1 db-restore-check # khôi phục bản mới nhất vào DB tạm, so hash từng hàng, rồi xóa DB tạm
```

- Dữ liệu nằm trong volume Docker **`deployments_carobud_rag_data`**, được khai báo `external` trong compose: `docker compose down` không xóa dữ liệu. **Không chạy `docker volume rm` với volume này.**
- File compose gốc ở `D:\Carobud-ASD-master\...` đã mất. `deployments/compose.rag.yml` tái tạo đúng project, service, image digest, cổng `127.0.0.1:5433` và volume.
- Khôi phục trên máy mới: `db-up` (volume trống sẽ được khởi tạo bằng `RAG_DB_PASSWORD`), sau đó `docker cp` bản dump vào container rồi chạy `pg_restore -U postgres -d asd_rag --clean --if-exists /tmp/<file>.dump`. Cuối cùng chạy `db-health` và `.\tasks.ps1 verify`.
- Bản sao lưu đã kiểm chứng: `asd_rag_20261106_235335.dump` và `asd_rag_20261107_000554.dump`, cả hai khôi phục khớp từng hàng: collections 3, documents 150, embedding_spaces 2, embeddings 40 (gồm cả collection cũ).

## 6. Kiểm tra

```powershell
.\tasks.ps1 all      # pins + db-health + test + verify + secrets
.\tasks.ps1 pins     # vài giây, không cần DB: không file nào bị ghim hash bị sửa
.\tasks.ps1 test     # 3 bộ test; lỗi nếu có fail/skip hoặc tổng khác 157
.\tasks.ps1 verify   # 4 verifier chỉ dùng cache
.\tasks.ps1 diag     # chẩn đoán truy xuất offline, theo từng bộ và theo câu duy nhất
```

Kết quả được ghi vào `reports/verification_runs/<tên>_<thời điểm>/` (git bỏ qua). **Không lệnh nào ghi vào thư mục báo cáo lịch sử.** Số test kỳ vọng nằm ở `[tool.asd_agent].expected_tests` trong `pyproject.toml`; khi thêm test, cập nhật con số này trong cùng commit.

## 7. Chạy một câu hỏi

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag.prepare_evidence "câu hỏi" --trace reports\my_trace.json
```

- Thứ tự xử lý: che định danh trực tiếp tại máy → lập kế hoạch câu hỏi (NVIDIA) → dừng nếu là chẩn đoán/liều cá nhân, pháp lý hoặc dịch vụ hiện hành → truy xuất (Cohere + PostgreSQL) → đọc bằng chứng → context. Chưa sinh câu trả lời cho người dùng.
- `python -m rag.read_evidence` (thứ tự cũ: truy xuất trước) được giữ nguyên để đối chiếu, vì các run nghiệm thu ghim hash của nó.
- Giới hạn của guard: không phát hiện tên người, địa chỉ hoặc mô tả tự do về trẻ; câu hỏi vẫn được gửi tới NVIDIA để phân loại; việc phân loại do model thực hiện. Chính sách dữ liệu (bước 6 của kế hoạch) phải quyết định phần còn lại.

## 8. Quy tắc với file bị ghim hash

61 file được các run nghiệm thu ghim SHA-256, gồm `rag/{__init__,__main__,retriever,tools,evidence_pipeline,evidence,context,semantic_reader,semantic_reader_v3,read_evidence}.py`, `deployments/{retriever,evidence_context,semantic_reader,semantic_reader_v3}.json`, `deployments/database.env`, `scripts/evaluation/evaluate_reader_v3.py` và 45 input trong `evaluation/`. Ngoài ra, 132 tệp nguồn và snapshot DB được kiểm tra riêng.

- Thêm chức năng bằng **module mới** (như `rag/guarded_pipeline.py`), không sửa file bị ghim.
- Khi buộc phải sửa file bị ghim (refactor, đổi prompt), làm như một **bản phát hành mới**: tag git trước, chạy đánh giá mới để tạo manifest mới, rồi cập nhật verifier sang baseline mới. Các verifier cũ vẫn chạy được trên tag cũ (`git worktree add ..\asd_baseline baseline-v3-20261102`).
- `.\tasks.ps1 pins` báo ngay file nào bị đổi.

## 9. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `pip` lỗi "Could not find a suitable TLS CA certificate bundle ... E:\..." | Biến hệ thống `CURL_CA_BUNDLE` trỏ tới ổ E: đã mất | `tasks.ps1` tự bỏ biến này trong phiên; nên xóa biến khỏi System Environment Variables |
| 4 test `LiveReadOnlyTests` lỗi `database_error` | PostgreSQL chưa chạy | `.\tasks.ps1 db-up` |
| `ModuleNotFoundError: rag` / `test_evidence_context` | Chạy unittest sai thư mục | Dùng `.\tasks.ps1 test` |
| Clone lỗi "Filename too long" | Chưa bật long paths | Bước 2 |
| `[transformers] PyTorch was not found` | Thông báo vô hại: chỉ dùng tokenizer | `tasks.ps1` đặt `TRANSFORMERS_VERBOSITY=error` |
| Verifier báo "Evaluation used another implementation" | Đã sửa một file bị ghim | `.\tasks.ps1 pins`, hoàn nguyên bằng `git checkout -- <file>` hoặc làm bản phát hành mới |
