"""Frozen-source retrieval evaluation; no answer generation, DML or corpus embedding."""
from __future__ import annotations
import argparse,csv,getpass,io,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from rag.retriever import PostgresRetriever,RetrievalError,sha,canonical,atomic_json
INPUTS=ROOT/"evaluation/retrieval_v1"

def snapshot(retriever):
    out={}
    with retriever._connection() as cur:
        for table in ["collections","documents","embedding_spaces","embeddings"]:
            # Table identifiers are constants above, never user input.
            cur.execute("select md5(row_to_json(t)::text) from carobud_rag."+table+" t order by 1")
            hashes=[r[0] for r in cur.fetchall()];out[table]=dict(rows=len(hashes),sha256=sha(canonical(hashes)))
        cur.execute("select md5(row_to_json(t)::text) from asd_knowledge_v2_pilot.chunks t order by 1")
        hashes=[r[0] for r in cur.fetchall()];out["legacy_curated_chunks"]=dict(rows=len(hashes),sha256=sha(canonical(hashes)))
    manifest=json.loads((ROOT/"knowledge/rag/source_library/SUPPLEMENT_20261030_MANIFEST.json").read_text(encoding="utf-8"))
    for name,info in manifest["files"].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to((ROOT/"knowledge/rag/source_library").resolve()) or sha(path.read_bytes())!=info["sha256"]:
            raise RetrievalError("source_changed","Protected source file changed: "+name)
    out["protected_files"]=dict(count=len(manifest["files"]),manifest_sha256=sha(canonical(manifest)))
    return out

def load_inputs(retriever):
    frozen=json.loads((INPUTS/"frozen_inputs.json").read_text(encoding="utf-8"))
    for name,expected in frozen["files"].items():
        if sha((INPUTS/name).read_bytes())!=expected: raise RetrievalError("labels_changed","Frozen evaluation inputs changed.")
    questions=[json.loads(line) for line in (INPUTS/"questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    labels=json.loads((INPUTS/"reference_labels.json").read_text(encoding="utf-8"))["labels"]
    if len(questions)!=30 or len({q["question_id"] for q in questions})!=30 or {q["question_id"] for q in questions}!={l["question_id"] for l in labels}:
        raise RetrievalError("labels_invalid","Question and reference IDs do not match.")
    by_id={l["question_id"]:l for l in labels};documents={}
    for lab in labels:
        for ev in lab["references"]:
            sid=ev["source_id"]
            if sid not in documents:
                source=retriever.read_source(sid)
                if source["status"]!="ok": raise RetrievalError("labels_invalid","Expected source is unavailable.")
                documents[sid]=source["document"]
            doc=documents[sid];start,end=ev["start"],ev["end"]
            if not (0<=start<end<=len(doc["content"])) or doc["content_sha256"]!=ev["content_sha256"] or doc["content"][start:end]!=ev["quote"]:
                raise RetrievalError("labels_invalid","Evidence span does not match PostgreSQL: "+sid)
    return questions,by_id,frozen

def score(question,label,result):
    expected=sorted({e["source_id"] for e in label["references"]})
    hits=result.get("results",[]);ids=[d["source_id"] for d in hits]
    actual={d["source_id"]:d for d in hits};matched=[]
    for ev in label["references"]:
        d=actual.get(ev["source_id"])
        if d and d["content_sha256"]==ev["content_sha256"] and d["content"][ev["start"]:ev["end"]]==ev["quote"]:
            matched.append(ev["support"])
    if result["status"]!="ok": support="LOI_THUC_THI"
    elif question["case_type"]=="insufficient": support="KHO_CHUA_DU_CAN_CU_CAN_KIEM_TRA_TU_CHOI"
    elif "DU" in matched: support="DU_THEO_NHAN_AI_CAN_DUYET"
    elif "MOT_PHAN" in matched: support="MOT_PHAN_THEO_NHAN_AI_CAN_DUYET"
    elif "GIOI_HAN" in matched: support="CHI_GIAI_THICH_GIOI_HAN"
    else: support="KHONG_TIM_THAY_NGUON_DA_GAN_NHAN_CAN_DOC_NGUON_KHAC"
    ranks=[i+1 for i,sid in enumerate(ids) if sid in expected]
    return dict(question_id=question["question_id"],question=question["question"],actual_query=result.get("actual_query",question["query"]),
        case_type=question["case_type"],expected_sources=";".join(expected),top5_source_ids=";".join(ids),
        evidence_sufficiency=support,status=result["status"],error_code=result.get("error_code",""),
        hit_at_5=bool(ranks) if expected and result["status"]=="ok" else None,
        reciprocal_rank=1/min(ranks) if ranks else 0.0,
        labeled_source_recall_at_5=len(set(ids)&set(expected))/len(expected) if expected else None,
        query_cache_hit=result.get("query_embedding",{}).get("cache_hit"),notes=label["expected_behavior"])

def metrics(rows,case_type):
    eligible=[r for r in rows if r["case_type"]==case_type]
    completed=[r for r in eligible if r["status"]=="ok"]
    return dict(eligible_questions=len(eligible),successful_queries=len(completed),execution_errors=len(eligible)-len(completed),
        hit_at_5=sum(bool(r["hit_at_5"]) for r in completed)/len(completed) if completed else None,
        mrr_at_5=sum(r["reciprocal_rank"] for r in completed)/len(completed) if completed else None,
        labeled_source_recall_at_5=sum(r["labeled_source_recall_at_5"] for r in completed)/len(completed) if completed else None,
        metric_denominator="successful queries with independently source-read candidate labels; reference sets are not exhaustive")

def run(args):
    secret=getpass.getpass("Cohere API key (hidden): ") if args.prompt_key else None
    retriever=PostgresRetriever(key_file=args.key_file,key_supplier=(lambda:secret) if secret else None)
    retriever.health();questions,labels,frozen=load_inputs(retriever)
    out=ROOT/"reports/retrieval_evaluation"/("R33_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f"));out.mkdir(parents=True)
    for name in ["questions.jsonl","reference_labels.json","frozen_inputs.json"]: (out/name).write_bytes((INPUTS/name).read_bytes())
    atomic_json(out/"retriever_config.json",retriever.config)
    before=snapshot(retriever);atomic_json(out/"before.json",before)
    rows=[];retrieved={};started=datetime.now(timezone.utc).isoformat();terminal_error=None
    atomic_json(out/"status.json",dict(status="running",started_at=started,planned_questions=len(questions)))
    print("RUN_DIR="+str(out),flush=True)
    try:
        with (out/"raw_results.jsonl").open("w",encoding="utf-8") as raw:
            for q in questions:
                tick=time.monotonic()
                try: result=retriever.retrieve(q["query"],5,include_content=True)
                except RetrievalError as exc: result=dict(status="error",error_code=exc.code,message=str(exc),actual_query=q["query"])
                row=score(q,labels[q["question_id"]],result);row["elapsed_seconds"]=round(time.monotonic()-tick,3);rows.append(row)
                for doc in result.get("results",[]): retrieved[doc["source_id"]]=doc
                stored=dict(result)
                stored["results"]=[{k:v for k,v in doc.items() if k!="content"} for doc in result.get("results",[])]
                raw.write(json.dumps(dict(question_id=q["question_id"],result=stored,evaluation=row),ensure_ascii=False)+"\n");raw.flush()
                print(q["question_id"],result["status"],row["top5_source_ids"],flush=True)
                if result["status"]!="ok":
                    terminal_error=result["error_code"];break  # Preserve progress, do not repeatedly send a failing API request.
        with (out/"retrieved_sources.jsonl").open("w",encoding="utf-8") as stream:
            for sid,doc in sorted(retrieved.items()):
                doc={k:v for k,v in doc.items() if k not in ("rank","cosine_distance")}
                stream.write(json.dumps(doc,ensure_ascii=False)+"\n")
        with (out/"ket_qua.csv").open("w",encoding="utf-8-sig",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        after=snapshot(retriever);atomic_json(out/"after.json",after)
        unchanged=before==after
        complete=len(rows)==len(questions) and all(r["status"]=="ok" for r in rows) and unchanged
        summary=dict(status="complete" if complete else "partial_or_failed",started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),
            planned_questions=30,processed_questions=len(rows),successful_queries=sum(r["status"]=="ok" for r in rows),
            direct=metrics(rows,"direct"),scope_limit=metrics(rows,"scope_limit"),insufficient_questions=sum(r["case_type"]=="insufficient" for r in rows),
            insufficient_excluded_from_recall=True,query_api_calls=sum(r["query_cache_hit"] is False for r in rows),
            query_cache_hits=sum(r["query_cache_hit"] is True for r in rows),database_and_protected_sources_unchanged=unchanged,
            terminal_error=terminal_error,answer_generation_performed=False,independent_clinical_review=False,
            references_exhaustive=False,unknown_returned_sources_automatically_irrelevant=False,
            unmatched_labeled_questions=[r["question_id"] for r in rows if r["case_type"]!="insufficient" and r["hit_at_5"] is False],
            review_required="Inspect returned bodies and candidate labels; clinical sufficiency and abstention are not established by source hit metrics.")
        atomic_json(out/"summary.json",summary);atomic_json(out/"status.json",dict(status=summary["status"],processed_questions=len(rows)))
        lines=["# Đánh giá retriever PostgreSQL — 33 tài liệu", "", "Chỉ đánh giá tìm nguồn; không sinh câu trả lời. Nhãn do AI đọc nguồn trước khi chạy, chưa được chuyên gia độc lập duyệt.","",f"- Trạng thái: {summary['status']}; chạy thành công {summary['successful_queries']}/30 câu.",f"- Database và 132 tệp nguồn giữ nguyên: {unchanged}.",f"- Câu trực tiếp: {summary['direct']}",f"- Câu giới hạn phạm vi: {summary['scope_limit']}","- Ba câu không đủ căn cứ được loại khỏi mẫu số recall. Trả về top 5 không có nghĩa hệ thống biết từ chối.","- DU/MOT_PHAN chỉ áp dụng nếu bằng chứng đã gán nhãn thực sự có trong toàn văn được trả về. Nguồn khác chưa gán nhãn cần đọc bổ sung.","- Chưa đo độ đúng câu trả lời, độ đúng trích dẫn, khả năng từ chối hay hiệu quả tư vấn y tế.","", "Xem ket_qua.csv, raw_results.jsonl, retrieved_sources.jsonl và các input/hash đã đóng băng trong cùng thư mục.",""]
        (out/"BAO_CAO.md").write_text("\n".join(lines),encoding="utf-8")
        print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
        return 0 if complete else 1
    finally: secret=None

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--key-file");parser.add_argument("--prompt-key",action="store_true")
    try: sys.exit(run(parser.parse_args()))
    except RetrievalError as exc:
        print(json.dumps(dict(status="error",error_code=exc.code,message=str(exc)),ensure_ascii=False));sys.exit(1)
