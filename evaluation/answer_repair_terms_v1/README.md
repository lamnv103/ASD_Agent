# Đơn vị đo vòng sửa: `answer_repair_terms_v1`

**Trạng thái:** `chua_duyet`. Soạn ngày 08/11/2026 cho thử nghiệm hướng dẫn thuật ngữ trong vòng sửa (`docs/answer_layer/THIET_KE_SUA_THUAT_NGU.md`).

Mỗi đơn vị là **một vòng sinh đầu** của S08, lấy từ bundle lượt chạy 2 (`reports/answer_eval_20261107_v0.5`). Đơn vị dùng nguyên vòng đã ghi, hoặc tạo từ nó bằng phép thay chữ chính xác (`derive`).

| Đơn vị | Vai trò |
|---|---|
| U1 | Ca đích: c2 "nguyên tắc trung thực" và c3 "du lượn" bị K1 loại. Ở lượt chạy 2, vòng sửa v0.5 viết lại đúng hai cụm sai đó |
| U2 | Giữ lại, chưa dùng để chỉnh thông báo: c3 vừa sai thuật ngữ vừa có nội dung sai ("đã được chứng minh là hiệu quả hơn ASI"; không đoạn nào nói vậy, E3 còn nói không thể kết luận về hiệu quả) |
| U3 | Giữ lại: dùng thuật ngữ đúng ngay từ đầu. Chỉ kiểm offline |

Hướng dẫn thuật ngữ (`deployments/answer_term_guidance.json`) được cố định trước mọi lượt gọi. Không chỉnh câu chữ của nó dựa trên kết quả các đơn vị này.
