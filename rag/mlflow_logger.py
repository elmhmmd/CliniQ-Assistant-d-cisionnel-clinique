from __future__ import annotations

import json
import logging
import os

import mlflow
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
)
from deepeval.test_case import LLMTestCase
from ollama import Client as OllamaClient

logger = logging.getLogger(__name__)

EXPERIMENT = "cliniq-rag"

# Static RAG config logged as params on every run
RAG_CONFIG = {
    "chunking_strategy":       "section-based",
    "chunking_overlap":        0,
    "embedding_model":         "intfloat/multilingual-e5-base",
    "embedding_dim":           768,
    "embedding_normalization": True,
    "similarity_metric":       "cosine",
    "retrieval_candidate_k":   20,
    "reranker_model":          "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
}


class _OllamaEvalModel(DeepEvalBaseLLM):
    """Wraps Ollama so DeepEval can use it for metric evaluation."""

    def __init__(self) -> None:
        self._model = os.getenv("OLLAMA_MODEL", "mistral")
        self._host  = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    def load_model(self) -> OllamaClient:
        return OllamaClient(host=self._host)

    def generate(self, prompt: str) -> str:
        return self.load_model().generate(model=self._model, prompt=prompt).response

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self) -> str:
        return f"ollama/{self._model}"


def setup_mlflow(tracking_uri: str) -> None:
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT)


def log_query(
    question:        str,
    answer:          str,
    contexts:        list[str],
    response_time_ms: float,
    llm_model:       str,
    top_k:           int,
    system_prompt:   str,
) -> None:
    try:
        with mlflow.start_run():
            # RAG config + LLM hyperparams
            mlflow.log_params({
                **RAG_CONFIG,
                "llm_model":           llm_model,
                "temperature":         0,
                "retrieval_top_k":     top_k,
                "system_prompt_chars": len(system_prompt),
            })

            # Response time
            mlflow.log_metric("response_time_ms", response_time_ms)

            # Artifacts
            mlflow.log_text(question,                                            "question.txt")
            mlflow.log_text(answer,                                              "answer.txt")
            mlflow.log_text(json.dumps(contexts, ensure_ascii=False, indent=2),  "contexts.json")
            mlflow.log_text(system_prompt,                                       "system_prompt.txt")

            # DeepEval metrics
            eval_model = _OllamaEvalModel()
            test_case  = LLMTestCase(
                input=question,
                actual_output=answer,
                expected_output=answer,   # proxy — no ground truth available
                retrieval_context=contexts,
            )

            metrics = [
                AnswerRelevancyMetric(    model=eval_model, threshold=0.5),
                FaithfulnessMetric(       model=eval_model, threshold=0.5),
                ContextualPrecisionMetric(model=eval_model, threshold=0.5),
                ContextualRecallMetric(   model=eval_model, threshold=0.5),
            ]

            for metric in metrics:
                try:
                    metric.measure(test_case)
                    mlflow.log_metric(metric.__class__.__name__, metric.score)
                except Exception as e:
                    logger.warning("DeepEval metric %s failed: %s", metric.__class__.__name__, e)

    except Exception as e:
        logger.error("MLflow logging failed: %s", e)
