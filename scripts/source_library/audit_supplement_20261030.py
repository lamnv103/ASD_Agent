"""Offline audit and readable handoff for the 2026-10-30 source supplement.
Does not access the database, embedding APIs or generative models.
"""
from __future__ import annotations
import csv,io,json,re,subprocess,sys
from pathlib import Path
from collections import Counter
import supplement_20261030 as s
from export_json import export_documents
from storage import atomic_write,audit_cache
ROOT=s.ROOT;LIB=s.LIB;REPORT=s.REPORT
MARKER='<!-- ORIGINAL_DOCUMENT_BODY -->\n'

def write(path,data):
 atomic_write(path,data if isinstance(data,str) else s.json_text(data))

def docs_and_guides(core,pending,held,publication):
 payload=json.loads((LIB/'documents.json').read_text(encoding='utf-8'))
 old=json.loads((REPORT/'before_release/documents.json').read_text(encoding='utf-8'))
 n=len(core);characters=payload['thong_tin_bo_du_lieu']['tong_ky_tu_noi_dung']
 delta=characters-old['thong_tin_bo_du_lieu']['tong_ky_tu_noi_dung']
 originals=sum(p.is_file() for p in (LIB/'originals').rglob('*'))
 main_guide=f"""# Dữ liệu toàn văn ASD cho ASD_AGENT

Kho chính nằm tại E:/AI4LIFE/ASD_AGENT/knowledge/rag/source_library. Đây là kho dữ liệu của dự án mới; chương trình và database của dự án trước vẫn ở Carobud_ASD_2026.

Đợt bổ sung ngày 30/10/2026 đã giữ nguyên 27 tài liệu ban đầu, bổ sung 6 tài liệu đạt kiểm tra chuyển đổi. Hiện tập chính có **{n} tài liệu, {characters:,} ký tự nội dung**; tăng {delta:,} ký tự. Mỗi tài liệu/phiên bản vẫn ở một tệp đầy đủ. Không chia đoạn mới, không cắt ngắn để vừa mô hình và chưa thực hiện embedding.

## Mở tệp nào trước

- [Báo cáo bổ sung theo bốn chủ đề bạn yêu cầu](reports/source_supplement_20261030/BAO_CAO_BO_SUNG_NGUON.md): đã thêm gì và phần nào còn thiếu.
- [Danh sách {n} tài liệu trong tập chính](knowledge/rag/source_library/CORE_DOCUMENTS.md).
- [documents.json](knowledge/rag/source_library/documents.json): toàn bộ nội dung của {n} tài liệu, có tên, nguồn/link/tác giả, nội dung và ngày tháng.
- [Hướng dẫn chi tiết cấu trúc dữ liệu](knowledge/rag/source_library/README.md).
- [Kết quả kiểm tra cuối](reports/source_supplement_20261030/verification.json).

## Những thư mục và danh mục chính

| Vị trí | Ý nghĩa |
|---|---|
| documents/ | {n} Markdown được nhận về mặt chuyển đổi; có thông tin nguồn và nội dung đầy đủ. |
| originals/ | {originals} tệp gốc/tài sản đi kèm cho cả tập chính và nhóm bổ sung đang chờ; không phải {originals} tài liệu độc lập. |
| pending_documents/ và documents_pending_review.json | {len(pending)} bản chuyển đổi bổ sung còn khoảng trống; không trộn vào documents.json hoặc coi là dữ liệu sẵn sàng nhúng. |
| core_catalog.jsonl | Danh mục của {n} tài liệu trong tập chính, có quyền sử dụng, phạm vi, giới hạn và hash. |
| catalog.jsonl | Danh mục rộng hơn, gồm cả hồ sơ chờ/loại từ dự án cũ. Không phải mọi dòng đều có toàn văn trong thư mục này. |
| CLINICAL_REVIEW_QUEUE.csv | Hàng chờ để chuyên gia thực sự thẩm định; không tự điền tên chuyên gia hay quyết định duyệt. |
| index_preview.jsonl | 183 mục cũ, chỉ thuộc 27 tài liệu ban đầu; chưa bổ sung chỉ mục cho các nguồn mới và không chứa vector. |

AAP, ASHA, AOTA và một bài Project AIM chưa xác minh được quyền tái sử dụng toàn văn chỉ được ghi thông tin nguồn/đường dẫn trong danh mục. Các nghiên cứu PEERS/SST, giao tiếp/ngôn ngữ và SenITA đã lấy được bản gốc nhưng một số hình/bảng/phụ lục chưa chuyển đủ; phần còn thiếu được ghi riêng.

**Kho nguồn đã đối chiếu phục vụ nghiên cứu, chưa có thẩm định lâm sàng độc lập.** “Đạt kiểm tra chuyển đổi” không có nghĩa phương pháp điều trị đã được chứng minh phù hợp cho mọi trẻ, hoặc chatbot đã đủ điều kiện tư vấn y khoa. Có nguồn có phạm vi tuổi rộng hơn 0–18 hoặc có điều kiện nghiên cứu cụ thể; giữ đúng phạm vi nguồn. Giấy phép áp dụng riêng từng nguồn, gồm cả giới hạn phi thương mại nếu có.

[DATA_TRANSFER_MANIFEST.json](DATA_TRANSFER_MANIFEST.json) là biên bản lịch sử lúc sao chép 27 tài liệu. Các con số/hash trong biên bản đó không phải snapshot hiện tại sau bổ sung; biên bản được giữ nguyên. [SUPPLEMENT_20261030_MANIFEST.json](knowledge/rag/source_library/SUPPLEMENT_20261030_MANIFEST.json) ghi hash của kho hiện tại. Danh mục cũ được sao lưu ở reports/source_supplement_20261030/before_release/.

Thư mục reports lưu bằng chứng thu thập, kết quả kiểm tra và cache nguồn; scripts/source_library lưu công cụ xử lý dữ liệu ngoại tuyến. Không dùng mọi tệp trong reports/cache làm tài liệu RAG. Không sao chép khóa API, môi trường Python, SQL hoặc vector vào kho mới trong đợt này; không thay database hay cấu hình agent cũ.
"""
 write(ROOT/'README.md',main_guide)
 library_guide=f"""# Cách đọc kho nguồn

Cập nhật 30/10/2026. Tập chính: {n} tài liệu, {characters:,} ký tự nội dung. **Phục vụ nghiên cứu; chưa có thẩm định lâm sàng độc lập.**

## Nội dung trong JSON

documents.json có hai trường chính:

- thong_tin_bo_du_lieu: số tài liệu, lượng nội dung, ngày xuất, hash danh mục và trạng thái sử dụng.
- tai_lieu: danh sách tài liệu. Mỗi phần tử có id, ten_tai_lieu, nguon, noi_dung, ngay_thang và doi_chieu.

nguon chứa tên tổ chức/tạp chí, link nguồn, link toàn văn và tác giả khi được công bố. Không tự tạo tên tác giả cá nhân cho bài CDC do cơ quan phát hành. noi_dung là toàn bộ phần nguồn đã chuyển đổi, giữ ngôn ngữ gốc, không phải bài giải thích tiếng Việt do AI viết. Phần biên tập về phạm vi/quyền/hạn chế nằm ở metadata và đầu Markdown, tách khỏi mốc ORIGINAL_DOCUMENT_BODY.

ngay_thang phân biệt ngày xuất bản, cập nhật và đối chiếu. Giá trị null nghĩa là chưa được công bố/xác định theo loại ngày đó. Với CDC Treatment, nguồn hiển thị 16/05/2024 nhưng không ghi rõ đó là ngày xuất bản hay cập nhật; ngày hiển thị được giữ trong nội dung và trường displayed_source_date của catalog.jsonl, không tự gán thành ngày xuất bản. Bài nghiên cứu có thể có ngày xuất bản trực tuyến khác năm/số báo; verified_bibliography giữ các ngày gốc. Không coi ngày tải là ngày xuất bản.

doi_chieu chứa quyền sử dụng, phạm vi tuổi gốc, giới hạn, đường dẫn Markdown/bản gốc/tài sản và SHA-256. Tài liệu nghiên cứu có thể chứa bảng HTML và công thức MathML trong Markdown; không xóa chúng vì tưởng là mã thừa.

## Tập chính và tập chờ

documents/ và documents.json có cùng {n} nội dung. core_catalog.jsonl có cùng các ID. “Tập chính” ở đây chỉ là nhóm đã đáp ứng kiểm tra xuất xứ/quyền/chuyển đổi của kho nghiên cứu, chưa được duyệt lâm sàng hoặc production.

pending_documents/ và documents_pending_review.json chứa {len(pending)} nguồn bổ sung có bản gốc nhưng còn hình/bảng/phụ lục hoặc quan hệ phiên bản cần xử lý. JSON chờ dùng cấu trúc source_id, title, source_url, status, conversion_gaps, metadata, content và mang nhãn NOT_ACCEPTED_FOR_INDEXING. Không nhập nhầm JSON này cùng documents.json để tăng quy mô.

catalog.jsonl có cả hồ sơ lịch sử chưa được tải toàn văn, nguồn bị loại và hồ sơ chỉ có đường dẫn. Chỉ dùng core_catalog.jsonl/documents.json khi muốn đọc tập chính hiện hành. Trường coverage_eligible trong bản phát hành này là điều kiện nhận nguồn của kho; không phải bằng chứng đã đạt đủ độ phủ y khoa.

Hai bản CDC bổ sung được lưu dưới dạng bản đọc web có đầy đủ các dòng nội dung bài, kèm đường dẫn đã đối chiếu. Đuôi bản gốc là .web.txt; đây không phải HTML gốc (máy chủ trả HTTP 403 khi tải HTML trực tiếp). Ảnh minh họa không được sao chép theo giả định quyền của phần chữ; alt text và việc loại ảnh được ghi rõ. Không chứng nhận bố cục/scripts của trang.

Mỗi nghiên cứu được nhận giữ nguyên bản XML và các bảng, tài liệu bổ sung cùng một Markdown nguồn. Ba sơ đồ đã được đối chiếu hình để chép lại nhãn/số liệu; ba phụ lục DOCX đã chuyển đầy đủ phần văn bản/bảng. Bản hình/DOCX vẫn được giữ để kiểm tra. Các biểu đồ chưa chuyển an toàn tiếp tục làm tài liệu chờ, không đoán số liệu từ vị trí điểm trên hình.

## Kiểm tra lặp lại

Dùng Python đã có của dự án trước, không cần khóa API hay kết nối database:

    & 'E:\\AI4LIFE\\Carobud_ASD_2026\\.venv-rag\\Scripts\\python.exe' -B scripts/source_library/export_json.py --check
    & 'E:\\AI4LIFE\\Carobud_ASD_2026\\.venv-rag\\Scripts\\python.exe' -B scripts/source_library/audit_supplement_20261030.py

Chạy từ E:/AI4LIFE/ASD_AGENT. Lệnh đầu chỉ đọc và đối chiếu JSON/Markdown/hash. Lệnh audit đọc kho, chạy kiểm thử và cập nhật báo cáo/hướng dẫn/manifest cục bộ; không gọi mạng, LLM, embedding hoặc database.

scripts/source_library/supplement_20261030.py plan tái dựng kế hoạch đợt bổ sung từ cache và danh mục cha đã sao lưu. Lệnh publish chỉ dùng một lần và sẽ từ chối ghi đè bản đã phát hành. Mọi bổ sung tiếp cần phiên bản mới thay vì sửa âm thầm dữ liệu nguồn.

index_preview.jsonl giữ nguyên 183 mục của 27 tài liệu cũ; chưa phải cấu hình chunk cuối cùng, không phản ánh các tài liệu bổ sung. Đợt này ưu tiên dữ liệu nguồn theo yêu cầu của bạn.

## Quyền và phạm vi

Không dùng số lượng file, phụ lục hoặc bài tổng quan trùng nghiên cứu để đếm bằng chứng độc lập. Không đổi phạm vi nguồn thành toàn bộ 0–18 tuổi. ASI khác hoạt động cảm giác nói chung; PEERS khác Social Stories và không có nghĩa đã có giáo trình PEERS được cấp phép. Dịch vụ/quyền lợi Hoa Kỳ không tự áp dụng tại Việt Nam.

Chưa làm embedding, chưa đếm lại token cho bộ mới, chưa cập nhật database và chưa thay dữ liệu chatbot đang sử dụng. Các trạng thái vector thử nghiệm trong dự án trước vẫn là lịch sử của tập cũ, không tự áp cho {n} tài liệu hiện tại.
"""
 write(LIB/'README.md',library_guide)
 byid={r['source_id']:r for r in core+pending+held}
 doc_lines=["# Bổ sung nguồn theo bốn chủ đề còn thiếu","","Ngày đối chiếu: 30/10/2026. Kho đích: E:/AI4LIFE/ASD_AGENT.","",
  f"Giữ nguyên 27 tài liệu; thêm 6 tài liệu đạt kiểm tra chuyển đổi. Tập chính hiện có **{n} tài liệu, {characters:,} ký tự**, tăng {delta:,} ký tự. Đã lưu thêm {len(pending)} bản gốc và bản chuyển đổi chờ xử lý, không cộng chúng vào tập chính. Chưa thực hiện embedding, gọi LLM hoặc thay database.","",
  "**Đây là kho nguồn nghiên cứu chưa có thẩm định lâm sàng độc lập.** Các nhận xét dưới đây là metadata biên tập/đối chiếu, không phải văn bản nguồn hay quyết định điều trị.","",
  "## Kết quả theo yêu cầu","",
  "| Nhóm | Đã thêm vào tập chính | Đã lấy bản gốc nhưng còn chờ | Phần chưa đáp ứng |","|---|---|---|---|",
  "| Can thiệp sớm | CDC Early Intervention; CDC Treatment; tổng quan nền tảng NDBI | Project AIM cập nhật | Chưa có toàn văn AAP được xác minh quyền; NDBI 2015 không phải guideline hiện hành. |",
  "| Ngôn ngữ/trị liệu ngôn ngữ | NDBI có phần dạy ngôn ngữ và giao tiếp; CDC có phần can thiệp ngôn ngữ | Tổng quan NDBI + AAC; tổng quan giao tiếp ở trẻ ít lời | Chưa có ASHA Practice Portal được xác minh quyền; chưa coi độ sâu speech-language therapy là hoàn tất. |",
  "| OT/can thiệp cảm giác | Tổng quan ASI 2019; tổng quan SBI 2025 | Phân tích phương pháp SI/SP; báo cáo SenITA 2022 đầy đủ PDF | Chưa có toàn văn AOTA được xác minh quyền. Cần giữ bằng chứng không đồng nhất và giới hạn quần thể. |",
  "| Kỹ năng xã hội/PEERS/SST | Thử nghiệm Social Stories ASSSIST-2 và phụ lục | RCT PEERS Ba Lan; tổng quan SST vị thành niên | Chưa nhận PEERS/SST vào tập chính do còn biểu đồ; không có giáo trình PEERS được cấp phép. |","",
  "Bốn nhóm đã được bổ sung tài liệu thực chất, nhưng chưa thể công bố tất cả đều đạt độ phủ đầy đủ hoặc chuẩn thực hành lâm sàng.","",
  "## Sáu tài liệu được nhận về mặt chuyển đổi","",
  "| Tài liệu / nguồn | Loại và ngày nguồn | Ký tự nội dung | Giới hạn cần giữ |","|---|---|---:|---|"]
 notes={
 'ASD-SUP-PMC4513196':'NDBI nền tảng, trẻ nhỏ. Bài bình luận 2022 về cách đơn giản hóa ngôn ngữ đầu vào được ghi ở metadata; không đưa ra đơn thuốc ngôn ngữ cố định.',
 'ASD-SUP-PMC6590432':'ASI có tiêu chí fidelity, kết luận cho trẻ 4–12 trong phạm vi chọn nghiên cứu; khác mọi hoạt động cảm giác. Cần đối chiếu nghiên cứu SenITA mới hơn.',
 'ASD-SUP-PMC12658592':'SBI, tiêu chí tuổi 0–21 và nhiều chẩn đoán; không suy thành bằng chứng cho mọi trẻ ASD hoặc an toàn cho trẻ sơ sinh.',
 'ASD-SUP-PMC11754701':'Trẻ 4–11 tại Anh. Kết quả chính ITT không có ý nghĩa thống kê; cải thiện mục tiêu cá nhân không đồng nghĩa cải thiện xã hội toàn diện.',
 'CDC-EARLY-INTERVENTION':'Hướng dẫn tiếp cận dịch vụ Hoa Kỳ; không áp quyền lợi/điều kiện dịch vụ vào Việt Nam.',
 'CDC-ASD-TREATMENT':'Tổng quan giáo dục sức khỏe, không phải guideline AAP/ASHA/AOTA; các cách can thiệp được nêu không có nghĩa hiệu quả ngang nhau.'}
 for sid in publication['additions_accepted']:
  r=byid[sid];date=r.get('publication_date') or ('Ngày hiển thị '+r['displayed_source_date'] if r.get('displayed_source_date') else 'Chưa xác định')
  if sid=='ASD-SUP-PMC6590432':date+=' online; số báo 2019'
  if sid=='ASD-SUP-PMC11754701':date+=' online; số báo 2025'
  doc_lines.append('| ['+sid+'](../../'+r['document_path']+') — ['+r['title']+']('+r['source_url']+') | '+r['source_type']+'; '+date+' | '+f"{r['body_characters']:,}"+' | '+notes[sid]+' |')
 doc_lines+=["","Các nghiên cứu giữ phương pháp, kết quả, thảo luận, hạn chế, tài liệu tham khảo và phần bổ sung đã chuyển đổi trong cùng tệp. Hai trang CDC là toàn bộ văn bản bài qua bản đọc web, không phải bản HTML gốc; giới hạn kỹ thuật/ảnh minh họa được ghi trong hồ sơ.","",
  "## Bảy tài liệu đã lấy bản gốc, chưa nhận bản chữ vào tập chính","",
  "| ID / tài liệu | Phần còn chờ | Bản gốc |","|---|---|---|"]
 for r in pending:
  gaps='; '.join(sorted({g['type']+': '+g['status'] for g in r['conversion']['gaps']}))
  doc_lines.append('| ['+r['source_id']+' — '+r['title']+'](../../'+r['document_path']+') | '+gaps+' | [Bản gốc](../../'+r['original_path']+') |')
 doc_lines+=["","ASD-CSV-017 đã có trong danh mục trước đây nên dùng lại ID, không tạo một nguồn thứ hai. Với Project AIM, quan hệ phiên bản/DOI gần giống nhau còn chờ xác minh; không cộng như hai bằng chứng độc lập. SenITA có đủ **172 trang PDF vật lý**, gồm phần đầu/cuối và phụ lục; không nhầm số trang PDF với trang nội dung đánh số của báo cáo. Bản Markdown SenITA là văn bản trích từng trang, chưa xác nhận thứ tự bảng/ký hiệu/hình.","",
  "## Hồ sơ chỉ có thông tin và link, chưa sao chép toàn văn","",
  "| Nguồn | Trạng thái và lý do |","|---|---|"]
 for r in held:doc_lines.append('| ['+r['source_id']+' — '+r['title']+']('+r['source_url']+') | '+r['limits'][0].replace('|',' / ')+' |')
 doc_lines+=["","Miễn phí đọc không tự động đồng nghĩa được phép sao chép toàn văn cho kho AI. Không gửi yêu cầu xin phép, thanh toán hoặc tự gán giấy phép. Các nguồn PMC được lấy qua OAI-PMH, có kiểm tra quyền từng bài và metadata phiên bản; kiểm tra đính chính/rút bài là snapshot, không bảo đảm đầy đủ mọi cập nhật trong tương lai.","",
  "## Các chi tiết y khoa đã giữ giới hạn","",
  "- ASI khác SBI và khác toàn bộ hoạt động trị liệu nghề nghiệp; không suy ra chỉ dẫn ép sâu/chăn nặng tại nhà.",
  "- Tổng quan ASI tìm trong 2006–2017 có ba nghiên cứu cuối cùng. SenITA 2022 không thấy lợi ích có ý nghĩa ở kết quả chính so với chăm sóc thường lệ; không dùng tổng quan cũ để khẳng định đồng thuận hiện tại. Khác biệt kết quả/thiết kế cần chuyên gia đánh giá.",
  "- ASSSIST-2: giữ khoảng tin cậy có dấu âm (−4.18 đến 0.96), p=.220 cho kết quả chính; không đổi thành thử nghiệm chứng minh hiệu quả toàn diện.",
  "- PEERS Ba Lan: tiêu chí tuổi 11–18 nhưng mẫu thực tế 11.8–16.1; không đổi thành bằng chứng cho mọi trẻ 0–18.",
  "- Các tổng quan có thể dùng chung nghiên cứu. Chưa có đánh giá độc lập để coi chúng là các khối bằng chứng không trùng.",
  "- Chưa dịch/biên soạn lại để thay văn bản gốc; agent giải thích tiếng Việt là bước sau.","",
  "## Kiểm tra và bước tiếp theo","",
  "verification.json ghi kết quả kiểm tra thực tế: 17 kiểm thử, hash nguồn/tài sản/Markdown, khớp JSON, giữ nguyên 27 hồ sơ và tệp nguồn ban đầu, tách tập chờ và kiểm tra lại phép chuyển đổi. Cache chứa một số trang báo lỗi HTTP 200; chúng được ghi vào invalid_cache_inputs.json và không nhận làm dữ liệu nguồn.","",
  "Bước tiếp theo ưu tiên đối chiếu hình/bảng/phụ lục và quan hệ phiên bản của bảy tài liệu chờ, tìm nguồn speech-language therapy có quyền phù hợp hoặc xác minh quyền ASHA/AAP/AOTA, rồi nhờ chuyên gia thẩm định các nhận định. Chỉ sau đó chốt tập đem thử embedding; chưa thể coi việc nhúng là bước còn thiếu duy nhất.","",
  "DATA_TRANSFER_MANIFEST.json được giữ làm lịch sử sao chép ban đầu. SUPPLEMENT_20261030_MANIFEST.json là snapshot hash mới; index_preview.jsonl vẫn chỉ có 183 mục của 27 tài liệu cũ.",""]
 write(REPORT/'BAO_CAO_BO_SUNG_NGUON.md','\n'.join(doc_lines))
 fields=['source_id','title','source_url','publication_date','displayed_source_date','topics','status','in_main_documents_json','rights_status','license','original_age_scope','body_characters','document_path','original_path','remaining_gaps']
 buff=io.StringIO(newline='');writer=csv.DictWriter(buff,fieldnames=fields);writer.writeheader()
 all_new_ids=publication['additions_accepted']+[r['source_id'] for r in pending]+[r['source_id'] for r in held]
 for sid in all_new_ids:
  r=byid[sid];row={k:r.get(k,'') for k in fields if k in r}
  row.update(topics=';'.join(r.get('topics',[])),in_main_documents_json=bool(r.get('coverage_eligible')),rights_status=r['rights']['status'],license=r['rights'].get('license',''),
   remaining_gaps='; '.join(g['type']+': '+g['status'] for g in r.get('conversion',{}).get('gaps',[])))
  writer.writerow(row)
 write(REPORT/'SOURCE_STATUS.csv','\ufeff'+buff.getvalue())

def audit():
 checks={}
 checks['json_export']=export_documents(check=True)
 status=json.loads((LIB/'BUILD_STATUS.json').read_text(encoding='utf-8'))
 publication=json.loads((REPORT/'publication.json').read_text(encoding='utf-8'))
 old,materials,held=s.plan()
 allrows=[json.loads(x) for x in (LIB/'catalog.jsonl').read_text(encoding='utf-8').splitlines() if x]
 core=[r for r in allrows if r.get('coverage_eligible')]
 current=json.loads((LIB/'documents.json').read_text(encoding='utf-8'))
 before=json.loads((REPORT/'before_release/documents.json').read_text(encoding='utf-8'))
 byid={d['id']:d for d in current['tai_lieu']}
 assert all(byid.get(d['id'])==d for d in before['tai_lieu']),'Original JSON document entry changed'
 checks['original_27_json_entries_unchanged']=True
 baseline=json.loads((REPORT/'before_release/original_27_file_hashes.json').read_text(encoding='utf-8'))
 for path,sha in baseline.items():assert s.digest((ROOT/path).read_bytes())==sha,'Protected original file changed: '+path
 checks['protected_original_files_verified']=len(baseline)
 transfer=json.loads((ROOT/'DATA_TRANSFER_MANIFEST.json').read_text(encoding='utf-8'))
 assert transfer['source_release_sha256']==s.PARENT
 old_root=Path(transfer['source_root'])
 for path,sha in baseline.items():assert s.digest((old_root/path).read_bytes())==sha,'Old-project original source differs: '+path
 checks['old_project_original_files_verified_read_only']=len(baseline)
 pending=[r for r,c in materials if not r['coverage_eligible']]
 accepted=[r for r,c in materials if r['coverage_eligible']]
 assert len(core)==33 and len(pending)==7 and len(accepted)==6 and len(held)==4
 assert len({r['source_id'] for r in allrows})==len(allrows)
 for row,copies in materials:
  current_row=next(r for r in allrows if r['source_id']==row['source_id'])
  assert current_row==row,'Reconstructed catalog record changed: '+row['source_id']
  for relative,raw in copies.items():assert (ROOT/relative).read_bytes()==raw,'Reconversion/file mismatch: '+relative
 checks['all_supplement_materials_match_offline_reconversion']=True
 for row in accepted:
  assert not row['conversion']['gaps']
  assert not row['clinical_reviewed'] and not row['production_ingest'] and not row['embedding']['requested']
  assert not row['embedding']['split'] and not row['embedding']['truncate']
 for row in pending:
  assert row['source_id'] not in byid
  assert row['conversion']['gaps']
  raw=(ROOT/row['document_path']).read_bytes()
  assert s.digest(raw)==row['document_sha256']
  assert s.digest(raw.decode('utf-8').split(MARKER,1)[1])==row['content_sha256']
  for asset in row.get('source_assets',[]):assert s.digest((ROOT/asset['archived_path']).read_bytes())==asset['asset_sha256']
 checks['pending_sources_excluded_from_main_json']=len(pending)
 pending_json=json.loads((LIB/'documents_pending_review.json').read_text(encoding='utf-8'))
 assert pending_json['status']=='NOT_ACCEPTED_FOR_INDEXING'
 assert {r['source_id'] for r in pending_json['documents']}=={r['source_id'] for r in pending}
 for d in pending_json['documents']:assert s.digest(d['content'])==d['metadata']['content_sha256']
 checks['pending_json_bodies_match_markdown']=True
 for row in held:assert not row['document_path'] and not row['coverage_eligible']
 checks['unknown_permission_sources_metadata_only']=len(held)
 old_preview=next(r for r in transfer['files'] if r['path'].endswith('/index_preview.jsonl'))
 assert s.digest((ROOT/old_preview['path']).read_bytes())==old_preview['sha256']
 checks['index_preview_unchanged_old_27_only']=True
 def load_reviews(path):
  with path.open(encoding='utf-8-sig',newline='') as f:return {r['source_id']:r for r in csv.DictReader(f)}
 previous_reviews=load_reviews(REPORT/'before_release/CLINICAL_REVIEW_QUEUE.csv')
 reviews=load_reviews(LIB/'CLINICAL_REVIEW_QUEUE.csv')
 assert len(reviews)==33
 assert all(reviews.get(k)==v for k,v in previous_reviews.items())
 for row in accepted:
  assert not any(reviews[row['source_id']][k] for k in ['independent_clinician_name','review_date','clinical_decision'])
 checks['original_clinical_review_notes_preserved_and_no_approval_fabricated']=True
 failures=[]
 for row,copies in materials:
  md=(ROOT/row['document_path']).read_text(encoding='utf-8')
  for target in re.findall(r'\]\((\.\./originals/[^)]+)\)',md):
   if not ((ROOT/row['document_path']).parent/target).resolve().is_file():failures.append([row['source_id'],target])
 assert not failures,'Broken original/figure link'
 checks['new_markdown_original_asset_links_valid']=True
 cache=audit_cache(REPORT);invalid=[x for x in cache if x['status']=='invalid']
 invalid_paths={str(s.CACHE/x['name']) for x in invalid}
 for row,copies in materials:
  for rel in copies:
   assert str(ROOT/rel) not in invalid_paths
 write(REPORT/'invalid_cache_inputs.json',dict(status='NOT_SOURCE_CONTENT',not_admitted=True,items=invalid))
 checks['invalid_download_pages_excluded']=len(invalid)
 result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'scripts/source_library'),'-p','test_supplement_20261030.py','-v'],cwd=ROOT,text=True,encoding='utf-8',errors='strict',capture_output=True)
 log=result.stdout+result.stderr;write(REPORT/'test_results.txt',log)
 assert result.returncode==0,log[-2500:]
 match=re.search(r'Ran (\d+) tests',log);assert match
 checks['regression_tests']=dict(passed=int(match[1]),failed=0,log='reports/source_supplement_20261030/test_results.txt')
 docs_and_guides(core,pending,held,publication)
 snapshot={}
 for file in sorted(LIB.rglob('*')):
  if file.is_file() and file.name!='SUPPLEMENT_20261030_MANIFEST.json':
   relative=file.relative_to(ROOT).as_posix();snapshot[relative]=dict(bytes=file.stat().st_size,sha256=s.digest(file.read_bytes()))
 write(LIB/'SUPPLEMENT_20261030_MANIFEST.json',dict(release_id=s.REVISION,date=s.DATE,scope='Current source_library files except this manifest; not a clinical approval or embedding manifest',
  historical_transfer_manifest_sha256=s.digest((ROOT/'DATA_TRANSFER_MANIFEST.json').read_bytes()),core_documents=len(core),supplement_pending=len(pending),originals_and_assets=sum(p.is_file() for p in (LIB/'originals').rglob('*')),
  files=snapshot,embedding_called=False,database_changed=False))
 manifest=json.loads((LIB/'SUPPLEMENT_20261030_MANIFEST.json').read_text(encoding='utf-8'))
 for path,entry in manifest['files'].items():assert s.digest((ROOT/path).read_bytes())==entry['sha256']
 checks['current_library_files_in_manifest']=len(snapshot)
 checks['release_hashes_match_status']=bool(status['documents_json_sha256']==s.digest((LIB/'documents.json').read_bytes()) and status['catalog_sha256']==s.digest((LIB/'catalog.jsonl').read_bytes()))
 assert checks['release_hashes_match_status']
 checks.update(core_documents=33,accepted_additions=6,acquired_supplement_pending=7,metadata_only_supplement_held=4,catalog_records=len(allrows),body_characters=sum(len(d['noi_dung']) for d in current['tai_lieu']),new_index_units_created=0)
 verification=dict(ok=True,checked_on=s.DATE,scope='Technical data audit; not independent clinical appraisal or a RAG quality evaluation',checks=checks,clinical_reviewed=False,embedding_called=False,llm_called=False,database_accessed=False)
 write(REPORT/'verification.json',verification)
 print(s.json_text(verification))

if __name__=='__main__':audit()
