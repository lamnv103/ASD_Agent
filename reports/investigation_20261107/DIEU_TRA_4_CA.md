# Điều tra 4 ca: H05, N02, S05, S08

**Ngày:** 07/11/2026. **Phạm vi:** chỉ dùng dữ liệu đã có trong repo: trace reader v3, vector đã lưu, query cache, tài liệu nguồn. **Không gọi API, không ghi database, không sửa file bị khóa hash.**

**Giới hạn chung:** 18 câu có nhãn của reader v3 đã được dùng trong quá trình phát triển. Nhãn do AI soạn, chưa đầy đủ (`reference_set_exhaustive=false`), chưa có chuyên gia duyệt. Mọi kết luận dưới đây là chẩn đoán kỹ thuật, không phải đánh giá chất lượng y khoa.

Tái lập: `python reports/investigation_20261107/probe_retrieval_offline.py` → `probe_output.txt` / `probe_output.json`.

## Tóm tắt

| Ca | Loại vấn đề | Kết quả hiện tại | Đã xác nhận | Chưa phân xử được | Đề xuất |
|---|---|---|---|---|---|
| H05 | Truy xuất | Reader trả `insufficient`, không bịa nội dung | Nguồn NIMH hạng 19/33. Điểm 20 tài liệu đầu chỉ chênh 0,075. Diễn đạt khác ("vì sao gọi là phổ") đưa NIMH lên hạng 4 | Vì sao embedding toàn tài liệu xếp NIMH thấp với cách hỏi này | Thử truy xuất theo mục + từ khóa trên bộ phát triển (mục 5) |
| N02 | Truy xuất | Reader trả `insufficient`; 2 đoạn ASD-CSV-002 bị đánh giá chỉ là bối cảnh | Nguồn NIMH hạng 20/33. Mục cần tìm chiếm khoảng 7% tài liệu. Thử nghiệm từ khóa không cứu được ca này: mục đúng hạng 46/731 | Liệu `partially_sufficient` dựa trên CSV-002 có chấp nhận được không | Như H05; cần người duyệt CSV-002 |
| S05 | Chọn bằng chứng (không phải lỗi trạng thái) | `sufficient`, hướng trả lời: chưa đủ để kết luận nhân quả hai chiều | Reader dùng đúng nguồn kỳ vọng nhưng khác đoạn. Đoạn được chọn có mâu thuẫn nội tại và có nhắc melatonin. Câu trực tiếp nhất về "hai chiều" không được chọn | Chỉ một tổng quan năm 2014 có đủ để chấm `sufficient` không | Người duyệt chấm; đưa vào bộ ca của tầng G |
| S08 | Khác đoạn tham chiếu (không phải lỗi) | `sufficient`, khớp nhãn | Đoạn tham chiếu được gửi trong context nhưng không được chọn làm bằng chứng. Các đoạn được chọn phân biệt ASI và SBI trực tiếp hơn | Câu trả lời có cần nêu mức bằng chứng của ASI không | Đưa vào bộ ca của tầng G |

**Kết luận chính:** cả 4 ca **không có ca nào reader bịa nội dung**. H05 và N02 là lỗi truy xuất; reader xử lý thận trọng đúng hướng khi không có nguồn. S05 và S08 là `reference_span_overlap_used=False` nhưng **không phải lỗi trạng thái**. Chúng cho thấy việc chọn đoạn còn chưa tối ưu, và tầng G sẽ gặp rủi ro thật nếu viết lại các đoạn này không cẩn thận.

## 1. H05: "Hai trẻ đều được chẩn đoán tự kỷ có nhất thiết có biểu hiện, điểm mạnh và nhu cầu hỗ trợ giống nhau không?"

**Bằng chứng**

- Câu tham chiếu: NIH-NIMH-ASD-2025 [1289–1423] *"Autism is known as a 'spectrum' disorder because people with autism have a range of characteristics, needs, strengths, and challenges."*
- Truy xuất dense: NIMH đứng hạng **19/33**. Top 5: PMC13005892 (tổng quan về tự kỷ ở Việt Nam), PMC6487529 (tỷ lệ mắc ở miền Bắc Việt Nam), CSV-088 (đồng mắc tâm thần), CSV-002 (đánh giá ASD), PMC11754701 (Social Stories trong trường học).
- Điểm cosine hạng 1 là 0,365, hạng 20 là 0,290 (chênh 0,075). Phân biệt giữa các tài liệu rất yếu.
- Một câu gần nghĩa trong query cache, "Vì sao gọi tự kỷ là phổ? Mọi trẻ tự kỷ có biểu hiện giống nhau không?", đưa NIMH lên **hạng 4**. Câu H05 không có từ "phổ".
- Reader v3: 30 đoạn trích từ 5 tài liệu, **0 bằng chứng được chọn**, trạng thái `insufficient`, chính sách `explain_insufficient_evidence`. Reader v2 trước đó dùng CSV-002 và trả `sufficient`, nên v3 thận trọng hơn.
- Trong top 5, câu gần nhất là CSV-002 *"profiling individual strengths and challenges"*. Đây là mục tiêu của một lượt đánh giá, không trả lời trực tiếp câu hỏi.

**Nguyên nhân đã xác nhận:** nguồn trả lời trực tiếp không nằm trong top 5, nên reader không thể đọc. Kết quả `insufficient` là hành vi an toàn, đúng với những gì reader nhận được.

**Đã loại trừ:**

- Văn bản không bị cắt khi tạo embedding: cả 33 tài liệu đều `truncate=NONE`, số ký tự gửi bằng số ký tự gốc.
- NIMH không phải tài liệu dài. Với 14.482 ký tự, nó thuộc nhóm ngắn nhất. Giả thuyết "vector tài liệu dài bị trung bình hóa" không áp dụng theo nghĩa độ dài.

**Chưa xác nhận (cần API trên bộ phát triển):**

- (a) Vector toàn tài liệu của một trang tổng quan nhiều chủ đề (chẩn đoán, điều trị, nghiên cứu, người lớn) làm loãng câu định nghĩa "phổ".
- (b) Câu hỏi tiếng Việt bị hút về các tài liệu liên quan Việt Nam. Xem mục 5.

## 2. N02: "Khi giáo viên nhận thấy trẻ tuổi đi học khó hiểu giọng điệu, nét mặt hoặc lối nói bóng, tài liệu mô tả việc nhận diện và đánh giá tiếp theo ra sao?"

**Bằng chứng**

- Đoạn tham chiếu: NIMH mục *"Diagnosis in older children and adolescents"* [7630–8601]. Đoạn này mô tả giáo viên thường nhận ra trước, nhóm giáo dục đặc biệt đánh giá ban đầu, rồi giới thiệu tới nhân viên y tế. Khoảng 970/14.482 ký tự, tức khoảng 7% tài liệu.
- Truy xuất dense: NIMH đứng hạng **20/33**. Top 5: CSV-002, PMC13005892, PMC6487529, CSV-091, PMC11754701.
- Reader chọn 2 đoạn của CSV-002 [24094–25326] và [25328–26736] về đánh giá toàn diện. Đoạn sau có nhắc *"informant report from various sources (e.g., caregiver, teacher, self-report)"*. Verifier của reader chấm cả hai là `context_only`, nên kết quả là `insufficient`.

**Nguyên nhân đã xác nhận:** nguồn tham chiếu nằm ngoài top 5. Đoạn cần tìm chỉ là một phần nhỏ trong tài liệu.

**Chưa phân xử:** CSV-002 mô tả quy trình đánh giá chung, có nhắc báo cáo từ giáo viên. Nó có đủ cho trạng thái `partially_sufficient` không? Hay reader đúng khi chỉ coi là bối cảnh? Việc này cần **người duyệt**. Nhãn hiện cho phép cả `sufficient` và `partially_sufficient`.

**Thử nghiệm từ khóa không cứu được N02:** tài liệu NIMH vào top 5 qua mục *"Diagnosis in adults"*, tức trúng nhầm mục. Mục đúng chỉ đứng hạng 46/731 mục.

## 3. S05: "Khó ngủ có liên quan đến hành vi ở trẻ tự kỷ, nhưng đã đủ để kết luận quan hệ nhân quả hai chiều chắc chắn chưa?"

**Bằng chứng**

- Nguồn: ASD-OA-PMC4271434, tổng quan xuất bản 11/12/2014. Đây là **nguồn duy nhất** được dùng.
- Đoạn tham chiếu [21651–23288] kết thúc bằng: *"limited research has been conducted on the bi-directional relationship between sleep and behavior in these individuals."* Đây là câu trả lời trực tiếp nhất cho phần "hai chiều". **Reader không chọn đoạn này.**
- Reader chọn hai đoạn:
  - [38221–40936] *Researched areas*. Đoạn này đồng thời nói *"clear uni-directional relationships"* và *"Given the bi-directional relationship between challenging behaviors and sleep disturbance…"*. Tức là chính nguồn dùng "hai chiều" như điều đã biết. Đoạn này cũng có câu *"melatonin is an effective sleep treatment for children with autism"*.
  - [45616–46864] *Conclusions*: *"these conclusions are still premature and require further investigation"*.
- Plan chỉ có 1 nhu cầu (n1, kiểm tra mệnh đề "đã đủ để kết luận nhân quả hai chiều"). Phần tiền đề "có liên quan" không được tách thành nhu cầu riêng.
- Kết quả: `sufficient` theo hướng bác bỏ mệnh đề (`direct_refutation`), khớp nhãn (cho phép `sufficient` hoặc `partially_sufficient`).

**Kết luận đã xác nhận:** trạng thái và hướng trả lời ("chưa đủ để kết luận") đúng với nguồn. `reference_span_overlap_used=False` vì reader chọn đoạn khác trong cùng nguồn kỳ vọng, không phải vì dùng sai nguồn.

**Rủi ro cho tầng G (quan trọng):**

1. Đoạn được chọn có mâu thuẫn nội tại. Nếu viết lại thiếu cẩn thận, câu trả lời có thể khẳng định "có quan hệ hai chiều", tức là đổi mức chắc chắn.
2. Đoạn có câu về melatonin. Câu trả lời có thể kéo thêm thông tin thuốc mà người hỏi không yêu cầu.
3. Chỉ một nguồn năm 2014. Câu trả lời phải nói rõ điều này.

**Chưa phân xử:** một tổng quan năm 2014 có đủ để chấm `sufficient` cho câu hỏi "bằng chứng đã đủ chưa" không? Hay nên là `partially_sufficient` kèm ghi chú về độ cũ? Cần **người duyệt**.

## 4. S08: "Các hoạt động kích thích cảm giác có phải đều giống phương pháp tích hợp cảm giác đã được nghiên cứu cho trẻ tự kỷ không?"

**Bằng chứng**

- Nguồn: PMC6590432 (tổng quan hệ thống về ASI, 2018) và PMC12658592 (tổng quan về can thiệp dựa trên cảm giác SBI, 2015–2024, xuất bản 2025).
- Đoạn tham chiếu [5465–8223] nằm **trong khối context đã gửi** [4216–15382], nhưng không được chọn làm bằng chứng. Đoạn này nói về mức bằng chứng của ASI: *"strong evidence for positive outcomes on individual goals, moderate evidence… emerging but insufficient evidence for… play, sensory-motor skills, language, and social skills"*.
- Reader chọn 5 bằng chứng, đều `direct` / `refutes`. Các đoạn này định nghĩa ASI (cá nhân hóa, trẻ chủ động, trong bối cảnh chơi) và phân biệt với SBI (người lớn áp dụng kích thích theo cùng một quy trình cho mọi trẻ).
- Kết quả: `sufficient`, khớp nhãn (chỉ chấp nhận `sufficient`).

**Kết luận đã xác nhận:** không phải lỗi. Câu hỏi hỏi "có giống nhau không"; các đoạn được chọn trả lời việc này trực tiếp hơn đoạn tham chiếu.

**Hệ quả cho tầng G:** đặc tả v0 chỉ cho trích dẫn các bằng chứng đã được duyệt. Vì vậy câu trả lời S08 sẽ **không** nêu được mức bằng chứng của ASI, dù đoạn đó có trong context. Đây là đánh đổi chủ ý: chặt hơn nhưng có thể thiếu ý. Rủi ro khác: đoạn i1 mô tả ASI theo hướng tích cực, nên câu trả lời có thể biến thành khuyến nghị ASI. Nhãn đã ghi giới hạn "không khuyến nghị mọi hoạt động cảm giác".

**Chưa phân xử:** câu trả lời đạt có bắt buộc nêu mức bằng chứng của ASI không? Cần **người duyệt**. Nếu bắt buộc, phải xem lại quy tắc "chỉ trích dẫn bằng chứng đã duyệt".

## 5. Phát hiện chung về truy xuất (đã đo offline, chưa có kết luận nhân quả)

**Hub tài liệu.** Có 67 truy vấn trong cache, tức 335 vị trí top 5; trung bình mỗi tài liệu chiếm 10,2 vị trí. Ba tài liệu chiếm 84/335 vị trí (25%): PMC6487529 (30), CSV-002 (27), PMC13005892 (27). **Hai tài liệu duy nhất nhắc tới Việt Nam cũng chính là hai hub lớn nhất** (65 và 305 lần nhắc). Hai tài liệu không bao giờ vào top 5: CDC-ASD-TREATMENT và PMC10018050.

- Bỏ hai tài liệu Việt Nam ra thì NIMH chỉ lên hạng 17 (H05) và 18 (N02). Hub **không đủ** để giải thích hai ca trượt.
- Giả thuyết "câu hỏi tiếng Việt bị hút về tài liệu liên quan Việt Nam" phù hợp với dữ liệu nhưng **chưa được kiểm chứng**. Cách thử: embed bản tiếng Anh của cùng câu hỏi, hoặc embed `search_terms` của plan, rồi so thứ hạng. Việc này cần gọi API Cohere cho truy vấn.

**Thử nghiệm từ khóa trên `search_terms` tiếng Anh của plan (BM25, chỉ để thăm dò).**

- Plan của reader v3 đã sinh `search_terms` tiếng Anh.
- Guard mới chạy plan **trước** truy xuất. Vì vậy dùng các term này cho truy xuất không làm tăng số lượt gọi.

| Cách | Top 5 có nguồn kỳ vọng (18 câu) | Riêng 11 câu có term không chứa tên nguồn |
|---|---|---|
| Dense hiện tại (Cohere, toàn tài liệu) | 16 | 9 |
| BM25 toàn tài liệu | 16 | 9 |
| BM25 theo mục tài liệu (heading) | 18 | 11 |

Không được đọc bảng này như một kết quả cải tiến, vì:

1. 7/18 câu có tên nguồn (NIMH, NIDCD, CDC) trong term do câu hỏi viết "Theo NIMH…", làm kết quả từ khóa đẹp hơn thực tế.
2. N02 trúng nhầm mục.
3. Mục "References" lọt vào top, gây nhiễu.
4. Chỉ đo theo tài liệu, chưa đo đúng đoạn, hit@1 hay tác động lên reader.
5. Đây là bộ phát triển, nhãn chưa đầy đủ. Ví dụ PMC12468522 đứng đầu ở H05 có câu "ASD is a heterogeneous neurodevelopmental condition…", có thể là nguồn hợp lệ nhưng chưa có nhãn.

Điểm có giá trị: H05 tìm đúng mục *"What is autism spectrum disorder?"* chứa câu tham chiếu (hạng 2). Hướng **truy xuất theo mục + kết hợp từ khóa từ plan** đáng thử nghiêm túc.

## 6. Đề xuất xử lý

Song song với tầng G; không đổi collection 33 vector đang dùng.

1. **Không sửa nhãn, không thêm nguồn ngoài top 5 để làm đẹp kết quả.** Giữ H05 và N02 là ca trượt đã biết.
2. **Chuyển ba câu hỏi phân xử cho người duyệt:**
   - N02: CSV-002 có đủ cho "một phần" không.
   - S05: một tổng quan 2014 có đủ cho `sufficient` không.
   - S08: có bắt buộc nêu mức bằng chứng ASI không.
3. **Đưa S05 và S08 vào bộ ca cho tầng G**, kèm lỗi cần bắt:
   - đổi "chưa đủ kết luận" thành "có quan hệ hai chiều";
   - thêm melatonin khi không được hỏi;
   - biến ASI thành khuyến nghị;
   - bỏ năm 2014 / chỉ có một nguồn.
4. **Thử nghiệm truy xuất (cần API, trên bộ phát triển, mỗi lần một thay đổi):**
   - (a) Embed `search_terms` tiếng Anh thay cho câu hỏi tiếng Việt để kiểm tra giả thuyết ngôn ngữ/hub.
   - (b) Chỉ mục theo mục tài liệu (bỏ mục References) + kết hợp BM25.
   - Đo hit@1/hit@5 theo tài liệu và theo đoạn, đo tác động lên trạng thái của reader. Phải loại các câu có tên nguồn khỏi phép so sánh chính.
5. **Bộ đánh giá sau này** cần câu hỏi không nêu tên nguồn. Hiện 7/18 câu có tên nguồn đi thẳng vào term tìm kiếm.

## File trong thư mục này

| File | Nội dung |
|---|---|
| `probe_retrieval_offline.py` | Script thăm dò offline, chỉ đọc file trong repo |
| `probe_output.txt`, `probe_output.json` | Kết quả: tần suất top 5, thứ hạng dense của H05/N02 và câu gần nghĩa, thử nghiệm BM25 |
