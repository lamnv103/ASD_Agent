"""Internal prototype: Vietnamese answer with checked citations (answer_contract_v0.1).

    # answer layer only, on an existing evidence trace (context already prepared):
    .venv-embedding\\Scripts\\python.exe -B -m rag.answer --from-trace path\\to\\trace.json --out result.json
    # full flow for a SYNTHETIC question (emergency check -> input guard -> retrieval -> reader -> answer):
    .venv-embedding\\Scripts\\python.exe -B -m rag.answer "câu hỏi" --out result.json

NVIDIA key: environment variable NVIDIA_API_KEY or --nvidia-key-file some.env (YAML and the root .env
are refused). Output is marked "NGUYÊN MẪU NỘI BỘ" and chua_duyet: not for real users, not a pilot basis.
Use synthetic questions without real personal data only; --no-cache keeps nothing on disk for this layer.
--offline replays the answer cache only (no key read, no connection); it cannot be combined with --no-cache.
--as-of YYYY-MM-DD pins the reference date used by date-dependent source notes (replays must pin it).
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import date
from pathlib import Path

from .answer_client import AnswerNimClient, read_answer_key
from .answer_layer import answer_from_trace, emergency_result
from .answer_policy import detect_emergency, load_config
from .retriever import atomic_json


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("question", nargs="?")
    p.add_argument("--from-trace", help="run only the answer layer on this evidence trace JSON")
    p.add_argument("--out", help="write the full answer result JSON here")
    p.add_argument("--trace-out", help="full flow: also write the evidence trace here")
    p.add_argument("--nvidia-key-file", help="dotenv *.env file with NVIDIA_API_KEY (default: environment)")
    p.add_argument("--cohere-key-file", help="full flow: dotenv file with COHERE_API_KEY (default: environment)")
    p.add_argument("--prompt-cohere-key", action="store_true", help="full flow: type the Cohere key (hidden)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--no-cache", action="store_true", help="do not read or write the answer-layer cache")
    mode.add_argument("--offline", action="store_true", help="answer cache only; never read the key or open a connection")
    p.add_argument("--cache-dir", help="answer-layer cache folder (default reports/answer_cache)")
    p.add_argument("--as-of", type=date.fromisoformat, help="reference date YYYY-MM-DD (default: today)")
    args = p.parse_args()
    if bool(args.question) == bool(args.from_trace):
        p.error("give either a question or --from-trace")
    if args.offline and not args.from_trace:
        p.error("--offline works with --from-trace only (the full flow needs retrieval and the reader)")
    cfg = load_config()
    secret = None
    try:
        if args.from_trace:
            trace = json.loads(Path(args.from_trace).read_text(encoding="utf-8"))
            question = trace["question"]
        else:
            question = args.question
        hits = detect_emergency(question, cfg)
        if hits:  # before ANY provider call
            result = emergency_result(question, cfg, hits)
        else:
            from .retriever import ROOT
            from .tokenization import load_counter
            if args.from_trace:
                counter = load_counter(json.loads((ROOT / "deployments/evidence_context.json").read_text(encoding="utf-8")))
            else:
                from .guarded_pipeline import GuardedEvidencePipeline
                from .retriever import PostgresRetriever
                from .semantic_reader_v3 import AtomicNeedsReader
                retriever = PostgresRetriever(key_file=args.cohere_key_file)
                retriever.health()
                if args.prompt_cohere_key:
                    secret = getpass.getpass("Cohere query API key (hidden): ")
                    retriever.embedder.key_supplier = lambda: secret
                pipe = GuardedEvidencePipeline(retriever)
                # Same key rule for the reader: never fall back to Continue's YAML.
                pipe.semantic_reader = AtomicNeedsReader(counter=pipe.counter,
                                                         key_supplier=lambda: read_answer_key(args.nvidia_key_file))
                trace = pipe.prepare(question, trace_path=args.trace_out)
                counter = pipe.counter
            client = AnswerNimClient(counter, key_file=args.nvidia_key_file, use_cache=not args.no_cache,
                                     offline=args.offline, cache_dir=args.cache_dir)
            result = answer_from_trace(trace, client=client, as_of=args.as_of)
            if not args.from_trace:
                result["reader_calls"] = trace["semantic_reader"].get("calls", [])
                result["input_guard"] = {k: v for k, v in trace.get("input_guard", {}).items() if k != "limitations"}
        if args.out:
            atomic_json(args.out, result)
        print(result["render"]["text"])
        print(json.dumps(dict(route=result["route"], status=result["status"], error=result["error"], repairs=result["repairs"],
                              removed=len(result["claims_removed"]), timings=result["timings"],
                              out=str(Path(args.out).resolve()) if args.out else None), ensure_ascii=False))
        return 0 if result["route"] != "system_error" else 1
    except Exception as exc:  # pipeline/retrieval failure before the answer layer
        print(json.dumps(dict(route="system_error", error=getattr(exc, "code", type(exc).__name__)), ensure_ascii=False))
        return 1
    finally:
        secret = None


if __name__ == "__main__":
    sys.exit(main())
