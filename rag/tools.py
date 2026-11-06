"""Model-independent tools. A chat agent may call these without a subprocess."""
from .retriever import PostgresRetriever, RetrievalError
TOOL_SCHEMAS=[
 {"type":"function","function":{"name":"search_sources","description":"Find whole documents in the research ASD library. Read returned sources before answering; similarity does not prove relevance or sufficiency.","parameters":{"type":"object","properties":{"query":{"type":"string"},"top_k":{"type":"integer","minimum":1,"maximum":10}},"required":["query"],"additionalProperties":False}}},
 {"type":"function","function":{"name":"read_source","description":"Read the complete original document and attribution from PostgreSQL by source ID. Do not invent attribution or omit source limitations.","parameters":{"type":"object","properties":{"source_id":{"type":"string"}},"required":["source_id"],"additionalProperties":False}}}
]
class RAGTools:
    def __init__(self,retriever=None,**kwargs): self.retriever=retriever or PostgresRetriever(**kwargs)
    def search_sources(self,query,top_k=5): return self.retriever.retrieve(query,top_k,include_content=False)
    def read_source(self,source_id): return self.retriever.read_source(source_id)
    def dispatch(self,name,arguments):
        try:
            if not isinstance(arguments,dict): raise RetrievalError("invalid_input","Tool arguments must be an object.")
            allowed={"search_sources":{"query","top_k"},"read_source":{"source_id"}}
            if name not in allowed or not set(arguments)<=allowed[name]: raise RetrievalError("invalid_input","Unknown tool or argument.")
            required="query" if name=="search_sources" else "source_id"
            if required not in arguments: raise RetrievalError("invalid_input","Missing required tool argument.")
            return getattr(self,name)(**arguments)
        except RetrievalError as exc: return dict(status="error",error_code=exc.code,message=str(exc))
