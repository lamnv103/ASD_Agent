"""Prepare source-grounded evidence for one question, with input checks before retrieval.

    .venv-embedding\\Scripts\\python.exe -B -m rag.prepare_evidence "câu hỏi" --trace reports/my_trace.json

Same output as `python -m rag.read_evidence` (reader v3), plus an `input_guard` block.
rag/read_evidence.py is kept unchanged because accepted evaluation runs pin its hash.
No patient-facing answer is generated.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from .guarded_pipeline import GuardedEvidencePipeline
from .retriever import PostgresRetriever, RetrievalError, atomic_json
from .semantic_reader_v3 import AtomicNeedsReader


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("question")
    p.add_argument("--trace", help="write the full trace JSON here")
    p.add_argument("--cohere-key-file", help="dotenv file with COHERE_API_KEY (default: environment)")
    p.add_argument("--prompt-cohere-key", action="store_true", help="type the Cohere key (hidden)")
    p.add_argument("--nvidia-key-file", help="dotenv with NVIDIA_API_KEY or Continue YAML (default: environment)")
    args = p.parse_args()
    secret = None
    try:
        retriever = PostgresRetriever(key_file=args.cohere_key_file)
        retriever.health()
        if args.prompt_cohere_key:
            secret = getpass.getpass("Cohere query API key (hidden): ")
            retriever.embedder.key_supplier = lambda: secret
        pipe = GuardedEvidencePipeline(retriever)
        pipe.semantic_reader = AtomicNeedsReader(counter=pipe.counter, key_file=args.nvidia_key_file)
        trace = pipe.prepare(args.question, trace_path=args.trace)
        result = dict(
            status="ok",
            trace=str(Path(args.trace).resolve()) if args.trace else None,
            input_guard={k: v for k, v in trace["input_guard"].items() if k != "limitations"},
            assessment=trace["assessment_after_selection"],
            policy=trace["medical_policy_after_selection"],
            context_status=trace["context_selection"]["status"],
            context_token_budget=trace["context_selection"]["budget"],
            reader_protocol=trace["semantic_reader"].get("protocol"),
            model_calls=trace["semantic_reader"].get("calls", []),
            generation_enabled=False,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except RetrievalError as exc:  # includes EvidenceError
        result = dict(status="error", error_code=exc.code, message=str(exc), error_stage=getattr(exc, "stage", None),
                      model_calls=getattr(exc, "reader_calls", []), generation_enabled=False)
        if args.trace:
            atomic_json(args.trace, result)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    finally:
        secret = None


if __name__ == "__main__":
    sys.exit(main())
