import copy,json,math,tempfile,unittest
from urllib.error import HTTPError
import io
from pathlib import Path
from unittest.mock import patch
from rag.retriever import PostgresRetriever,CohereQueryEmbedder,RetrievalError,PROFILE,ROOT,canonical,sha,vector_checked,atomic_json
from rag.tools import RAGTools
class RetrieverTests(unittest.TestCase):
    def test_bad_vectors(self):
        for vec in [[],[0]*1536,[True]*1536,[float("nan")]*1536,[float("inf")]*1536]:
            with self.subTest(kind=str(vec[:1])):
                with self.assertRaises(RetrievalError):vector_checked(vec)
    def test_configuration_rejects_wrong_space_profile(self):
        cfg=json.loads((ROOT/"deployments/retriever.json").read_text(encoding="utf-8"));cfg["profile"]["model"]="other"
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"config.json";atomic_json(path,cfg)
            with self.assertRaises(RetrievalError):PostgresRetriever(path)
    def test_cache_hit_needs_no_api_or_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=CohereQueryEmbedder("test",cache_dir=tmp);query="full original query "
            identity=dict(schema_version=1,space_id="test",profile=PROFILE,query=query);vec=[0.01]*1536
            atomic_json(Path(tmp)/(sha(canonical(identity))+".json"),dict(identity=identity,embedding=vec,embedding_sha256=sha(canonical(vec))))
            with patch.object(e,"_key",side_effect=AssertionError("must not request key")):
                got,usage=e.embed(query)
            self.assertEqual(got,vec);self.assertTrue(usage["cache_hit"])
    def test_tampered_cache_fails_without_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=CohereQueryEmbedder("test",cache_dir=tmp);identity=dict(schema_version=1,space_id="test",profile=PROFILE,query="q")
            atomic_json(Path(tmp)/(sha(canonical(identity))+".json"),dict(identity=identity,embedding=[1.0]*1536,embedding_sha256="wrong"))
            with self.assertRaises(RetrievalError) as caught:e.embed("q")
            self.assertEqual(caught.exception.code,"cache_invalid")
    def test_nvidia_key_not_sent_to_cohere(self):
        e=CohereQueryEmbedder("test",key_supplier=lambda:"nvapi-example")
        with self.assertRaises(RetrievalError):e._key()
    def test_invalid_query_and_topk_before_db(self):
        r=PostgresRetriever()
        for query,k in [("",5),("q",True),("q",11),(None,5),("\x00",5),("a"*8001,5)]:
            with self.subTest(query=str(query)[:15],k=k):
                with self.assertRaises(RetrievalError):r.retrieve(query,k)
    def test_tools_do_not_execute_unknown_calls(self):
        tools=RAGTools()
        for name,args in [("sql",{}),("search_sources",{"query":"q","sql":"drop"}),("read_source",{})]:
            self.assertEqual(tools.dispatch(name,args)["error_code"],"invalid_input")
    def test_database_error_not_empty_result(self):
        tools=RAGTools()
        with patch.object(tools.retriever,"retrieve",side_effect=RetrievalError("database_error","unavailable")):
            result=tools.dispatch("search_sources",{"query":"q"})
        self.assertEqual(result["status"],"error");self.assertNotIn("results",result)
    def test_provider_payload_is_query_only_and_no_truncation(self):
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps(dict(id="test-request",embeddings={"float":[[0.02]*1536]})).encode()
        with tempfile.TemporaryDirectory() as tmp:
            e=CohereQueryEmbedder("test",cache_dir=tmp,key_supplier=lambda:"dummy-unit-test-key")
            with patch("rag.retriever.request.build_opener") as build:
                build.return_value.open.return_value=Reply()
                _,meta=e.embed("original Vietnamese query")
                req=build.return_value.open.call_args.args[0];payload=json.loads(req.data)
                self.assertEqual(payload["texts"],["original Vietnamese query"])
                self.assertEqual(payload["input_type"],"search_query");self.assertEqual(payload["truncate"],"NONE")
                self.assertEqual(payload["output_dimension"],1536);self.assertFalse(meta["cache_hit"])
            self.assertNotIn("dummy-unit-test-key",next(Path(tmp).glob("*.json")).read_text())
    def test_provider_failures_are_not_retried_or_cached(self):
        for status,expected in [(401,"provider_auth"),(429,"provider_rate_limit")]:
            with self.subTest(status=status),tempfile.TemporaryDirectory() as tmp:
                e=CohereQueryEmbedder("test",cache_dir=tmp,key_supplier=lambda:"dummy-unit-test-key")
                with patch("rag.retriever.request.build_opener") as build:
                    build.return_value.open.side_effect=HTTPError("https://api.cohere.com",status,"failed",{},io.BytesIO(b"sensitive-response"))
                    with self.assertRaises(RetrievalError) as caught:e.embed("q")
                    self.assertEqual(caught.exception.code,expected);self.assertNotIn("sensitive-response",str(caught.exception))
                    self.assertEqual(build.return_value.open.call_count,1)
                self.assertFalse(list(Path(tmp).glob("*.json")))
    def test_source_id_traversal_rejected(self):
        with self.assertRaises(RetrievalError):PostgresRetriever().read_source("../../.env")

class LiveReadOnlyTests(unittest.TestCase):
    def test_real_db_fulltext_and_blocked_sources(self):
        r=PostgresRetriever();self.assertEqual(r.health()["vectors"],33)
        doc=r.read_source("ASD-NEW-003")["document"]
        self.assertGreater(len(doc["content"]),150000);self.assertEqual(sha(doc["content"]),doc["content_sha256"])
        for sid in ["ASD-CSV-017","KB-ASD-01","asha_aac_portal"]:self.assertEqual(r.read_source(sid)["status"],"not_found")
    def test_integrity_refuses_changed_vector_and_content_pin(self):
        r=PostgresRetriever();r.config=copy.deepcopy(r.config)
        r.config["sources"]["ASD-NEW-003"]["database_vector_sha256"]="wrong"
        with self.assertRaises(RetrievalError) as caught:r.health()
        self.assertEqual(caught.exception.code,"database_integrity")
    def test_integrity_checks_content_and_attribution(self):
        for field in ["content_sha256","metadata_sha256"]:
            r=PostgresRetriever();r.config=copy.deepcopy(r.config);r.config["sources"]["ASD-NEW-003"][field]="wrong"
            with self.subTest(field=field),self.assertRaises(RetrievalError):r.health()
    def test_real_cached_query_reads_fulltext_from_database_without_api(self):
        r=PostgresRetriever()
        with patch.object(r.embedder,"_key",side_effect=AssertionError("cached query must need no key")):
            result=r.retrieve("Trẻ tự kỷ kén ăn cần đánh giá dinh dưỡng và tiền sử ăn uống như thế nào?",5)
        self.assertTrue(result["query_embedding"]["cache_hit"])
        self.assertEqual(result["results"][0]["source_id"],"ASD-NEW-003")
        self.assertGreater(len(result["results"][0]["content"]),150000)
        for doc in result["results"]:self.assertEqual(sha(doc["content"]),doc["content_sha256"])
    def test_real_db_readonly(self):
        r=PostgresRetriever()
        with r._connection() as cur:
            cur.execute("show transaction_read_only");self.assertEqual(cur.fetchone()[0],"on")
            cur.execute("show transaction_isolation");self.assertEqual(cur.fetchone()[0],"repeatable read")

if __name__=="__main__":unittest.main(verbosity=2)
