# Review gói nền tảng và bàn giao ngày 07/11/2026

Đối tượng: chủ dự án và nhóm kỹ thuật. Bản được kiểm tra: `2643b2e`; baseline `347f77b`, tag `baseline-v3-20261102`. Đây là review kỹ thuật bằng AI, không phải duyệt chuyên môn cho MVP.

**Kết luận: các kiểm tra được công bố chạy đạt trên workspace hiện tại; hai backup khôi phục đúng dữ liệu. Chưa nghiệm thu trọn vẹn khả năng bàn giao sang máy mới và tính bắt buộc của guard ở API Python. Cần sửa năm vấn đề P1 bên dưới trước khi đóng gói nền tảng.**

## 1. Findings theo mức ưu tiên

### F1 — P1: Config DB theo máy bị ghim hash, làm hỏng hướng dẫn dựng trên máy mới

Vị trí: `scripts/dev/check_pins.py:27–38`; `reports/evidence_context_20261031_175633/protected_code_before.json:7`; `SETUP.md:38`.

`deployments/database.env` được Git bỏ qua nhưng SHA-256 toàn bộ file nằm trong cả ba manifest bảo vệ. `tasks.ps1 all` chạy `pins` đầu tiên. Người nhận repo tạo file riêng theo hướng dẫn, thay mật khẩu hoặc endpoint hợp lệ, sẽ bị kiểm tra hash từ chối dù trỏ tới cùng dữ liệu đã phục hồi đúng.

Đã đối chiếu: file ví dụ không khớp hash bị ghim. Thay bất kỳ byte nào trong file cấu hình cá nhân cũng làm sai hash. Clone sạch chạy cùng DB với bản sao nguyên byte config cũ chỉ chứng minh một trường hợp hẹp; không chứng minh quy trình cấu hình cho một máy khác hoạt động.

Đề nghị: phân biệt tính toàn vẹn nội dung/embedding/cấu hình chức năng với thông tin kết nối cục bộ. Thiết kế baseline phát hành mới cho phép cấu hình kết nối riêng; giữ nguyên bằng chứng lịch sử để kiểm định ở bản cũ, không sửa hash cũ chỉ để làm kiểm tra xanh.

Nghiệm thu lại: cấu hình mật khẩu khác trên DB thử nghiệm độc lập, cùng corpus/vector đã phục hồi, vẫn vượt qua kiểm tra tính toàn vẹn và các kiểm tra hiện hành được thiết kế cho bản mới.

### F2 — P1: Quy trình máy mới thiếu bước tạo external volume

Vị trí: `deployments/compose.rag.yml:34–36`; `tasks.ps1:110–122`; `SETUP.md:59`.

Compose khai báo volume `external: true`. Nhánh tạo mới của `db-up` chỉ gọi compose, không tạo volume; hướng dẫn máy mới cũng không có bước này. Trên Docker chưa có `deployments_carobud_rag_data`, quy trình dừng trước khi tạo được database. Image đúng và container hiện tại khỏe không chứng minh nhánh bootstrap này hoạt động.

Đề nghị: thêm bước bootstrap rõ ràng cho volume chưa tồn tại và tách hai đường đi: khởi động lại DB sẵn có, dựng DB mới từ backup. Hướng dẫn phục hồi phải nói rõ backup được chuyển riêng vì `backups/` không nằm trong Git; kiểm tra cả role/quyền và cấu hình đăng nhập trên cluster mới.

Nghiệm thu lại: chạy trên Docker context/cluster thử nghiệm riêng chưa có container hoặc volume của dự án; tạo mới, phục hồi, health và verify đạt. Không xóa volume thật để mô phỏng.

Finding này dựa trên luồng mã và cấu hình; lượt review không thử compose trên Docker trống. Việc phục hồi ở mục 2 chỉ dùng database mới trong cluster hiện tại.

### F3 — P1: Guard bỏ qua phân loại khi thiếu reader hoặc có review truyền sẵn

Vị trí: `rag/guarded_pipeline.py:50–58`.

Nếu không có `AtomicNeedsReader`, hoặc caller truyền `review`, `decision` thành `not_checked_reader_has_no_plan_stage` nhưng luồng vẫn gọi `retriever.retrieve()`. Constructor kế thừa mặc định không có semantic reader. Vì vậy, người tích hợp chỉ tạo `GuardedEvidencePipeline()` rồi gọi `prepare()` có thể gửi yêu cầu cá nhân tới retriever trước khi phân loại.

Đã tái hiện bằng câu tổng hợp, retriever giả và tokenizer fixture: `retrieval_called=true`, `guard_decision=not_checked_reader_has_no_plan_stage`. Không gọi provider hoặc lưu dữ liệu cá nhân thật.

CLI `python -m rag.prepare_evidence` có gắn reader v3 đúng, nên kết quả replay 18/5 vẫn hợp lệ. Finding nằm ở hợp đồng của lớp Python và khả năng tích hợp, không phải bằng chứng CLI đang bỏ qua guard.

Đề nghị: mặc định thiếu thành phần phân loại thì dừng trước retriever; nếu cần bỏ qua để replay/test, yêu cầu chế độ được bật tường minh. Tài liệu và trace phải phân biệt rõ chế độ đó.

Nghiệm thu lại: khởi tạo mặc định, reader sai loại, review truyền sẵn và lỗi planner đều không tự động rơi xuống retriever trong chế độ phục vụ thông thường. Kiểm tra cả việc không ghi query cache. Bổ sung ca này vào bộ test thay vì chỉ kiểm cấu hình đã gắn reader đúng.

### F4 — P1: Restore-check có thể xóa một DB không do lần chạy hiện tại tạo

Vị trí: `tasks.ps1:140–152`.

Lệnh dùng tên cố định `asd_rag_restore_check`, gọi `dropdb --if-exists` trước khi tạo và luôn gọi lại trong `finally`. Nếu DB tên đó đã tồn tại vì mục đích khác, nó bị xóa; hai lần kiểm tra chạy đồng thời cũng có thể phá DB của nhau. Không tác động trực tiếp tên `asd_rag`, nhưng vẫn là hành vi xóa ngoài tài nguyên mà lần chạy chắc chắn sở hữu.

Đề nghị: tên duy nhất theo mỗi run; không xóa DB có sẵn; chỉ cleanup sau khi xác nhận `createdb` của chính run thành công. Dùng tên file tạm riêng tương ứng.

Nghiệm thu lại: một DB có sẵn không bị đụng tới; hai lượt chạy đồng thời độc lập; lỗi tại từng stage vẫn không xóa tài nguyên của run khác. Không cần tạo DB chứa dữ liệu thật để kiểm chứng.

Trong lượt review, không chạy nhánh xóa cố định này. Hai backup được kiểm bằng script riêng dùng UUID và cờ xác nhận đã tạo DB thành công.

### F5 — P1: Tệp bí mật được hướng dẫn tạo chưa được Git bỏ qua

Vị trí: `.env.example:1–2`, `.gitignore:2–6`, `SETUP.md:45`.

`.env.example` khuyên sao chép sang một tệp bị Git bỏ qua, ví dụ `secrets.env`. Nhưng các mẫu hiện tại chỉ gồm `.env`, `.env.*`, `deployments/*.env` và một số tên riêng, không có `*.env` toàn cục hoặc `secrets.env`. Đã xác nhận `git check-ignore --no-index secrets.env` không coi tên này là bị bỏ qua.

Nếu người nhận làm theo ví dụ rồi dùng `git add .`, tệp có thể vào index. Secret scanner có thể phát hiện một số định dạng khóa nếu được chạy, nhưng chưa được gắn thành chốt bắt buộc của mọi commit. Lượt review không tạo tệp chứa khóa và không phát hiện vụ lộ thực tế.

Đề nghị: thống nhất một vị trí/tên tệp bí mật thực sự bị bỏ qua, cập nhật cả ví dụ và tài liệu, đồng thời giữ các tệp `.env.example` được theo dõi như chủ đích.

Nghiệm thu lại: mọi tên tệp bí mật được hướng dẫn đều được `git check-ignore` xác nhận; không đi vào index khi thêm tệp bình thường; tệp mẫu vẫn có trong repo.

### F6 — P2: Che ngày chưa bao phủ định dạng ISO

Vị trí: `rag/input_guard.py:29–30`.

Regex chỉ nhận ngày có thứ tự ngày/tháng/năm. Đầu vào tổng hợp `Con tôi sinh 2019-03-12, email me@example.com.` được che email nhưng giữ nguyên ngày ISO. Ngày này tiếp tục tới provider và cache nếu luồng đi tiếp.

Đề nghị: định nghĩa rõ các định dạng hỗ trợ, bổ sung dạng năm-tháng-ngày phổ biến và kiểm tra tránh che nhầm số liệu không phải ngày. Nếu chưa hỗ trợ, thu hẹp tuyên bố “che ngày tháng” thành đúng các định dạng thực tế; vẫn phải coi đây là giảm dữ liệu định danh, không phải ẩn danh đầy đủ.

Nghiệm thu lại: dữ liệu tổng hợp theo từng định dạng chỉ để lại placeholder trong mọi payload, cache và trace; các con số cần thiết như tuổi/năm tài liệu được giữ theo chính sách đã chốt.

## 2. Những gì đã kiểm tra và xác nhận đạt

Lệnh `powershell -NoProfile -ExecutionPolicy Bypass -File .\tasks.ps1 all` chạy hoàn tất với exit 0 và `ALL CHECKS PASSED`. Lệnh trực tiếp `./tasks.ps1 all` ban đầu bị Execution Policy của phiên hiện tại chặn; chỉ dùng tùy chọn cho tiến trình, không thay đổi policy Windows.

| Tuyên bố | Kết quả kiểm tra độc lập |
|---|---|
| Git baseline rồi 4 commit | Đúng; tag trỏ baseline, sau đó 4 commit được nêu |
| 157/157 test, 0 fail/skip | Đúng: 123 + 17 + 17, 0 fail/error/skip |
| 61 file ghim hash | Đúng, pins PASS |
| Collection 33/33, 1536 chiều | Health PASS; verifier xác nhận snapshot không đổi |
| 132 tệp nguồn không đổi | Verifier kiểm tra đạt |
| Bốn verifier | Đều PASS; 30 truy vấn gốc, replay v2/v3 và guard chạy được |
| Guard: 18 câu giữ hành vi, 5 câu chặn trước retrieval | Đúng trong các câu replay, với reader v3 đã gắn đúng |
| Không ghi đè báo cáo cũ | Code đã chuyển đầu ra sang thư mục mới; Git không ghi nhận thay đổi các file lịch sử sau kiểm tra |
| Script retrieval đã sửa | Chạy `diag`: 73 dòng, 67 câu duy nhất, 55 có nhãn; hit@5 0,964; H05/N02 hạng 19/20 |
| Hai backup | Cả hai checksum khớp, phục hồi và đối chiếu hàng ở 4 bảng đạt |
| DB dùng thật không đổi khi kiểm backup | Hash 4 bảng trước/sau khớp; chỉ xóa DB UUID vừa tạo |
| Secret scan | PASS theo phạm vi scanner hiện tại; không phải chứng nhận không có bí mật ở mọi nơi |

Backup được phục hồi vào hai DB tên ngẫu nhiên, mỗi DB mới trong cluster đang có. Bốn bảng khớp: collections 3 hàng, documents 150 hàng, embedding_spaces 2 hàng, embeddings 40 hàng. Các số lớn hơn 33 do bao gồm collection cũ.

Không tự dựng thêm clone/venv trong lượt review này. Tuyên bố clone sạch trước đó được đọc từ bàn giao, nhưng không có log clone/commit/môi trường được lưu trong thư mục bàn giao để đối chiếu độc lập. Cũng chưa kiểm chứng bootstrap trên máy Windows hoặc PostgreSQL cluster hoàn toàn mới.

## 3. Bằng chứng của lượt review

- Tests: `reports/verification_runs/tests_20261107_002316_856716/`.
- Evidence/context: `reports/verification_runs/evidence_context_20261107_002326_816829/verification.json`.
- Reader v2: `reports/verification_runs/semantic_reader_20261107_002347_516648/verification.json`.
- Reader v3: `reports/verification_runs/reader_v3_20261107_002411_448880/verification.json`.
- Guard: `reports/verification_runs/guarded_pipeline_20261107_002510_453139/verification.json`.
- Retrieval: `reports/verification_runs/retrieval_diagnostics_20261107_002657_649774/summary.json`.
- Reproducer và backup: `reports/verification_runs/review_foundation_20261107/`, gồm `probes.json`, `backup_review.json` và hai script đã chạy.

Thư mục `verification_runs` bị Git bỏ qua: nếu cần bàn giao bằng chứng, phải đóng gói hoặc lưu riêng theo quy trình, không chỉ đưa đường dẫn cục bộ.

## 4. Phạm vi MVP và tài liệu

`docs/MVP_SCOPE_DRAFT.md` làm đúng vai trò bản nháp: xác định người dùng, nhóm A–D, hành vi ngoài phạm vi, cấu trúc trả lời và 8 quyết định cần chốt. Chưa có chữ ký/phê duyệt; không được trình bày như phạm vi đã nghiệm thu. Tầng trả lời và xử lý khẩn cấp chưa tồn tại được ghi rõ.

Trước khi chốt bộ 30 + 50, cần làm rõ thêm trong các quyết định hiện có: thời hạn lưu cache, quy trình xóa, ai được xem trace, và cách xử lý thông tin cá nhân mà guard không nhận diện. Quyết định độ trễ nên là ngưỡng cần đo; streaming hoặc đổi model là phương án kỹ thuật cần thử, không phải tiêu chí nghiệm thu tự thân.

Một số câu trong tài liệu cần thu hẹp:

- “Khóa đã hiện trong log ngày 06/11”: lượt review này không có log chứng minh lịch sử đó. Phân biệt xác nhận có khóa cục bộ với xác nhận đã lộ. Việc thu hồi khóa chưa được kiểm chứng trong lượt này.
- “Gitignore chặn `*.env`”: quy tắc hiện tại chặn các vị trí cụ thể; không có mẫu toàn cục `*.env`. Một file như `secrets.env` ở thư mục gốc không được chính các quy tắc `.env`/`.env.*` bảo vệ. Secret scan là lớp bổ sung nhưng không thay cho mô tả chính xác.
- Secret scanner đọc file ở working tree, không đọc blob trong index hoặc lịch sử Git. Vì vậy, không nên nói đã kiểm nội dung staged/commit lịch sử. Scanner còn bỏ qua một số định dạng và có ngoại lệ placeholder.
- SETUP cần có mục Execution Policy hoặc lệnh chạy theo tiến trình vì lệnh được ghi hiện không chạy trực tiếp trong phiên review.

## 5. Điều kiện đóng gói việc

1. Sửa F1–F5, giữ kiểm tra bảo vệ dữ liệu và lưu bằng chứng của release mới nếu thay manifest.
2. Xử lý F6 hoặc thu hẹp đúng tuyên bố và phạm vi bảo vệ dữ liệu.
3. Chạy lại các kiểm tra bị ảnh hưởng; lưu commit, môi trường và đường dẫn log có thể bàn giao.
4. Kiểm chứng một đường đi bootstrap trên hạ tầng thử nghiệm riêng chưa có volume/cluster của dự án, sử dụng thông tin đăng nhập khác máy hiện tại.
5. Chủ dự án và chuyên môn chốt bản MVP. Có thể tiếp tục chuẩn bị rubric/taxonomy song song, nhưng chưa đóng băng bộ test cuối theo một phạm vi chưa được duyệt.

Lượt review chỉ thêm báo cáo và công cụ kiểm định riêng trong thư mục bằng chứng; không sửa mã triển khai, test hiện hành, lockfile, manifest, khóa hoặc cấu hình hệ thống.
