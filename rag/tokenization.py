"""Pinned, local-only tokenizer adapter. Never estimates tokens from characters."""
from pathlib import Path
from collections.abc import Mapping
from .retriever import ROOT,sha
from .evidence import EvidenceError,require

class HuggingFaceCounter:
    def __init__(self,config):
        self.config=config;tok=config['tokenizer'];directory=(ROOT/tok['directory']).resolve()
        require(tok.get('kind')=='huggingface_local','tokenizer_config','Unsupported tokenizer adapter.')
        hashes=tok.get('artifact_hashes',{})
        require({'tokenizer.json','tokenizer_config.json','chat_template.jinja'}<=set(hashes),'tokenizer_config','Missing pinned tokenizer/template hashes.')
        for name,digest in hashes.items():
            path=(directory/name).resolve()
            require(path.is_relative_to(directory) and path.is_file() and sha(path.read_bytes())==digest,'tokenizer_integrity','Local tokenizer asset hash differs: '+name)
        try:
            from transformers import AutoTokenizer
            self.tokenizer=AutoTokenizer.from_pretrained(str(directory),local_files_only=True,trust_remote_code=False)
            require(bool(self.tokenizer.chat_template),'tokenizer_config','No official chat template was loaded.')
        except (ImportError,OSError,ValueError) as exc:
            raise EvidenceError('tokenizer_unavailable','Cannot load the pinned local tokenizer/chat template; no approximate fallback.') from None
        self.profile=dict(kind='huggingface_local',model_id=config['model_id'],repository=tok['repository'],revision=tok['revision'],
            artifact_hashes=hashes,request_profile=tok['request_profile'],exactness='exact_for_pinned_local_chat_template',
            hosted_endpoint_prompt_token_parity_verified=False)

    def count_messages(self,messages):
        p=self.config['tokenizer']['request_profile']
        try:
            ids=self.tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=p['add_generation_prompt'],
                truncation=False,**p.get('template_kwargs',{}))
        except Exception:
            raise EvidenceError('tokenizer_failed','Official chat-template tokenization failed; input was not truncated.') from None
        if isinstance(ids,Mapping):ids=ids['input_ids']
        require(isinstance(ids,list) and all(type(x) is int for x in ids),'tokenizer_failed','Tokenizer returned an unexpected token ID format.')
        return len(ids)

def load_counter(config):
    if config.get('tokenizer',{}).get('kind')=='unconfigured':return None
    return HuggingFaceCounter(config)
