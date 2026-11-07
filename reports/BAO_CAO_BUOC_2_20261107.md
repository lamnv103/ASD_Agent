# Bước 2 tầng G: chốt dược lý → A → B (07/11/2026)

**Phạm vi:** nguyên mẫu nội bộ, `chua_duyet`. Nhãn bộ đo là nhãn nháp của nhóm. 4 câu là dữ liệu phát triển.

## 1. Kết quả theo tầng, mẫu số cố định

Bộ đo `evaluation/answer_verifier_faults_v1`: 10 ca sạch, 18 ca lỗi, 2 ca tranh cãi. Mỗi ca đơn là một nhận định trong một lượt gọi verifier.
- **core16:** 16 ca lỗi chấm được ngay từ v0.2.
- **all18:** toàn bộ 18 ca lỗi.

| Lần đo | Ca sạch bị từ chối nhầm | Hệ thống bắt (core16 / all18) | Chặn tất định | **Verifier bắt (core16 / all18)** | Verifier để lọt (core16) |
|---|---|---|---|---|---|
| v0.2 (`verifier_eval_20261107_v0.2`) | 0/10 | 11/16 · 12/18 | — | **11/16 · 12/18** | F01, F04, F05, F10, F11 |
| v0.3 chốt dược lý (`…_v0.3`) | 0/10 | 12/16 · 13/18 | F11 | **11/16 · 12/18** | như v0.2 |
| v0.4 B + thuật ngữ (`…_v0.4`) | 0/10 | 13/16 · 14/18 | F04, F05, F11 | **10/16 · 11/18** | thêm **F06** |

- Mức tăng của "hệ thống" ở v0.3 và v0.4 đến **hoàn toàn từ tầng tất định** (chốt dược lý; danh sách lỗi thuật ngữ đã biết). Model verifier không tốt hơn.
- Ở v0.3, các ca đơn dùng lại đúng các request của v0.2 (cache seed, 30/30 trùng), vì prompt và payload của verifier không đổi.
- F01 (S05 c3, đọc sai phạm vi) và F10 (bỏ điều kiện "chức năng cao") vẫn lọt ở cả ba phiên bản. Chốt dược lý không giải quyết được hai loại lỗi này.

## 2. B không được nhận

Theo quy tắc ở mục 7.1 của đặc tả kiểm tra, B bị loại vì **verifier bắt ít hơn**: 10/16 so với 11/16.

Ca hồi quy là F06, đúng nhận định S07 vòng 1 mà v0.2 đã bắt đúng. Với B, verifier trả hai mảnh ngắn, đều nguyên văn:

- "Results point mostly to negligible or small effects."
- "there was no evidence of loss of speech skills."

Hai mảnh này **bỏ mất điều kiện "for individuals with autism"** nằm ngay trong câu gốc. Kết quả là verifier chấm `supported` và không gắn cờ. Ca tranh cãi X01 cũng chuyển từ bị loại sang qua, với cùng cơ chế.

Kết luận: cho phép nhiều đoạn ngắn đã mở đường cho việc **chọn mảnh tránh điều kiện**. Phép kiểm tra nguyên văn không bắt được kiểu này, vì từng mảnh vẫn là nguyên văn. Với kích thước mẫu này, một ca không đủ để nói chắc về tỉ lệ, nhưng cơ chế thì đã rõ và có thể tái hiện.

Vì vậy **chưa chạy 4 câu với v0.4**. Script đã soạn sẵn nhưng không chạy.

## 3. Đứng riêng hay theo nhóm

Từ v0.3, đã đo 27 ca ở cả hai cách gọi. Ở **cả v0.3 lẫn v0.4**, kết quả lệch ở cùng 4 ca, theo cả hai chiều:

| Ca | Đứng riêng | Theo nhóm |
|---|---|---|
| F02 (S05 c2, nhóm G1, đúng tập nhận định của lượt chạy S05 thật) | bị loại | **lọt** |
| F10, F11 (nhóm G5) | **lọt** | bị loại (`supported` nhưng vẫn gắn cờ `unrequested_medical_content`) |
| X02 (tranh cãi) | qua | bị loại (lại ghép đoạn) |

Đo chỉ bằng ca đơn sẽ không phản ánh cách gọi thật. Từ nay báo cáo luôn có cả hai bảng.

## 4. Đánh giá offline v0.3 trên cache v0.2 (`answer_eval_20261107_v0.3_offline`)

Chạy mã v0.3 (A + chốt dược lý) trên đúng 14 phản hồi đã ghi, offline:

- S08 chuyển từ `khong_du` sang `mot_phan` và hiển thị c1–c3. **Hai trong ba nhận định mang lỗi thuật ngữ** ("nguyên tắc trung thực", "du lượn"). Đây là lý do danh sách lỗi thuật ngữ đã biết được thêm ở v0.4. Danh sách này độc lập với B và có thể giữ lại.
- S05, S07, H03: không đổi. Chốt dược lý không chặn nhầm câu nào, kể cả nội dung về thuốc ở H03, vốn đúng là phần được hỏi.

## 5. Phát lại

`tasks.ps1 verify` phát lại mọi bộ bằng chứng **bằng mã của chính nó**:

| Bộ bằng chứng | Mã dùng để phát lại |
|---|---|
| Bundle v0.2 | e0f3cc1 |
| Bundle offline v0.3 | 42f7cde |
| Đo v0.2 | 4de9458 |
| Đo v0.3 | 42f7cde |
| Đo v0.4 | 231f872 |

Không có bộ nào bị gán lại thành kết quả của mã mới hơn.

## 6. Cần quyết định

HEAD hiện vẫn chứa mã B (v0.4) **chưa được nhận**. Các hướng có thể chọn:

1. **Bỏ B, giữ danh sách thuật ngữ:** v0.5 = v0.3 + danh sách thuật ngữ. Sau đó chạy lại 4 câu.
2. **Sửa B:** mỗi đoạn trích phải là **trọn một câu** của quote, với ranh giới câu được kiểm tra tất định. Như vậy verifier không cắt được phần điều kiện ra khỏi câu. Đo lại bộ F (36 lượt gọi), và chỉ nhận nếu verifier không bắt ít hơn v0.3.
3. Bỏ B hẳn, chuyển sang C/D.
