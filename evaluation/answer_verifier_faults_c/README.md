# Bộ ca C: `answer_verifier_faults_c`

**Trạng thái:** `chua_duyet`. Nhãn phát triển (`team_draft`), soạn ngày 08/11/2026 cùng thiết kế C; nhóm đã duyệt bằng đối chiếu nguồn (xem cuối bảng). Bộ này báo cáo riêng, không gộp với v1 hay bộ bổ sung. Không dùng câu hỏi mới: chỉ dùng trace S05 và S08 sẵn có.

Bộ ca kiểm tra C: verifier được thấy các đoạn catalog mà nhận định **không** trích, nhưng chỉ để tìm giới hạn, điều kiện hoặc mâu thuẫn bị bỏ qua. C chỉ có tác dụng với S05 (2 đoạn) và S08 (5 đoạn); catalog của S07 và H03 chỉ có 1 đoạn.

| Ca | Câu | Kỳ vọng | Kiểm tra gì |
|---|---|---|---|
| CD1 | S05 | loại, lý do `context_limit:E2` với câu giới hạn đã đăng ký | **Bỏ mức thận trọng** (`caution_dropped`): đúng với E1 ("đã được nghiên cứu kỹ") nhưng bỏ lời thận trọng của E2 không trích trong cùng bài, nơi kết luận này được gọi là còn quá sớm. Hai đoạn không mâu thuẫn hoàn toàn. Là cách diễn đạt thứ hai của lỗi F02 (nhãn `fault_type` của F02 trong v1 không đổi vì bộ v1 bất biến) |
| CC1 | S05 | qua | Bản CD1 có giữ giới hạn và trích E2 (cặp KC1) |
| CC2 | S05 | qua | Chủ đề khác (thang đo CSHQ); E2 nói về chuyện khác, không phải giới hạn của nhận định |
| CC3 | S08 | qua | Đúng với E4; các đoạn khác chỉ thêm thông tin, không giới hạn nhận định |
| CR1 | S05 | loại vì support | Nội dung chỉ có trong E1 không trích, còn trích E2; đoạn không trích **không được cứu** nhận định |
| CR2 | S08 | loại vì support | Các ví dụ chỉ có trong E4 không trích, còn trích E1 |

Nhóm `GC1` (S05) gồm CC2, CD1, CR1.

Nhãn "qua" của CC2 và CC3 chỉ có nghĩa là nhận định bám đúng nguồn và không bị báo nhầm. Nó **không** có nghĩa là nhận định đủ hữu ích để trả lời toàn bộ câu hỏi.

Đã duyệt nhãn ngày 08/11/2026 bằng cách đối chiếu nguồn (không dựa vào kết quả model): CD1 đổi tên loại lỗi từ `conflict_with_other_evidence` thành `caution_dropped` trước khi đo lần nào.

Ngoài bộ này, C còn được đo trên các ca cũ:

- **F02** (v1, ca đích, `measurable_from = C`): đứng riêng, v0.5 bắt nhưng vì lý do khác (`contradicted`); trong nhóm G1 thì lọt;
- **P08, A04**: ca chống báo nhầm;
- **G5, G6**: ca chống báo nhầm và kiểm tra hồi quy.

Nhãn A06 vẫn giữ nguyên và được ghi là vấn đề cần phân xử riêng (`reports/BAO_CAO_BUOC_2C_20261108.md`).
