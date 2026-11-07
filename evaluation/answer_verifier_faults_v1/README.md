# Bộ đo bước kiểm tra tầng G (answer_verifier_faults_v1)

**Trạng thái:** `chua_duyet`. Nhãn do nhóm kỹ thuật đặt và **chưa được chuyên gia phân xử**. Đây là ca hồi quy phát triển, không phải bộ nghiệm thu.

Mỗi dòng trong `cases.jsonl` là **một nhận định tiếng Việt** kèm mã bằng chứng (E1..En) trong catalog của một trace reader v3 đã commit. Quote không lưu ở đây mà được dựng lại từ corpus đã ghim hash, giống hệt tầng G. Câu hỏi đều là câu tổng hợp, không có dữ liệu cá nhân.

| Nhóm | Số ca | Kỳ vọng |
|---|---|---|
| Sạch (`P..`) | 10 | Qua kiểm tra. Gồm nhận định quan sát được ở lượt chạy 1, bản đã sửa thuật ngữ (S08) và bản đã tách phạm vi (S07) |
| Lỗi (`F..`) | 18 | Bị loại. 6 lỗi quan sát được ở lượt chạy 1, 12 lỗi cài sẵn (đảo phủ định, đổi mức chắc chắn, bỏ điều kiện, thêm khuyến nghị, nội dung thuốc không được hỏi, đổi số, đảo chiều quan hệ...) |
| Tranh cãi (`X..`) | 2 | Chưa có nhãn. Kết quả được ghi lại nhưng không tính vào tỉ lệ cho đến khi có người phân xử |

`measurable_from` cho biết ca đo được từ phiên bản nào. Ví dụ, F02 (mâu thuẫn với đoạn khác trong catalog) chỉ đo được khi verifier được xem catalog, tức thay đổi C. Ở phiên bản sớm hơn, các ca này được liệt kê riêng, không tính là bắt trượt.

Đo và phát lại: xem docstring của `scripts/evaluation/measure_verifier.py`. Mỗi lần đo ghi `cache/` và `results.json` vào một thư mục `reports/verifier_eval_*`. Lệnh `--check` phát lại chỉ từ cache, có chặn mạng.

Giới hạn:
- Mỗi lượt gọi verifier chỉ chứa **một** nhận định, trong khi pipeline gửi cả nhóm nhận định của một câu hỏi.
- Bộ ca nhỏ, lấy từ đúng 4 câu đã dùng để phát triển, nên chỉ cho biết hướng thay đổi, không cho tỉ lệ lỗi tổng quát.
- Lỗi thuật ngữ (F04, F05) được tính là lỗi vì làm đổi nghĩa. Hiện chưa rõ verifier có được kỳ vọng bắt loại lỗi này hay không.
