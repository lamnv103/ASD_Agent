# Tầng G, lượt chạy 2: contract v0.5 (S05, S08, S07, H03)

**Ngày:** 07/11/2026. **Code:** `b98486f`, `answer_contract_v0.5`. Thành phần: chốt dược lý, A, danh sách lỗi thuật ngữ; không có B.
**Model:** Nemotron cho cả bước sinh và bước kiểm tra. Prompt giống hệt v0.2/v0.3.
**Phạm vi:** nguyên mẫu nội bộ, `chua_duyet`. Đánh giá nội dung dưới đây là đánh giá nháp của nhóm theo rubric, **chưa phải đánh giá chuyên môn**.

**Cách chạy.** Cache được seed bằng các request của lượt 1. Request nào giống hệt thì dùng lại phản hồi đã ghi; request nào khác thì gọi thật.
- Kết quả: chỉ **2 lượt gọi mới**, đều ở S08 (verify vòng 1 và repair; 4.559 token).
- S05, S07, H03 lấy hoàn toàn từ cache, vì v0.5 không chặn thêm gì trong ba câu này. Với ba câu đó, đây là **phát lại** bằng quy tắc v0.5, **không phải** lần sinh mới.
- Lượt này **không đo** độ dao động của bước sinh.

Phát lại: `python -B scripts/evaluation/verify_answer_layer.py` (có trong `tasks.ps1 verify`).

## 1. Kết quả

| Câu | Trạng thái lượt 1 (v0.2) | **Lượt 2 (v0.5)** | Hiển thị | Nhu cầu đáp ứng |
|---|---|---|---|---|
| S05 | du | du | c1–c4 (không đổi) | n1 |
| S08 | khong_du | **du** | c1, c4 | n1 |
| S07 | khong_du | khong_du | — | — |
| H03 | du | du | c1 | n1 |

S08 đổi như sau:
- c2 và c3 bị chặn ở **cả hai vòng** vì lỗi thuật ngữ đã biết. Lượt sửa không sửa được thuật ngữ, vì bước sinh không được cho biết cách dịch đúng.
- c4 vòng 1 lần này có đoạn trích nguyên văn hợp lệ, nên qua kiểm tra.
- Không nhận định nào bị bỏ do trạng thái.
- *(Bổ sung sau rà soát)* Lượt `verify_repair` của S08 trùng hệt request `verify` vòng 1 trong cùng lần chạy, vì sau K1 vẫn còn đúng c1 và c4 với cùng câu chữ. Phản hồi vì vậy được lấy từ cache (cùng `request_id`). Đây là **lặp lại verdict vòng 1, không phải một lần kiểm chứng độc lập** sau lượt sửa.

## 2. Đánh giá nháp của nhóm trên 7 nhận định hiển thị

| Nhận định | Đánh giá | Ghi chú |
|---|---|---|
| S05 c1 | Chấp nhận được | |
| S05 c2 | **Lỗi** | Mâu thuẫn với E2 ("premature"); bỏ điều kiện nghiên cứu cắt ngang. Cần C |
| S05 c3 | **Lỗi** | Verifier cho qua sai (F01): đọc sai phạm vi của "preliminary" |
| S05 c4 | **Lỗi nhẹ** | Không tự đứng được (F03); "trẻ" hẹp hơn "individuals". Cần D hoặc kiểm tra tính tự đứng |
| S08 c1 | Chấp nhận được | |
| **S08 c4** | **Lỗi** | "dẫn đến việc đưa ra **kết luận sai lệch** về hiệu quả của ASI" trong khi nguồn viết "makes it **impossible to draw conclusions**". Verifier chấm `supported`, không gắn cờ, và lời giải thích còn diễn giải lại nguồn thành "flawed conclusions". **Lỗi verifier mới quan sát được**, cùng loại với F01 (đọc sai mức kết luận) |
| H03 c1 | Chấp nhận được | |

**3/7 chấp nhận được, 4/7 có vấn đề.** Ba lỗi ở S05 vẫn y như lượt 1, vì v0.5 không có cơ chế cho các lỗi này.

S08 lên `du` **không có nghĩa là câu trả lời tốt hơn**. Ở lượt 1, lỗi ghép đoạn "..." đã vô tình chặn đúng nhận định sai (c4, phiên bản vòng 1). Ở lượt này nhận định đó lọt qua. Đây là bằng chứng thêm rằng tăng số câu có nội dung không phải mục tiêu tự thân.

## 3. Phép đo verifier v0.5 (`reports/verifier_eval_20261107_v0.5`)

| | core16 | all18 |
|---|---|---|
| Hệ thống bắt | 14/16 | 15/18 |
| Chặn tất định | F04, F05, F11 | như core16 |
| **Verifier bắt** | **11/16** (bằng v0.2/v0.3) | **12/18** |
| Còn lọt ở hệ thống | F01, F10 | F01, F03, F10 |
| Ca sạch bị từ chối nhầm | 0/10 | |

- Các ca đơn và nhóm đầy đủ dùng lại đúng các request của v0.3 (cache trùng 30/30 và 6/6).
- **Nhóm theo pipeline** (gửi lại G2 và G5 sau khi đã bỏ các nhận định bị tầng tất định chặn; 2 lượt gọi mới):
  - **F10 lọt.** Trong nhóm đầy đủ, F10 bị bắt chỉ vì mang cùng cờ `unrequested_medical_content` với F11. Khi chốt loại F11, verifier cho F10 qua. F10 vẫn là lỗ hổng thật của verifier, và chốt dược lý đã vô tình bỏ đi bối cảnh từng giúp bắt nó.
  - X02 (tranh cãi) chuyển từ bị loại sang qua khi đi cùng ít nhận định hơn.

## 4. Ưu tiên cho C/D

- F01, S08 c4 (mới) và F10 cùng là lỗi **diễn giải mức kết luận hoặc phạm vi**. Hướng thử: verifier phải liệt kê điều kiện hoặc mức chắc chắn trong đoạn trích, rồi đối chiếu với nhận định. Đo trên ca đơn, nhóm đầy đủ và nhóm theo pipeline.
- F02 (theo nhóm) và S05 c2 cần C: các đoạn khác trong danh mục **chỉ** dùng để phát hiện giới hạn hoặc mâu thuẫn, không được tính là căn cứ.
- S08 c4 nên được thêm vào bộ đo dưới dạng ca quan sát mới, trong một bộ ca phiên bản mới. Bộ `answer_verifier_faults_v1` giữ nguyên để mẫu số không đổi.
- Lượt sửa không sửa được lỗi thuật ngữ. Nên đưa cách dịch đúng vào phần `problems` gửi cho lượt sửa. Việc này đổi payload, nên làm cùng C/D.
