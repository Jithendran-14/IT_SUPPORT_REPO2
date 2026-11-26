"""Reusable local retrieval. Repair the three marked query-config fields."""
import json
import math
import os

from iat_common.db import OracleDB
from iat_common.models.database import IATDBConfig
from iat_rag_retrieval.models import RetrievalQueryConfig
from iat_rag_retrieval.retriever import IATRAGRetriever

from local_embeddings import LocalQwenEmbeddings


WORKSHOP_USER = "IT_SUPPORT_WORKSHOP"


def build_query_config(question, query_vector, limit):
    """Used by both the offline checks and the actual SDK retrieval call."""
    return RetrievalQueryConfig(
        query="""
            SELECT
                id AS CHUNK_ID,
                text AS CONTENT,
                1 - VECTOR_DISTANCE(
                    embedding,
                    TO_VECTOR(:query_vector, 1024, FLOAT32),
                    COSINE
                ) AS SCORE,
                metadata AS METADATA
            FROM IT_SUPPORT_EMBEDDINGS
            ORDER BY SCORE DESC, CHUNK_ID
            FETCH FIRST :result_limit ROWS ONLY
        """,
        params={
            "query_vector": question,  # R2-1: Bind the generated query embedding.
            "result_limit": limit,
        },
        id_col="CHUNK_ID",
        content_col="TEXT",  # R2-2: Map the returned content column.
        score_col="SCORE",
        additional_metadata_cols=[],  # R2-3: Preserve source metadata.
        retrieval_source="it_support_workshop_oracle",
        retrieval_method="semantic",
    )


def decode_metadata(value):
    if hasattr(value, "read"):
        value = value.read()
    if isinstance(value, (str, bytes, bytearray)):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON metadata object.")
    return value


async def search_support_knowledge(question, limit=3):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must not be empty.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise ValueError("Result limit must be an integer from 1 to 5.")
    for name in ("IAT_IT_USER", "IAT_IT_PASSWORD", "IAT_IT_DSN"):
        if not os.environ.get(name):
            raise RuntimeError(f"Setup: missing {name}. See README.md.")
    if os.environ["IAT_IT_USER"].upper() != WORKSHOP_USER:
        raise RuntimeError("Use IT_SUPPORT_WORKSHOP; the main application's user is blocked.")

    print("Generating local query embedding...")
    query_vector = await LocalQwenEmbeddings().aembed_query(question.strip())
    if (
        len(query_vector) != 1024
        or not all(math.isfinite(float(v)) for v in query_vector)
        or not any(query_vector)
    ):
        raise ValueError("Expected a finite, nonzero 1024-dimensional query vector.")
    print("Query dimensions:", len(query_vector))

    database = OracleDB(
        config=IATDBConfig(
            user=os.environ["IAT_IT_USER"],
            password=os.environ["IAT_IT_PASSWORD"],
            dsn=os.environ["IAT_IT_DSN"],
            min_pool_size=1,
            max_pool_size=2,
        ),
        auth_config=None,
    )
    try:
        identity = await database.dql(
            "SELECT USER AS USERNAME, SYS_CONTEXT('USERENV', 'CON_NAME') AS CONTAINER_NAME FROM dual",
            {},
        )
        if (
            identity["USERNAME"].iloc[0] != WORKSHOP_USER
            or identity["CONTAINER_NAME"].iloc[0] != "FREEPDB1"
        ):
            raise RuntimeError("Use IT_SUPPORT_WORKSHOP in FREEPDB1.")

        query_config = build_query_config(question.strip(), query_vector, limit)
        print("Searching through IAT Retrieval SDK...")
        results = await IATRAGRetriever(db=database).fetch_result_single_retrieval(query_config)

        passages = []
        for result in results:
            metadata = decode_metadata(result.result_metadata["METADATA"])
            passages.append({
                "chunk_id": result.id,
                "text": result.content,
                "similarity_score": result.score,
                "document_id": metadata["document_id"],
                "document_title": metadata["title"],
                "original_page": metadata["page_number"],
                "source_reference": metadata["source_reference"],
                "product": metadata.get("product_name"),
                "applicable_os": metadata.get("applicable_os", []),
                "excluded_os": metadata.get("excluded_os", []),
                "specialist_review_required_for": metadata.get("specialist_review_required_for", []),
            })
        return {
            "status": "CANDIDATES" if passages else "INSUFFICIENT_EVIDENCE",
            "results": passages,
        }
    finally:
        if not await database.close(force=True):
            print("Warning: database pool cleanup reported a failure.")
