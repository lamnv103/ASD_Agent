# Bước 2 — đánh giá tìm nguồn, tách khỏi sinh câu trả lời

Bộ chuẩn ban đầu có 30 câu tiếng Việt: 26 câu tìm nội dung (25 nhãn đủ trong phạm vi câu hỏi, 1 nhãn một phần), 1 câu kiểm tra giới hạn áp dụng tại Việt Nam và 3 câu kho không đủ căn cứ. Đây là nhãn tham chiếu do AI đọc nguồn trước khi xem ranking, **không phải gold standard được chuyên gia lâm sàng độc lập duyệt**. Các nguồn liên quan chưa được liệt kê hết.

## Tệp đầu vào

- `questions.jsonl`: câu hỏi gốc, truy vấn thực tế (giữ nguyên), loại câu.
- `reference_labels.json`: source ID, mức hỗ trợ `DU`/`MOT_PHAN`/`GIOI_HAN`, đoạn trích nguyên văn, vị trí, hash, giới hạn và người/ngày đọc nguồn.
- `frozen_inputs.json`: hash hai tệp trên, chốt trước khi chạy tìm kiếm. Không sửa nhãn sau khi xem thứ hạng để làm đẹp điểm. Thay đổi có căn cứ cần tạo phiên bản bộ đánh giá mới.
- `source_evidence.md`: bản đọc thuận tiện của các bằng chứng và giới hạn.

`start`/`end` là offset ký tự Unicode Python, bắt đầu từ 0, khoảng `[start,end)`, trong trường `content` PostgreSQL/`noi_dung` của bản nguồn JSON. Không phải số byte, dòng Markdown hay token. Đây là ghi chú đánh giá; không tạo chunk hoặc vector dẫn xuất. Trước khi gọi API, script đối chiếu tất cả bằng chứng với toàn văn đang có trong PostgreSQL.

## Chạy

Ở thư mục `E:\AI4LIFE\ASD_AGENT`:

```powershell
.\.venv-embedding\Scripts\python.exe -B scripts/evaluation/evaluate_retriever.py --key-file deployments/cohere.env
```

Hoặc dùng `--prompt-key` để nhập khóa ẩn. Câu đã có query cache hợp lệ không gọi API lại. Khi toàn bộ 30 câu đã có cache, có thể chạy lệnh không có tham số khóa. Query mới vẫn cần khóa Cohere hợp lệ.

Mỗi lần chạy tạo thư mục riêng dưới `reports/retrieval_evaluation/`, lưu input đóng băng, config, snapshot trước/sau và:

| Tệp | Cách đọc |
|---|---|
| `ket_qua.csv` | Mã câu, câu hỏi, truy vấn PostgreSQL thực nhận qua vector câu hỏi, nguồn dự kiến, top 5, mức hỗ trợ theo nhãn và lỗi/ghi chú. |
| `raw_results.jsonl` | Ranking, khoảng cách cosine, metadata và provenance query/API/cache cho từng câu. |
| `retrieved_sources.jsonl` | Toàn văn các nguồn đã được trả về, mỗi nguồn lưu một lần; đối chiếu ID/hash với ranking. |
| `summary.json` | Trạng thái, số câu thành công/lỗi, hit@5, MRR@5, labeled source recall@5, kiểm tra không thay dữ liệu. |
| `BAO_CAO.md` | Diễn giải phạm vi và giới hạn kết quả. |

Không chép cả năm toàn văn lặp lại 30 lần. File toàn văn riêng vẫn đủ kiểm tra nội dung mà ranking thực sự trả về; không dùng nguồn đọc bổ sung nhưng chưa tìm được để nâng điểm.

## Chấm đúng phạm vi

- Hit@5: có ít nhất một source ID đã gán nhãn trong top 5.
- MRR@5: nghịch đảo vị trí đầu tiên của nguồn đã gán nhãn, rồi lấy trung bình.
- Labeled source recall@5: phần nguồn đã gán nhãn xuất hiện trong top 5. Vì nhãn chưa đầy đủ, không gọi đây là recall toàn bộ nguồn liên quan trong kho.
- Tách riêng 26 câu nội dung và 1 câu giới hạn. Ba câu thiếu căn cứ không vào mẫu số recall. Khi có lỗi thực thi, công bố số câu thành công và lỗi riêng; không biến lỗi API/database thành kết quả tìm kiếm rỗng.
- `DU_THEO_NHAN_AI_CAN_DUYET` chỉ xuất hiện khi đúng source/hash/đoạn bằng chứng có trong toàn văn trả về. `MOT_PHAN` không tự nâng thành `DU`. Nếu chưa thấy nguồn đã gán nhãn, cần đọc nguồn khác trong top 5 trước khi kết luận không đủ căn cứ.
- Câu chẩn đoán cá nhân, liều thuốc và giá dịch vụ hiện hành: top 5 vẫn có thể chứa nghiên cứu gần nghĩa. Chưa có tầng trả lời/từ chối nên không chấm là đã vượt qua kiểm tra từ chối.

## Người duyệt nên làm tiếp

1. Đọc `ket_qua.csv` cùng đoạn bằng chứng và toàn văn thực trả về.
2. Duyệt độ hỗ trợ, giới hạn quần thể/tuổi/quốc gia, chất lượng và tính hiện hành; ký tên/ngày người thực sự duyệt trong phiên bản nhãn mới.
3. Bổ sung nguồn liên quan chưa được gán nhãn; giữ kết quả v1 để đối chiếu. Không gọi các nguồn chưa gán nhãn là sai tự động.
4. Mở rộng bộ kiểm tra với câu diễn đạt đời thường, câu khó, phủ định, xung đột nguồn và nhiều bối cảnh ngoài phạm vi. Giữ một tập độc lập để kiểm tra sau tối ưu.
5. Khi bắt đầu bước sinh câu trả lời, chấm riêng nội dung trả lời, độ đúng dẫn nguồn và từ chối; không dùng hit@5 thay cho độ đúng y khoa.

Kiểm thử:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m unittest discover -s tests -v
```

Bộ kiểm thử hiện gồm kiểm thử đơn vị và kiểm thử tích hợp chỉ đọc. Các bài `LiveReadOnlyTests` cần PostgreSQL đang chạy, collection 33 tài liệu và query cache đã tạo trong lần đánh giá thật. Xem [bàn giao và diễn giải kết quả](../../reports/retrieval_evaluation/BAN_GIAO_BUOC_1_2.md).
