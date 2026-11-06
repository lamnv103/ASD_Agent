"""Read-only retriever for the pinned 33-document Cohere embedding space."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import hashlib, json, math, os, ssl, tempfile, threading
from urllib import request, error
import certifi
import psycopg2
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PROFILE = dict(provider="cohere", model="embed-v4.0", dimensions=1536,
    document_input_type="search_document", query_input_type="search_query", truncate="NONE",
    max_tokens=128000, whole_document=True, pooling="native_model_single_input", schema_version=1)
ENDPOINT = "https://api.cohere.com/v2/embed"

def sha(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value,str) else value).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":"))

class RetrievalError(Exception):
    def __init__(self, code, message):
        self.code=code
        super().__init__(message)

def vector_checked(value):
    if not isinstance(value,list) or len(value)!=1536 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in value):
        raise RetrievalError("invalid_vector", "Expected 1536 finite numeric coordinates.")
    if not any(x!=0 for x in value):
        raise RetrievalError("invalid_vector", "Zero vector rejected.")
    return value

def atomic_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".pending-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:
            json.dump(value,f,ensure_ascii=False,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class CohereQueryEmbedder:
    """Embeds only queries; cache never contains source documents or API keys."""
    def __init__(self, space_id, *, cache_dir=None, key_file=None, key_supplier=None):
        self.space_id=space_id
        self.cache_dir=Path(cache_dir) if cache_dir else ROOT/"reports/retriever/query_cache"
        self.key_file=Path(key_file) if key_file else None
        self.key_supplier=key_supplier
        self._lock=threading.Lock()

    def _key(self):
        key=self.key_supplier() if self.key_supplier else None
        if not key and self.key_file:
            if not self.key_file.is_file(): raise RetrievalError("missing_key", "Cohere credential file does not exist.")
            key=dotenv_values(self.key_file,interpolate=False).get("COHERE_API_KEY")
        key=key or os.environ.get("COHERE_API_KEY")
        if not key: raise RetrievalError("missing_key", "Set COHERE_API_KEY or supply a Cohere dotenv file; do not use an NVIDIA key.")
        if key.startswith("nvapi-") or any(c in key for c in "\r\n"):
            raise RetrievalError("invalid_key", "Invalid credential for the Cohere endpoint.")
        return key

    def embed(self, query):
        identity=dict(schema_version=1, space_id=self.space_id, profile=PROFILE, query=query)
        path=self.cache_dir/(sha(canonical(identity))+".json")
        with self._lock:
            if path.exists():
                try:
                    cached=json.loads(path.read_text(encoding="utf-8"))
                    vec=vector_checked(cached["embedding"])
                    if cached["identity"]!=identity or cached["embedding_sha256"]!=sha(canonical(vec)):
                        raise ValueError("cache mismatch")
                except (ValueError,KeyError,TypeError,RetrievalError):
                    raise RetrievalError("cache_invalid", "Query cache failed validation; preserve it for inspection.") from None
                return vec,dict(cache_hit=True,provider_request_id=cached.get("provider_request_id"),usage=cached.get("usage"))
            payload=dict(model=PROFILE["model"],texts=[query],input_type="search_query",
                embedding_types=["float"],output_dimension=1536,truncate="NONE",max_tokens=128000)
            req=request.Request(ENDPOINT,data=json.dumps(payload).encode("utf-8"),method="POST",
                headers={"Content-Type":"application/json","Authorization":"Bearer "+self._key()})
            opener=request.build_opener(NoRedirect(),request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
            try:
                with opener.open(req,timeout=45) as response:
                    raw=response.read(2_000_000)
                body=json.loads(raw)
            except error.HTTPError as exc:
                code="provider_auth" if exc.code in (401,403) else "provider_rate_limit" if exc.code==429 else "provider_http"
                raise RetrievalError(code,"Cohere HTTP %s; credentials and response body omitted."%exc.code) from None
            except (error.URLError,TimeoutError,OSError):
                raise RetrievalError("provider_network", "Cohere request failed or timed out; no automatic repeat was sent.") from None
            except (ValueError,TypeError):
                raise RetrievalError("provider_response", "Invalid Cohere JSON response.") from None
            try:
                rows=body["embeddings"]["float"]
                if len(rows)!=1: raise ValueError("wrong row count")
                vec=vector_checked(rows[0])
                if "texts" in body and body["texts"]!=[query]: raise ValueError("echo mismatch")
            except (KeyError,TypeError,ValueError,RetrievalError):
                raise RetrievalError("provider_response", "Cohere response did not contain one valid query vector.") from None
            record=dict(identity=identity,embedding=vec,embedding_sha256=sha(canonical(vec)),
                provider_request_id=body.get("id"),usage=body.get("meta",{}))
            atomic_json(path,record)
            return vec,dict(cache_hit=False,provider_request_id=record["provider_request_id"],usage=record["usage"])

class PostgresRetriever:
    def __init__(self, config_file=None, *, database_env=None, key_file=None, key_supplier=None, embedder=None):
        self.config_file=Path(config_file) if config_file else ROOT/"deployments/retriever.json"
        try: self.config=json.loads(self.config_file.read_text(encoding="utf-8"))
        except (OSError,ValueError): raise RetrievalError("config_invalid", "Cannot read retriever configuration.") from None
        cfg=self.config
        if cfg.get("profile")!=PROFILE or cfg.get("document_count")!=33 or len(cfg.get("sources",{}))!=33:
            raise RetrievalError("config_invalid", "Unapproved embedding profile or source count.")
        if cfg.get("clinical_reviewed") is not False or cfg.get("production_ingest") is not False:
            raise RetrievalError("config_invalid", "This release is research-only and has no independent clinical approval.")
        self.database_env=Path(database_env) if database_env else ROOT/cfg["database_env"]
        self.embedder=embedder or CohereQueryEmbedder(cfg["space_id"],key_file=key_file,key_supplier=key_supplier)

    @contextmanager
    def _connection(self):
        try:
            settings=dotenv_values(self.database_env,interpolate=False)
            dsn=settings.get("RAG_DATABASE_URL")
            if not dsn: raise RetrievalError("database_config", "Missing RAG_DATABASE_URL in database dotenv file.")
            # Configuration must not silently override the approved provider/collection.
            checks={"RAG_COLLECTION":self.config["collection_id"],"RAG_EMBEDDING_SPACE":self.config["space_id"],"RAG_EMBEDDING_PROVIDER":"cohere","RAG_EMBEDDING_MODEL":"embed-v4.0","RAG_EMBEDDING_DIMENSIONS":"1536","RAG_WHOLE_DOCUMENT":"true"}
            for field,expected in checks.items():
                if settings.get(field) and settings[field]!=expected:
                    raise RetrievalError("database_config", "Database environment selects a different collection or embedding space.")
            conn=psycopg2.connect(dsn,connect_timeout=5,options="-c statement_timeout=20000 -c lock_timeout=5000")
            if conn.info.dbname!="asd_rag":
                conn.close(); raise RetrievalError("database_config", "Expected the asd_rag database.")
            conn.set_session(readonly=True,isolation_level="REPEATABLE READ",autocommit=False)
            try:
                with conn:
                    with conn.cursor() as cur: yield cur
            finally: conn.close()
        except psycopg2.Error:
            raise RetrievalError("database_error", "PostgreSQL operation failed; connection details omitted.") from None

    def _check(self, cur):
        cfg=self.config
        cur.execute("select corpus_sha256 from carobud_rag.collections where collection_id=%s",(cfg["collection_id"],))
        row=cur.fetchone()
        if not row or row[0]!=cfg["corpus_sha256"]: raise RetrievalError("database_integrity", "Collection release hash differs.")
        cur.execute("select profile,dimensions,verified from carobud_rag.embedding_spaces where space_id=%s",(cfg["space_id"],))
        row=cur.fetchone()
        if not row or row!=(PROFILE,1536,True): raise RetrievalError("database_integrity", "Embedding space is unverified or incompatible.")
        cur.execute("""select d.source_id,d.chunk_id,d.content_sha256,
          encode(sha256(convert_to(d.content,'UTF8')),'hex'),d.enabled,d.prototype_ingest,d.production_ingest,d.metadata,
          e.space_id,e.dimensions,encode(sha256(convert_to(e.embedding::text,'UTF8')),'hex')
          from carobud_rag.documents d left join carobud_rag.embeddings e using(collection_id,chunk_id)
          where d.collection_id=%s order by d.source_id""",(cfg["collection_id"],))
        rows=cur.fetchall()
        if len(rows)!=33 or {r[0] for r in rows}!=set(cfg["sources"]):
            raise RetrievalError("database_integrity", "Expected exactly 33 approved sources and one vector per document.")
        for sid,unit,stored,actual,enabled,prototype,production,meta,space,dims,vhash in rows:
            pin=cfg["sources"][sid]
            if (unit!="whole-document:"+sid or stored!=actual or actual!=pin["content_sha256"] or
                (enabled,prototype,production)!=(True,True,False) or space!=cfg["space_id"] or dims!=1536 or
                vhash!=pin["database_vector_sha256"] or meta.get("id")!=sid or meta.get("whole_document") is not True or
                meta.get("clinical_reviewed") is not False or meta.get("production_ingest") is not False or
                meta.get("source_release_sha256")!=cfg["corpus_sha256"] or meta.get("embedding_status")!="complete_whole_document" or sha(canonical(meta))!=pin["metadata_sha256"]):
                raise RetrievalError("database_integrity", "Source, vector, release or research-only metadata differs: "+sid)

    def health(self):
        with self._connection() as cur: self._check(cur)
        return dict(status="ok",collection_id=self.config["collection_id"],space_id=self.config["space_id"],documents=33,
            vectors=33,dimensions=1536,read_only=True,whole_document=True,clinical_reviewed=False,production_ingest=False)

    @staticmethod
    def _document(sid,content,digest,metadata):
        source=metadata.get("nguon",{})
        return dict(source_id=sid,title=metadata.get("ten_tai_lieu"),source=source,
            dates=metadata.get("ngay_thang"),scope=metadata.get("doi_chieu",{}),
            content_sha256=digest,content=content,clinical_reviewed=False,whole_document=True)

    def read_source(self,source_id):
        if not isinstance(source_id,str) or len(source_id)>100 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-" for c in source_id):
            raise RetrievalError("invalid_input", "Invalid source ID.")
        with self._connection() as cur:
            self._check(cur)
            if source_id not in self.config["sources"]: return dict(status="not_found",source_id=source_id)
            cur.execute("select source_id,content,content_sha256,metadata from carobud_rag.documents where collection_id=%s and source_id=%s",(self.config["collection_id"],source_id))
            doc=self._document(*cur.fetchone())
        return dict(status="ok",document=doc,collection_id=self.config["collection_id"])

    def retrieve(self,query,top_k=5,*,include_content=True):
        if not isinstance(query,str) or not query.strip() or len(query)>8000 or "\x00" in query:
            raise RetrievalError("invalid_input", "Query must contain 1–8000 characters without NUL.")
        if isinstance(top_k,bool) or not isinstance(top_k,int) or not 1<=top_k<=10:
            raise RetrievalError("invalid_input", "top_k must be an integer from 1 to 10.")
        self.health()  # Refuse incompatible data before spending an API call.
        vec,usage=self.embedder.embed(query)
        vector_checked(vec)
        with self._connection() as cur:
            self._check(cur)
            cur.execute("""select d.source_id,d.content,d.content_sha256,d.metadata,e.embedding <=> %s::vector as distance
                from carobud_rag.documents d join carobud_rag.embeddings e using(collection_id,chunk_id)
                where d.collection_id=%s and e.space_id=%s and d.enabled
                order by distance,d.source_id limit %s""",(json.dumps(vec),self.config["collection_id"],self.config["space_id"],top_k))
            results=[]
            for rank,row in enumerate(cur.fetchall(),1):
                doc=self._document(*row[:4]); doc.update(rank=rank,cosine_distance=float(row[4]))
                if not include_content: doc.pop("content")
                results.append(doc)
        return dict(status="ok",query=query,actual_query=query,collection_id=self.config["collection_id"],
            space_id=self.config["space_id"],model=PROFILE["model"],strategy="exact_cosine",top_k=top_k,results=results,
            query_embedding=usage,evidence_sufficiency="not_assessed",clinical_reviewed=False,
            note="Distances rank documents; they are not clinical confidence. Nearest matches can be irrelevant. No answer was generated.")
