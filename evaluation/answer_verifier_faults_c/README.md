# Bộ ca C: `answer_verifier_faults_c`

**Trạng thái:** `chua_duyet`. Nhãn phát triển (`team_draft`), soạn ngày 08/11/2026 cùng thiết kế C, chờ duyệt. Bộ này báo cáo riêng, không gộp với v1 hay bộ bổ sung. Không dùng câu hỏi mới: chỉ dùng trace S05 và S08 sẵn có.

Bộ ca kiểm tra C: verifier được thấy các đoạn catalog mà nhận định **không** trích, nhưng chỉ để tìm giới hạn, điều kiện hoặc mâu thuẫn bị bỏ qua. C chỉ có tác dụng với S05 (2 đoạn) và S08 (5 đoạn); catalog của S07 và H03 chỉ có 1 đoạn.

| Ca | Câu | Kỳ vọng | Kiểm tra gì |
|---|---|---|---|
| CD1 | S05 | loại, lý do `context_limit:E2` | Đúng với E1 ("đã được nghiên cứu kỹ"), nhưng E2 không trích của cùng bài nói kết luận này còn quá sớm. Là cách diễn đạt thứ hai của lỗi F02 |
| CC1 | S05 | qua | Bản CD1 có giữ giới hạn và trích E2 (cặp KC1) |
| CC2 | S05 | qua | Chủ đề khác (thang đo CSHQ); E2 nói về chuyện khác, không phải giới hạn của nhận định |
| CC3 | S08 | qua | Đúng với E4; các đoạn khác chỉ thêm thông tin, không giới hạn nhận định |
| CR1 | S05 | loại vì support | Nội dung chỉ có trong E1 không trích, còn trích E2; đoạn không trích **không được cứu** nhận định |
| CR2 | S08 | loại vì support | Các ví dụ chỉ có trong E4 không trích, còn trích E1 |

Nhóm `GC1` (S05) gồm CC2, CD1, CR1.

Ngoài bộ này, C còn được đo trên các ca cũ:

- **F02** (v1, ca đích, `measurable_from = C`): đứng riêng, v0.5 bắt nhưng vì lý do khác (`contradicted`); trong nhóm G1 thì lọt;
- **P08, A04**: ca chống báo nhầm;
- **G5, G6**: ca chống báo nhầm và kiểm tra hồi quy.

Nhãn A06 vẫn giữ nguyên và được ghi là vấn đề cần phân xử riêng (`reports/BAO_CAO_BUOC_2C_20261108.md`).
