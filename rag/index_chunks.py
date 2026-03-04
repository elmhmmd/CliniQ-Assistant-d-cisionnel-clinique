import json
import sys
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer



class E5Embeddings(Embeddings):
    def __init__(self, model_name: str = "intfloat/multilingual-e5-base"):
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"passage: {t}" for t in texts]
        return self.model.encode(prefixed, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(f"query: {text}", normalize_embeddings=True).tolist()



def index(chunks_path: str = "data/chunks.json", chroma_dir: str = "data/chroma_db") -> None:
    chunks_path = Path(chunks_path)
    chroma_dir  = Path(chroma_dir)

    print(f"Loading chunks from {chunks_path} ...")
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    print(f"  {len(chunks)} chunks loaded")

    print(f"\nLoading embedding model (multilingual-e5-base) ...")
    embeddings = E5Embeddings()

    texts     = [c["page_content"] for c in chunks]
    metadatas = [c["metadata"]     for c in chunks]
    ids       = [c["metadata"]["chunk_id"] for c in chunks]

    print(f"\nIndexing into ChromaDB at '{chroma_dir}' ...")
    vectorstore = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        ids=ids,
        persist_directory=str(chroma_dir),
        collection_name="protocols",
    )

    count = vectorstore._collection.count()
    print(f"  Done. Collection 'protocols' contains {count} documents.")

    print("\nSmoke test — querying: 'traitement diarrhée enfant déshydratation'")
    results = vectorstore.similarity_search(
        "traitement diarrhée enfant déshydratation", k=3
    )
    for i, doc in enumerate(results, 1):
        md = doc.metadata
        print(f"  [{i}] {md['chunk_id']}")
        print(f"       {doc.page_content[:120].replace(chr(10), ' ')} ...")

    print("\nSmoke test — querying: 'antibiotique angine ORL'")
    results = vectorstore.similarity_search("antibiotique angine ORL", k=3)
    for i, doc in enumerate(results, 1):
        md = doc.metadata
        print(f"  [{i}] {md['chunk_id']}")
        print(f"       {doc.page_content[:120].replace(chr(10), ' ')} ...")


if __name__ == "__main__":
    index(*sys.argv[1:3])
