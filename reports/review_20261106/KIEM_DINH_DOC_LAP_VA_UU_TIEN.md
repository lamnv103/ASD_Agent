# ASD_AGENT — Kiểm định độc lập tiến độ và mức sẵn sàng

Ngày: 06/11/2026, múi giờ Asia/Saigon. Đây là rà soát kỹ thuật bằng AI dựa trên workspace hiện tại, không phải nghiệm thu của chuyên gia lâm sàng.

## 1. Kết luận điều hành

**Dự án đã xây dựng được nguyên mẫu nghiên cứu về truy xuất và đọc bằng chứng có khả năng truy nguyên tốt. Chưa đủ điều kiện nghiệm thu như một sản phẩm hỏi–đáp ASD hoàn chỉnh hoặc mở cho người dùng cuối.**

Thành quả có thực: kho nguồn, vector, retriever PostgreSQL, reader v3, kiểm soát trích dẫn và ngân sách context đều tồn tại và chạy được. Khoảng trống lớn nhất để thành sản phẩm là chưa có câu trả lời đầu cuối, chưa có đánh giá độc lập của con người và chưa có bằng chứng vận hành trên câu hỏi mới.

Không xác nhận con số “hoàn thành 35%” trong báo cáo trước: chưa có phạm vi sản phẩm đã chốt, bảng trọng số, ước lượng công việc còn lại hoặc tiêu chí nghiệm thu tổng thể. Cũng chưa đủ dữ liệu để kết luận đúng/chậm tiến độ vì không có lịch cơ sở, nguồn lực và lịch sử hoàn thành được kiểm soát phiên bản trong workspace này.

## 2. Phạm vi và cách kiểm tra

Đã đọc mã nguồn chính trong `rag/`, script đánh giá, kiểm thử, cấu hình, nhãn tham chiếu và báo cáo cũ; chạy kiểm thử hiện có, kiểm tra DB read-only, tính lại xếp hạng từ vector cache và phát lại 23 trace v3. Không gọi provider API; không thay đổi mã chạy chính, nguồn, vector hay cấu hình.

Bằng chứng của lượt kiểm định cuối:

- [audit.json](audit_20261106_210235_872111/audit.json): health, số liệu truy xuất, replay, lịch sử lỗi và thời gian từng request.
- [rankings.json](audit_20261106_210235_872111/rankings.json): từng câu hỏi, bộ dữ liệu, nguồn kỳ vọng và hạng nguồn.
- [audit_project.py](audit_project.py): script tái lập, chỉ ghi vào thư mục audit mới. Cache thiếu sẽ dừng, không lấy khóa gọi API.

Lượt audit đầu được giữ tại `audit_20261106_210129_048307`; lượt cuối sửa cách khử trùng telemetry từ hash nội dung trả về sang `request_id`, tránh gộp nhầm hai request có cùng câu trả lời. Dùng số liệu lượt cuối khi đối chiếu.

Kiểm thử chạy trực tiếp trong phiên này:

| Kiểm tra | Kết quả mới | Ý nghĩa |
|---|---|---|
| `unittest discover -s tests -v` | 115/115 đạt, không skip | Các ràng buộc kỹ thuật đã kiểm tra tiếp tục hoạt động; có kiểm tra DB thật |
| `unittest discover -s scripts/embedding -p 'test_*.py'` | 17/17 đạt | Kiểm thử module embedding đạt; không phải nhúng lại qua provider |
| `unittest discover -s scripts/source_library -p 'test_*.py'` | Lỗi import `bs4` | Không chạy được 17 phương thức test trong module nguồn |
| Health PostgreSQL | 33 tài liệu, 33 vector, 1536 chiều, read-only | Đúng collection và embedding space đã ghim |
| Replay v3 | 23/23 khớp các trường assessment/context/policy được đối chiếu | Khả năng tái lập từ cache; không phải 23 câu mới |
| Tính toàn vẹn | Snapshot DB và 53 tệp trong danh sách bảo vệ không đổi | Giữ nguyên baseline được đối chiếu trong lượt audit |

Lệnh chạy tại thư mục gốc, PowerShell:

```powershell
$env:PYTHONPATH='.'
./.venv-embedding/Scripts/python.exe -B -m unittest discover -s tests -v
./.venv-embedding/Scripts/python.exe -B -m unittest discover -s scripts/embedding -p 'test_*.py'
./.venv-embedding/Scripts/python.exe -B -m unittest discover -s scripts/source_library -p 'test_*.py'
./.venv-embedding/Scripts/python.exe -B reports/review_20261106/audit_project.py
```

Không chạy lại `verify_reader_v3.py` trong lượt này vì script ghi đè `final_tests.txt`, `verification.json`, `after.json` của báo cáo cũ. Xác nhận tác dụng phụ tại các dòng 103 và 110 của script. Replay mới dùng hàm so sánh có sẵn nhưng lưu kết quả riêng. Chưa tái chạy độc lập toàn bộ 20 replay v2 và 30 phép so thứ hạng của verifier cũ; không trình bày số đó như kết quả mới của lượt này.

## 3. Những gì dự án đã đạt được

| Hạng mục | Thành quả đã có | Giới hạn nghiệm thu |
|---|---|---|
| Kho tri thức | 33 Markdown trong tập chính; 7 bản chờ xử lý riêng | Số tài liệu không chứng minh phủ đủ nhu cầu người dùng |
| Embedding và DB | Mỗi tài liệu một vector; kiểm tra hash nội dung, metadata và vector | Chưa kiểm chứng toàn bộ quá trình dựng lại trên máy sạch |
| Truy xuất | Exact cosine, đọc nguyên văn, cấu hình provider/space nhất quán | Có câu nguồn đúng ở hạng 19–20; chưa có đánh giá rộng |
| Reader v3 | Tách nhu cầu, giữ mệnh đề có/không, chọn ID thật, kiểm tra liên kết nhu cầu–đoạn | Diễn giải vẫn do model; chưa có người thẩm định độc lập |
| Context | Tokenizer được ghim; giới hạn budget; giữ đoạn hỗ trợ và điều kiện | Chưa đo chất lượng câu trả lời sau khi dùng context |
| Truy nguyên | Offset, hash, nguồn và passage ID được kiểm tra; test chặn ID giả và nguồn sai | Trích dẫn tồn tại không đồng nghĩa kết luận được nguồn hỗ trợ đúng |
| Kiểm thử | 132 test đã chạy đạt qua hai nhóm | Pipeline nguồn còn lỗi import; chưa có kiểm thử sản phẩm đầu cuối |

Đáng giữ nhất là kiểm soát xuất xứ, tách lỗi thực thi khỏi kết luận thiếu bằng chứng, kiểm tra phủ nhu cầu và giữ các run lỗi. Đây là tài sản kỹ thuật có thể tiếp tục phát triển.

## 4. Những kết luận của báo cáo trước cần điều chỉnh

### 4.1. Chỉ số truy xuất bị thiếu nhãn và đếm lặp

`scripts/evaluation/diagnose_retrieval_offline.py:38` không đọc trường `references` của bộ retrieval_v1. Vì vậy, 27 câu có nguồn của bộ này không được tính vào mẫu số có nhãn. Script khử trùng theo `(setname, qid)`, nên câu H05 xuất hiện trong hai bộ vẫn được tính hai lần.

| Cách tính | Mẫu có nhãn nguồn | Hit@1 | Hit@5 | MRR |
|---|---:|---:|---:|---:|
| retrieval_v1 riêng | 27 | 66,7% | 100% | 0,801 |
| Năm bộ reader, giữ từng lượt theo bộ | 34 | 64,7% | 91,2% | 0,758 |
| Cả sáu bộ, giữ từng lượt theo bộ | 61 | 65,6% | 95,1% | 0,777 |
| Khử trùng câu hỏi chính xác, hợp nguồn tham chiếu | 55 | 65,5% | 96,4% | 0,779 |

Có 73 dòng câu hỏi theo bộ nhưng chỉ 67 chuỗi câu hỏi duy nhất; 55 câu duy nhất có nguồn tham chiếu. Hợp nhãn khi khử trùng chỉ phục vụ mô tả, không tạo thành một benchmark độc lập mới. Các bộ từng dùng để phát triển và phân bố nội dung khác nhau, nên ưu tiên xem kết quả riêng từng bộ.

Hai câu hỏi duy nhất trượt top-5: H05, nguồn NIMH ở hạng 19; N02, nguồn NIMH ở hạng 20. Có ba dòng trượt vì H05 bị lặp. Tăng từ top-5 lên top-10 không cứu hai ca này trong dữ liệu hiện tại.

**Không dùng hit@1 để bác bỏ một kết quả hit@5**: đó là hai chỉ số khác nhau. Kết quả 27/27 của retrieval_v1 vẫn đúng trong phạm vi bộ đó, nhưng không chứng minh khả năng tổng quát hóa.

Hit ở đây là có ít nhất một nguồn tham chiếu trong top-k, không phải tìm đủ mọi nguồn cho câu nhiều ý. Nhãn được ghi là không đầy đủ mọi nguồn hợp lệ; thiếu nguồn tham chiếu chưa đủ để kết luận mọi kết quả khác đều sai. Cần chấm recall theo nhu cầu và đọc các nguồn thay thế.

### 4.2. Chưa chứng minh nguyên nhân là vector toàn văn

Tài liệu dài xuất hiện thường xuyên và tương quan độ dài–tần suất không chứng minh cơ chế nhân quả. Vector embedding không được triển khai bằng cách trung bình các vector đoạn trong mã hiện tại. Không đủ cơ sở gọi nó là “trung bình nhiều chủ đề” như một kết quả đã chứng minh.

Có thể thử chỉ mục cấp mục, lexical hoặc rerank, nhưng phải so sánh từng thay đổi trên cùng tập dev. Không áp ngay hybrid + rerank + MMR + boost để rồi không biết yếu tố nào giúp. Giới hạn một nguồn xuất hiện tối đa 25% số câu cũng không phải tiêu chí chất lượng độc lập: một nguồn tốt có thể phù hợp với nhiều câu hỏi.

Giữ 33 vector toàn văn làm baseline. Nếu thử chia mục, tạo chỉ mục thử nghiệm riêng; không coi đề xuất trong báo cáo là quyết định đã được chủ dự án chấp thuận thay đổi nguyên tắc toàn văn.

### 4.3. “22/156 lỗi” là lịch sử phát triển

Đếm lại đúng 23 run, 156 lượt, 22 lỗi: 8 lỗi HTTP/mạng và 14 lỗi context/schema. Dữ liệu trộn phiên bản, câu lặp, chạy lại và cache. **14,1% không phải tỷ lệ lỗi của bản v3 hiện tại khi phục vụ người dùng.** Muốn đo độ tin cậy phải cố định bản build, cấu hình, chính sách retry và tập câu mới.

### 4.4. Có telemetry thời gian thật từng request

112 request phân biệt theo `request_id` có thời gian gốc được lưu: trung vị khoảng 9,88 giây/request, lớn nhất 55,05 giây. Trong 23 kết quả được chọn, tổng thời gian gốc các stage NIM có trung vị 26,72 giây, khoảng 9,71–61,28 giây; số lượt NIM là 1, 3 hoặc 4.

Đây là tổng stage lịch sử, có thể ghép từ cache của những lần khác nhau, chưa gồm đầy đủ embedding và xử lý DB. Không gọi đó là latency đầu cuối. Tuy nhiên, nó cho thấy mục tiêu p95 ≤25 giây của báo cáo trước cần benchmark trước khi cam kết. Trường `elapsed_seconds` 1–2 giây của lượt replay không đại diện câu mới.

### 4.5. Tổng số kiểm thử trong kế hoạch cũ không đúng

Có 115 test trong `tests/`, 17 test embedding và 17 phương thức test nguồn: 149 test dự kiến nếu toàn bộ module tải được, không phải 133. Hiện chỉ xác nhận 132 test đã thực thi đạt; bộ nguồn dừng ở import, chưa được phép tính đạt hoặc kết luận logic xử lý nguồn sai.

## 5. Các vấn đề cần xử lý theo mức ưu tiên

| Mức | Vấn đề và bằng chứng | Ảnh hưởng | Điều kiện đóng |
|---|---|---|---|
| P0 trước pilot | Chưa có câu trả lời đầu cuối; `rag/evidence_pipeline.py:66` luôn `generation_enabled=False` | Chưa hoàn thành tác vụ hỏi–đáp của sản phẩm | Có luồng hỏi → bằng chứng → trả lời → kiểm tra trích dẫn; đánh giá trên câu mới |
| P0 trước pilot | Hàng đợi 33 nguồn: 0 người duyệt được ghi tên, 0 quyết định | Chưa có nghiệm thu độc lập về nội dung | Giao người chịu trách nhiệm; lưu quyết định, phạm vi và các nguồn phải loại |
| P0 trước pilot | Guard intent nằm sau retrieval; `EvidencePipeline.prepare()` gửi câu hỏi tới retriever trước khi reader phân loại | Câu hỏi chứa dữ liệu trẻ có thể đã gửi sang provider embedding và lưu cache trước khi guard chạy | Chốt chính sách dữ liệu; có xử lý đầu vào trước provider/cache, thời hạn lưu và xóa |
| P1 ngay | Lỗi đo lường nhãn/trùng câu; holdout nhỏ và đã được xem | Dễ chọn cải tiến theo chỉ số lệch | Schema nhãn được kiểm tra; báo cáo riêng từng bộ, câu duy nhất và denominator |
| P1 ngay | Thiếu `bs4`; publish bị chặn bởi đường dẫn E: cứng tại `supplement_20261030.py:263` | Chưa dựng lại được pipeline nguồn trong workspace D: | Khai báo dependency đầy đủ, bỏ phụ thuộc vị trí máy sau khi giữ kiểm tra an toàn workspace |
| P1 ngay | Workspace hiện tại không phải Git repo; chưa có lockfile chung | Khó rollback và chứng minh bản build | Có baseline được quản lý phiên bản, dependency tái lập và lệnh kiểm tra chuẩn |
| P1 trước chia sẻ repo | `.env` có mẫu khóa NVIDIA thật; chỉ kiểm tra sự hiện diện, không in giá trị | Rủi ro khi sao chép hoặc đưa vào phiên bản | Mẫu cấu hình không chứa khóa; kiểm tra cả lịch sử/tệp cấu hình trước chia sẻ |
| P1 | H05/N02 trượt nguồn ở hạng 19–20 | Reader không thể đọc nguồn không được truy xuất | Chấm nguồn thay thế, xác nhận root cause và thử cải tiến trên dev |
| P2 | Kiểm tra hash toàn kho lặp lại ở retrieve/read_source | Tốn CPU/DB khi tăng quy mô hoặc đồng thời | Profile trước; giữ integrity theo snapshot phát hành mà không quét lặp vô ích |
| P2 | Verifier ghi đè báo cáo cũ | Mất phân biệt bằng chứng lịch sử với nghiệm thu mới | Mỗi audit có thư mục riêng và checksum đầu vào |

P0 biểu thị điều kiện chặn pilot, không có nghĩa cần triển khai tất cả trong một ngày. Việc giữ khóa ở máy không tự chứng minh khóa đã lộ ra bên ngoài. Báo cáo trước nói khóa “đã hiện trong log”; lượt này không có bằng chứng để xác nhận lịch sử đó. Nếu đã chia sẻ ra ngoài phạm vi tin cậy, cần thu hồi/đổi khóa qua nhà cung cấp; không tự thay khóa trong một lượt review.

Test guard và prompt injection hiện có kiểm tra các tình huống cụ thể. Phân loại intent vẫn do model và một phần phát hiện instruction dựa trên mẫu chuỗi. Chưa thể suy rộng thành bảo đảm chống prompt injection hoặc an toàn đầu cuối. Chưa có bằng chứng rò rỉ thực tế trong lượt kiểm tra này.

## 6. Tiến độ theo mốc nghiệm thu

| Mốc | Trạng thái hiện tại | Bằng chứng còn thiếu |
|---|---|---|
| M1: Kho nghiên cứu truy nguyên được | Đạt một phần lớn về kỹ thuật | Tái lập ingest từ máy sạch; người duyệt nội dung và quyền dùng theo mục đích thực tế |
| M2: Retriever/reader chạy và phát lại được | Đạt trên mẫu kiểm tra hiện có | Chất lượng trên câu mới, người chấm độc lập, độ phủ nhu cầu |
| M3: MVP trả lời đầu cuối | Chưa đạt | Generator, trình bày nguồn, xử lý lỗi và kiểm chứng câu trả lời |
| M4: Pilot có giám sát | Chưa đạt | M3, chính sách dữ liệu, bộ đánh giá và quy trình duyệt lỗi nghiêm trọng |
| M5: Vận hành rộng | Chưa có bằng chứng đạt | Benchmark câu mới/tải, theo dõi lỗi/chi phí, rollback và trách nhiệm vận hành |

Hai góc nhìn cần phân biệt: nếu mục tiêu đợt vừa qua chỉ là xây nền dữ liệu và reader thì đã có thành quả đáng kể; nếu mục tiêu là trợ lý ASD cho người dùng thì phần giá trị đầu cuối vẫn chưa hoàn thành. Không nên lấy số file, số vector hoặc số test thay cho phần trăm hoàn thành sản phẩm.

## 7. Kế hoạch tiếp tục đề xuất

Ưu tiên theo điều kiện hoàn thành; thời lượng cần ước lượng lại sau khi biết người thực hiện và phạm vi MVP. Kế hoạch 8 tuần cũ là giả định, chưa phải lịch giao hàng đã được xác nhận.

| Thứ tự | Việc cụ thể | Đầu ra nghiệm thu | Vai trò cần giao |
|---|---|---|---|
| 1 | Chốt MVP: người dùng, nhóm tuổi, loại câu được hỗ trợ, tình huống chuyển chuyên gia, chính sách dữ liệu | Một trang phạm vi và checklist nghiệm thu được chủ dự án duyệt | Chủ sản phẩm + người phụ trách chuyên môn |
| 2 | Ổn định nền: phiên bản, dependency, đường dẫn, lệnh test, audit ghi riêng | Môi trường sạch chạy được cả ba nhóm test; tổng test được đếm tự động | Kỹ thuật |
| 3 | Sửa quy trình đo; tạo bộ câu mới không nêu tên nguồn, tách dev/test và quản lý quyền xem | Nhãn nguồn/đoạn/nhu cầu có người duyệt; log các lần sử dụng test | Đánh giá + chuyên môn |
| 4 | Điều tra H05/N02, S05/S08; thử từng cải tiến truy xuất trên dev | So sánh với baseline, nguồn hợp lệ được dùng, số nhu cầu được phủ, thời gian và token | RAG + người duyệt |
| 5 | Tạo lát cắt đầu cuối nhỏ cho phạm vi đã chốt, giữ truy nguyên hiện tại | Câu trả lời tiếng Việt có trích dẫn kiểm tra được, thiếu căn cứ thì nêu rõ hoặc dừng | Kỹ thuật + chuyên môn |
| 6 | Đo bản cố định trên câu mới; kiểm tra dữ liệu, lỗi mạng, yêu cầu vượt phạm vi và tấn công | Báo cáo chất lượng/độ trễ/chi phí, danh sách lỗi chặn pilot và người ký nghiệm thu | Kỹ thuật + chủ sản phẩm + chuyên môn |

Chưa cần xây vòng lặp agent nhiều lượt, thay nhiều model hoặc mở rộng hàng loạt tài liệu để chứng minh MVP. Trước hết phải có một luồng đầu cuối đo được trên phạm vi hẹp. Với mọi thử nghiệm retrieval, giữ collection 33 vector làm baseline và ghi rõ tác động của từng thay đổi.

Định nghĩa chỉ số trước khi đặt ngưỡng: tìm được ít nhất một nguồn khác với tìm đủ bằng chứng cho mọi nhu cầu; citation coverage khác với citation correctness; tỷ lệ từ chối đúng phải báo cáo cùng tỷ lệ từ chối sai. Báo cáo mẫu số, nhóm câu và khoảng bất định thay vì chỉ một phần trăm tổng.

**Quyết định review:** tiếp tục phát triển nội bộ; chưa mở pilot người dùng cuối. Mốc tiếp theo nên là môi trường tái lập + đánh giá có người duyệt + một luồng trả lời đầu cuối hẹp. Chỉ nghiệm thu sản phẩm khi có bằng chứng trực tiếp cho tác vụ đó.
