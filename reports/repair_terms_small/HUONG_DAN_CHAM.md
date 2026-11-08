# Hướng dẫn chấm: thử nghiệm sửa thuật ngữ (S08)

**Tiêu chí đã đăng ký:** `evaluation/trials/repair_terms_small/criteria.json` (commit `2a7ebd3`).

**Chạy:** 12/12 lần, 24/24 phản hồi đã lưu, 0 lỗi, `cost_unknown = 0`. Cả 12 lần phát lại được bằng `measure_repair.py --check`.

## Phiếu và khóa

- `review_sheet.json`: phiếu mù gồm 30 nhận định được hiển thị, đã xáo trộn với seed cố định; nhánh và đơn vị bị ẩn.
- `review_key.json`: khóa ánh xạ dòng → lần chạy, nhánh, câu chữ. sha256 `bb269604ff34a6377dbfa91f28293600d20266f6058d2691bd58f3694eccc28b`.
  **Không mở khóa, `trial_state.json` hay các thư mục `U*_*_rep*` trước khi phân xử xong**, vì chúng để lộ nhánh. Việc làm mù dựa vào điều này, và còn giới hạn: người thiết kế có thể nhận ra nhánh qua câu chữ.

## Thứ tự

1. **Nhóm chấm trước, độc lập.** Người chấm đọc nguyên văn đoạn trích (`cited`) cho từng dòng. Chép `review_sheet.json` thành `review_team.json` và điền:
   - `concepts`: danh sách mã trong `concept_choices` mà nhận định thể hiện (có thể rỗng);
   - `term_correct`: `"y"` / `"n"` / `"na"`. Với K_FIDELITY và K_SWING, chỉ `"y"` mới tính là sửa đúng;
   - `faithful`: `"y"` / `"n"`, tức giữ nghĩa, phạm vi, mức chắc chắn và không thêm thông tin so với đoạn trích;
   - `contains_known_wrong_content`: `"y"` / `"n"`, tức có khẳng định hiệu quả vượt quá bằng chứng ("đã được chứng minh hiệu quả hơn ASI") hay không;
   - `note`: tự do.
2. **Đánh giá nháp bằng model** (Claude) đã làm xong ngày 08/11/2026 trên phiếu mù, không mở khóa. Bản này được niêm phong: file `_sealed/review_model.json` nằm ngoài git (`.git/info/exclude`), sha256 `6816e0abac051134bb88d68e552c9b11567f25e5bcccf46cfb488099975953f5`. **Nhóm không mở file này trước khi `review_team.json` được commit.** Sau đó chép nó thành `review_model.json` và kiểm tra lại sha256.
3. **Phân xử:** nhóm phân xử các bất đồng khi nhánh vẫn ẩn, ghi vào `review_adjudicated.json`.
4. **Chấm:** `measure_repair.py --judge evaluation/trials/repair_terms_small/criteria.json`. Bộ chấm từ chối nếu bất kỳ bản nào trong ba bản thiếu, trùng hoặc có giá trị không hợp lệ.

Verifier chấm `supported` hay trạng thái `du` **không** phải phán quyết chất lượng.
