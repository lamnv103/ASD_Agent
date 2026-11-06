# Bàn giao: chuẩn hóa nền kỹ thuật và kiểm tra đầu vào — 07/11/2026

Phạm vi: gói việc đầu tiên của kế hoạch đã thống nhất, gồm bước 2 (môi trường tái lập được), phần sửa đo lường của bước 3, đưa guard lên trước truy xuất, và bản nháp bước 1. Không thay đổi 33 tài liệu/33 vector, không sửa file bị ghim hash, không gọi provider API.

## 1. Kết quả nghiệm thu

| Tiêu chí (theo kế hoạch) | Kết quả | Bằng chứng |
|---|---|---|
| Môi trường sạch chạy đủ ba nhóm kiểm thử | **Đạt.** Clone mới + venv mới từ lockfile: `.\tasks.ps1 all` → ALL CHECKS PASSED | Chạy 07/11 trong thư mục clone riêng; 0 file bị thay đổi sau khi chạy |
| Đếm test tự động, giải thích mọi trường hợp bỏ qua | **Đạt.** 157 test (nay 167, xem phụ lục): tests/ 123, embedding 17, source_library 17; 0 fail, 0 error, 0 skip. Runner báo lỗi nếu tổng khác `pyproject.toml` | `scripts/dev/run_all_tests.py` |
| Collection 33/33 giữ nguyên toàn vẹn | **Đạt.** 4 verifier: DB snapshot và 132 tệp nguồn không đổi; 61 file bị ghim hash không đổi | `.\tasks.ps1 verify`, `.\tasks.ps1 pins` |
| Người khác làm theo hướng dẫn được | **Đạt về kỹ thuật.** SETUP.md đã được kiểm bằng clone sạch; chỉ cần tự tạo `deployments/database.env` | [SETUP.md](../../SETUP.md) |
| Kiểm định không ghi đè báo cáo cũ | **Đạt.** Mỗi lần chạy tạo `reports/verification_runs/<tên>_<thời điểm>/`; input đóng băng chỉ được so byte | `git status` sạch sau mọi lần verify |
| Cách khởi động DB, kiểm tra, phục hồi | **Đạt.** Compose được tái tạo; sao lưu; khôi phục vào DB tạm khớp hash từng hàng (4 bảng) | `.\tasks.ps1 db-backup`, `db-restore-check` |

## 2. Thay đổi đã thực hiện

Lịch sử git: `347f77b` baseline (tag `baseline-v3-20261102`) → `f701098` verifier → `2d4d751` môi trường + guard → `bc52ac9` setup → commit tài liệu.

**Quản lý phiên bản.** Khởi tạo git và commit baseline trước mọi thay đổi. `.gitattributes` (`* -text`) giữ nguyên byte để clone trên Windows không làm sai hash. `.gitignore` chặn bí mật, venv, `backups/` và `reports/verification_runs/`. Kho git khoảng 43 MB.

**Dependency.** `pyproject.toml` (phụ thuộc trực tiếp, ghim phiên bản) và `requirements.lock.txt` (đầy đủ). Bổ sung `beautifulsoup4`, `markdownify`, `pypdf` còn thiếu, nhờ đó test xử lý nguồn chạy được: 17/17.

**Đường dẫn.** Không còn đường dẫn ổ E: trong mã. Guard publish của `supplement_20261030.py` chuyển sang kiểm tra theo tên dự án trong `pyproject.toml`, không còn so ký tự ổ đĩa.

**Verifier.** Ba verifier cũ không còn ghi đè `verification.json`, `after.json`, log test trong thư mục lịch sử, và không ghi lại 31 input của `evaluation/evidence_context_v1`. Helper mới: `scripts/evaluation/audit_output.py`.

**Kiểm tra đầu vào trước truy xuất** (`rag/input_guard.py`, `rag/guarded_pipeline.py`, CLI `python -m rag.prepare_evidence`):
- Che tại máy: email, số điện thoại Việt Nam, số định danh 9/12 chữ số, ngày đầy đủ. Từ chối câu rỗng hoặc dài hơn 2000 ký tự. Trace chỉ ghi loại và số lượng đã che, không ghi giá trị.
- Lập kế hoạch câu hỏi v3 trước khi truy xuất, với payload giống hệt reader nên dùng chung cache. Chẩn đoán cá nhân, liều cá nhân, pháp lý và dịch vụ hiện hành dừng lại: **không gửi tới Cohere, không ghi query cache**.
- Phát lại 23 câu v3 chỉ từ cache: 18 câu cho kết quả giống hệt; 5 câu (N09, N10, N11, N12, F05) nay dừng trước truy xuất, kết luận, context và chính sách giống bản gốc. Khác biệt duy nhất là danh sách `excluded` rỗng, vì không còn đoạn nào được truy xuất mà không dùng. Script: `verify_guarded_pipeline.py`.
- 8 test mới khẳng định: retriever không được gọi khi bị chặn; chỉ văn bản đã che tới được provider; lỗi kế hoạch không rơi xuống bước truy xuất; input bị từ chối không liên hệ provider nào.
- `rag/read_evidence.py` **giữ nguyên** vì ba run nghiệm thu ghim hash của nó. Lần sửa đầu tiên đã bị verifier phát hiện và được hoàn nguyên.

**Database.** `deployments/compose.rag.yml` tái tạo file compose đã mất: cùng project, service, image digest, cổng, và volume `external` nên `down` không xóa dữ liệu. Hai bản sao lưu đã kiểm chứng nằm trong `backups/`.

**Đo lường.** `diagnose_retrieval_offline.py` được sửa: đọc `references` của retrieval_v1, báo cáo theo từng bộ và theo câu duy nhất. Kết quả khớp bản kiểm định độc lập: 55 câu duy nhất, hit@1 0,655, hit@5 0,964, MRR 0,779; hai ca trượt là H05 (hạng 19) và N02 (hạng 20).

**Công cụ.** `tasks.ps1` gồm setup, db-up, db-health, db-backup, db-restore-check, test, verify, diag, secrets, pins, all. Thêm `scripts/dev/secret_scan.py` và `scripts/dev/check_pins.py`.

**Tài liệu.** SETUP.md; [docs/MVP_SCOPE_DRAFT.md](../../docs/MVP_SCOPE_DRAFT.md); đầu README; sửa lỗi mã hóa ký tự trong bàn giao v3 và README_READER_V3; ghi chú đính chính vào đánh giá 06/11 và `retrieval_diagnostics.txt`.

## 3. Sự cố phát hiện trong quá trình làm

| Sự cố | Xử lý |
|---|---|
| File compose của container DB đã mất; **collection hiện tại chưa có bản sao lưu nào** (dump cũ có từ trước khi tạo collection) | Tái tạo compose; tạo và kiểm chứng sao lưu |
| Biến hệ thống `CURL_CA_BUNDLE` trỏ tới ổ E: đã mất, làm `pip` lỗi | `tasks.ps1` bỏ biến trong phiên. **Nên xóa biến khỏi cấu hình Windows** |
| `core.autocrlf=true` có thể làm sai toàn bộ hash khi clone | `.gitattributes` `* -text`; đã kiểm bằng clone sạch |
| Đường dẫn bằng chứng vượt 260 ký tự | Yêu cầu `core.longpaths` (SETUP.md bước 2) |
| `py -3.13` không có trên máy; Python 3.13 chỉ có trong miniconda | `setup` tự dò, hoặc đặt `$env:ASD_PYTHON` |
| Ngày 06/11, chạy verifier cũ đã ghi lại 73 file lịch sử: 31 input giống hệt hash cũ; 42 file còn lại bị thay mốc thời gian, giá trị số liệu không đổi | Không khôi phục được vì lúc đó chưa có git. Baseline ghi nhận trạng thái này; từ nay verifier không ghi vào thư mục lịch sử |

## 4. Việc còn lại

**Chủ dự án cần làm:**
1. **Thu hồi khóa NVIDIA cũ và tạo khóa mới** trên trang quản lý của NVIDIA. Khóa cũ từng hiện trong log rà soát ngày 06/11. Đặt khóa mới vào biến `NVIDIA_API_KEY`, không ghi vào file trong dự án.
2. Xóa biến hệ thống `CURL_CA_BUNDLE`, hoặc trỏ nó tới một file CA có thật.
3. Duyệt [docs/MVP_SCOPE_DRAFT.md](../../docs/MVP_SCOPE_DRAFT.md) cùng người phụ trách chuyên môn và chốt 11 quyết định ở mục 5 (các quyết định 9–11 về lưu, xóa và xem dữ liệu được bổ sung sau review).
4. Nếu đưa repo lên máy chủ git: dùng remote **riêng tư** (kho có tài liệu CC BY-NC), clone với `core.longpaths=true`.

**Giai đoạn kỹ thuật tiếp theo (chỉ sau khi chốt MVP):**
- Bước 3: bộ đánh giá mới gồm 30 câu phát triển và 50 câu kiểm tra, không ghi tên nguồn, nhãn AI chỉ là nháp và cần chuyên gia duyệt.
- Bước 4: điều tra H05, N02, S05, S08; mỗi lần chỉ thử một thay đổi truy xuất trên bộ phát triển, giữ collection 33 vector làm baseline.
- Bước 5: khung luồng trả lời trên bộ phát triển, có thể bắt đầu song song với bước 3–4.

**Giới hạn còn tồn tại (không che giấu):**
- Guard không phát hiện tên người, địa chỉ hoặc mô tả tự do về trẻ. Câu hỏi vẫn được gửi tới NVIDIA để phân loại. Việc phân loại do model làm nên vẫn có thể sai.
- Query cache vẫn lưu nguyên văn câu hỏi (đã che) trên đĩa, chưa có thời hạn lưu. Việc này thuộc chính sách dữ liệu ở bước 6.
- Mã trong các file bị ghim vẫn viết dày đặc và khó bảo trì. Chỉ nên refactor như một bản phát hành mới với baseline nghiệm thu mới.
- Mọi phép phát lại dùng câu hỏi đã có cache và nhãn do AI gán; đây không phải đánh giá chất lượng mới.

## Phụ lục — sửa theo review ngày 07/11/2026

Review: [reports/review_20261107/REVIEW_GOI_NEN_TANG.md](../review_20261107/REVIEW_GOI_NEN_TANG.md). Cả 6 phát hiện đã được tái hiện độc lập trước khi sửa (probe của người review: `retrieval_called=true`, ngày ISO không bị che, `database.env` bị ghim, `secrets.env` không bị bỏ qua). Commit sửa: `914518c`.

| # | Vấn đề | Đã sửa | Kiểm chứng |
|---|---|---|---|
| F1 | `database.env` của từng máy bị ghim hash | Khớp chính xác hash lịch sử thì đạt; nếu không, các thiết lập phát hành phải khớp `deployments/database.release.json`, còn host, cổng, user và mật khẩu được tự do. Quy tắc dùng chung cho `pins` và 3 verifier. Hash lịch sử giữ nguyên | 5 test mới; trên cluster mới với **mật khẩu và cổng khác**: `pins` báo NOTE và đạt, 4 verifier đạt |
| F2 | Thiếu bước tạo volume external trên máy mới | `db-up` tạo volume khi chưa có. Lệnh mới `db-bootstrap` kiểm checksum, khôi phục vào `asd_rag` trống, và từ chối nếu đã có dữ liệu | Docker **chưa có** volume hay container của bài thử: tạo, khôi phục, chạy `all`, tất cả đạt; chạy bootstrap lần 2 bị từ chối |
| F3 | Guard rơi xuống retriever khi thiếu reader v3 | Fail-closed với lỗi `input_guard_unavailable`; chỉ được bỏ qua khi đặt `allow_unchecked_retrieval=True`, và việc này được ghi vào trace | 3 test mới: constructor mặc định, reader sai loại, review truyền sẵn; retriever không được gọi |
| F4 | Restore-check có thể xóa DB không do nó tạo | Tên DB và tên file tạm riêng cho mỗi lượt; chỉ xóa sau khi `createdb` của chính lượt đó thành công; không còn bước xóa trước | DB tên cũ `asd_rag_restore_check` có sẵn **vẫn còn**; 2 lượt chạy đồng thời đều đạt; không để lại DB tạm |
| F5 | Tệp bí mật được hướng dẫn tạo không bị git bỏ qua | `*.env` ở mọi thư mục và `secrets/` bị bỏ qua, `*.env.example` vẫn được theo dõi. Trình quét đọc cả blob đã staged (`--staged` dùng cho hook) và gọi git một lần duy nhất | `git check-ignore` đúng cho 6 tên bí mật và 4 tệp mẫu; khóa giả đã staged (trong khi đĩa sạch) bị phát hiện |
| F6 | Ngày ISO không bị che | Thêm dạng `2019-03-12`, `2019/03/12`, `2019.03.12` và `ngày 12 tháng 3 năm 2019`; ghi rõ dạng được che và dạng được giữ | 2 test mới: 9 dạng ngày bị che; tuổi, năm đứng riêng, khoảng năm, tháng/năm, điểm số và cân nặng được giữ |

**Bằng chứng nghiệm thu máy mới** (lưu trong git): [acceptance_20261107_004204/new_machine_bootstrap.log](acceptance_20261107_004204/new_machine_bootstrap.log) cùng script đã chạy. Clone sạch tại `914518c`, venv mới, cluster riêng (`asdboot`, cổng 5435, mật khẩu ngẫu nhiên không được ghi log), khôi phục từ `asd_rag_20261107_000554.dump`, chạy `all` với 167 test. Hash từng hàng của DB gốc trước và sau bài thử **giống nhau**.

Ghi chú trung thực: bước dọn dẹp tự động của script không xóa được volume thử, vì Windows PowerShell 5.1 làm rơi dấu nháy kép trong template `docker inspect`. Volume `asdboot_rag_data` (do chính bài thử tạo, có nhãn `asd_agent=rag-db`, không container nào gắn) được xóa thủ công và ghi cuối log. Bản script lưu kèm đã được sửa để đọc nhãn qua JSON. `tasks.ps1` không có template nào dùng dấu nháy kép lồng nhau.

**Chưa làm được:** cài pre-commit hook bị hệ thống quyền của phiên làm việc từ chối, vì đây là thay đổi lâu dài trong `.git/hooks`. Chủ dự án có thể tự bật bằng `.	asks.ps1 hooks`.

**Thu hẹp tuyên bố:** trình quét bí mật không quét lịch sử commit cũ. Khóa NVIDIA đã hiện nguyên văn trong output một lệnh đọc tệp ở phiên ngày 06/11; đây là quan sát trực tiếp, không có tệp log lưu lại. Việc thu hồi khóa chưa được thực hiện hay kiểm chứng.
