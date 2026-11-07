"""Lab check: one chat call to an NVIDIA-hosted model through LangChain (NOT part of the RAG pipeline).

Run it with the separate lab environment, never with .venv-embedding:
    .venv-lab\\Scripts\\python.exe app.py

Key: NVIDIA_API_KEY from the environment, else secrets/nvidia.env (git-ignored). No key in code.
TLS: certificate verification stays ON. A stale CURL_CA_BUNDLE/REQUESTS_CA_BUNDLE that points to a
missing file (this machine: an old E: path) is dropped for this process only, so requests falls back
to its default CA bundle (certifi). If verification still fails, fix the CA configuration; do not
disable verification.
"""
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
MODEL = "mistralai/mistral-large-4-1t-a52b"


def load_key():
    key = os.environ.get("NVIDIA_API_KEY") or dotenv_values(ROOT / "secrets/nvidia.env").get("NVIDIA_API_KEY")
    if not key or not key.startswith("nvapi-"):
        sys.exit("NVIDIA_API_KEY is empty: paste the new key into secrets/nvidia.env (NVIDIA_API_KEY=nvapi-...).")
    return key


def drop_missing_ca_bundles():
    for var in ("CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        path = os.environ.get(var)
        if path is not None and not Path(path).is_file():
            print(f"[tls] {var} points to a missing file; ignoring it for this process (verification stays on).",
                  file=sys.stderr)
            os.environ.pop(var)


def main():
    drop_missing_ca_bundles()
    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    client = ChatNVIDIA(model=MODEL, api_key=load_key(), temperature=0.5, top_p=1, max_completion_tokens=4096)
    response = client.invoke("Xin chào, hãy giới thiệu ngắn gọn về bản thân bạn.", reasoning_effort="high")
    print("--- Response ---")
    print(response.content)


if __name__ == "__main__":
    main()
