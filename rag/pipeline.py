from __future__ import annotations

from rag.retriever import Retriever
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage


SYSTEM_PROMPT = """\
Tu es CliniQ, un assistant d'aide à la décision clinique pour les infirmiers de Polynésie française.
Tu réponds UNIQUEMENT à partir des protocoles médicaux fournis dans le contexte.
Si l'information demandée n'est pas dans les protocoles, dis-le clairement.
Réponds en français, de façon concise et structurée.\
"""

CONTEXT_TEMPLATE = """\
Protocoles pertinents :

{context}

---
Question : {question}\
"""


class Pipeline:
    def __init__(
        self,
        model:     str = "mistral",
        top_k:     int = 5,
        specialty: str | None = None,
    ):
        self.retriever = Retriever()
        self.llm = ChatOllama(model=model, temperature=0)
        self.top_k = top_k
        self.specialty = specialty

    def query(self, question: str, specialty: str | None = None) -> dict:
        sp = specialty or self.specialty
        chunks = self.retriever.search(question, k=self.top_k, specialty=sp)

        context = "\n\n---\n\n".join(
            f"[{c['specialty']} / {c['protocol']} / {c['section_header']}]\n"
            f"{c['page_content']}"
            for c in chunks
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=CONTEXT_TEMPLATE.format(
                context=context, question=question
            )),
        ]

        response = self.llm.invoke(messages)

        sources = [
            {k: v for k, v in c.items() if k != "page_content"}
            for c in chunks
        ]

        return {"answer": response.content, "sources": sources}
