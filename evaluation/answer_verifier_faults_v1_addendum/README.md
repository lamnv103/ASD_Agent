# Bộ ca bổ sung cho bộ đo verifier (answer_verifier_faults_v1_addendum)

**Trạng thái:** `chua_duyet`. Nhãn do nhóm kỹ thuật đặt, chưa được chuyên gia phân xử. Bộ `answer_verifier_faults_v1` giữ nguyên.

Bộ này **luôn báo cáo riêng**, có mẫu số riêng, và không bao giờ gộp với v1 thành một tỉ lệ chung. Mục đích là đo trực tiếp những lỗi diễn giải mà v0.5 còn để lọt, trước khi đổi prompt verifier.

Mỗi lỗi đi theo **cặp**: một bản sai và một bản đúng tương ứng. Nhờ vậy cùng một phép đo cho thấy cả việc bắt lỗi lẫn việc không từ chối nhầm.

| Cặp | Ca đúng | Ca lỗi | Loại lỗi |
|---|---|---|---|
| K1 | A02 | A01 (S08 c4 ở lượt 2, verifier cho qua sai), A03 (cặp tối thiểu của A02) | Đổi kết luận: "không thể rút ra kết luận" thành "kết luận sai lệch" |
| K2 | A04 | A05 | Bỏ điều kiện đối tượng và loại nghiên cứu, mở rộng phạm vi (giống F10) |
| K3 | A06 | A07 | F01: thứ "sơ bộ" là bằng chứng về điều trị riêng rẽ, không phải quan hệ hai chiều. A07 đọc đúng nguồn nhưng là nội dung điều trị mà câu hỏi S05 không hỏi |
| K4 | A09 | A08 | Không tự đứng được (giống S05 c4). Chưa có cơ chế kiểm tra riêng (`measurable_from = self_contained_check`) |

Hai điều chỉnh so với yêu cầu ban đầu:
- Bản "giữ điều kiện" của **chính F10** vẫn là nội dung điều trị không được hỏi trong S05, nên không thể là ca sạch. Cặp K2 vì vậy dùng một nhận định đúng chủ đề.
- Bản đọc đúng của F01 cũng là nội dung không được hỏi, nên được xếp là ca lỗi (A07). Ca sạch tương ứng là A06.

`groups.jsonl` có hai nhóm (GA1: S08; GA2: S05) để đo cả cách gọi theo nhóm. Đo bằng `scripts/evaluation/measure_verifier.py --cases … --groups …`.
