"""Repo 2 checks, live query demonstration and verified learning feedback."""
import argparse
import asyncio
import json
import math
import sys
import textwrap
from importlib.metadata import version

from retrieval_pipeline.helpdesk_retrieval import build_query_config, search_support_knowledge


SDK_VERSIONS = {
    "iat-agent-sdk": "2.6.3",
    "iat-rag-ingestion-sdk": "3.0.6",
    "iat-rag-retrieval-sdk": "1.1.22",
    "iat-service-sdk": "1.1.26",
}
SCENARIOS = (
    (
        "VPN connection",
        "How do I connect to an existing VPN profile using Windows Settings?",
        "MS_WINDOWS_VPN_001", 4,
        ("connect to a vpn from the windows settings page", "select connect"),
    ),
    (
        "Work-account administrator fallback",
        "What should I do if self-service password reset is unavailable for my work account?",
        "MS_WORK_ACCOUNT_001", 2,
        ("administrator", "help desk"),
    ),
    (
        "Desktop application repair",
        "How do I repair an installed desktop application using Windows Settings?",
        "MS_WINDOWS_INSTALL_001", 2,
        ("advanced options", "repair"),
    ),
)


def preflight():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Use the shared Python 3.12 environment.")
    for package, expected in SDK_VERSIONS.items():
        if version(package) != expected:
            raise RuntimeError(f"Setup: {package} must be {expected}.")
    print("[PASS] Shared Python/SDK baseline.")

    vector = [0.25] * 1024
    config = build_query_config("Offline SDK configuration check", vector, 3)
    try:
        bound = json.loads(config.params["query_vector"])
        vector_ok = bound == vector
    except (TypeError, ValueError, KeyError):
        vector_ok = False
    checks = (
        ("R2-1", vector_ok, "Query embedding parameter binding"),
        ("R2-2", config.content_col == "CONTENT", "SDK content-column mapping"),
        ("R2-3", "METADATA" in (config.additional_metadata_cols or []), "SDK source-metadata selection"),
    )
    for challenge, passed, label in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {challenge}: {label}")
    if not all(passed for _, passed, _ in checks):
        print("\nExercise incomplete. See the matching sections in HINTS.md.")
        print("No embeddings generated, database connections or document writes.")
        return False
    print("[PASS] RetrievalQueryConfig is ready for live retrieval.")
    return True


def display_results(question, response):
    print("\nQuestion:", question)
    print("Status:", response["status"])
    print("Results returned:", len(response["results"]))
    for number, result in enumerate(response["results"], 1):
        print(f"\n--- Result {number} ---")
        print("Document:", result["document_title"])
        print("Document ID:", result["document_id"])
        print("Original PDF page:", result["original_page"])
        print("Product:", result["product"])
        print("Similarity:", round(result["similarity_score"], 4))
        print("Source:", result["source_reference"])
        print("Content:\n" + result["text"])


def verify_results(response, expected, limit):
    results = response.get("results", [])
    if response.get("status") != "CANDIDATES" or not 1 <= len(results) <= limit:
        raise RuntimeError("Expected nonempty retrieval candidates within the requested limit.")
    seen = set()
    previous_score = float("inf")
    for result in results:
        chunk_id = result["chunk_id"]
        if not isinstance(chunk_id, str) or not chunk_id.strip() or chunk_id in seen:
            raise RuntimeError("Missing or duplicate SDK result identifier.")
        seen.add(chunk_id)
        key = (result["document_id"], result["original_page"], result["text"])
        if key not in expected:
            raise RuntimeError("Returned text/document/page does not match the approved corpus.")
        metadata = expected[key]
        if (
            result["source_reference"] != metadata["source_reference"]
            or result["document_title"] != metadata["title"]
        ):
            raise RuntimeError("Returned source metadata does not match the corpus.")
        score = float(result["similarity_score"])
        if not math.isfinite(score) or score > previous_score + 1e-12:
            raise RuntimeError("Similarity scores must be finite and ordered highest first.")
        previous_score = score


def verify_scenario(response, document_id, page, required_phrases):
    passages = [
        " ".join(result["text"].lower().split())
        for result in response["results"]
        if result["document_id"] == document_id and result["original_page"] == page
    ]
    if not any(all(phrase in text for phrase in required_phrases) for text in passages):
        raise RuntimeError(
            f"Expected supporting passage from {document_id}, page {page} was not returned. "
            "This check does not require a specific similarity score or first-place ranking."
        )


def print_feedback():
    print("\n" + "=" * 70)
    print("Congratulations! You completed Repo 2: IAT Retrieval SDK.")
    explanations = (
        ("1. RetrievalQueryConfig parameters", """
         The starter passed the question text into a SQL parameter that expects
         a serialized vector. The application must first embed the question
         with the same local model used for the documents. Correct binding
         supplies that 1024-dimensional vector through RetrievalQueryConfig.
         Live verification generated query embeddings and used the configured
         vector parameter in native IAT Retrieval SDK searches against Oracle.
         """),
        ("2. SearchResult content mapping", """
         The starter's content mapping named a column that the SELECT did not
         return under that name. IAT reads the configured result-column names
         when constructing SearchResult objects; the mapping must match the
         returned alias, not just the physical table column name. Verification
         checked that the returned content is nonempty approved chunk text
         with consistent document identity and original-page information.
         """),
        ("3. Additional result metadata", """
         Selecting METADATA in SQL does not automatically retain it in every
         SearchResult. The additional_metadata_cols setting tells IAT which
         extra result columns to preserve. The repaired configuration lets the
         application decode that metadata into document titles, original pages
         and source URLs. Verification checked these references against the
         frozen corpus for VPN, work-account and desktop-repair searches.
         """),
    )
    for heading, explanation in explanations:
        print("\n" + heading)
        print(textwrap.fill(textwrap.dedent(explanation).strip(), width=76))
    print("\nSDK flow: query embedding -> RetrievalQueryConfig -> IATRAGRetriever")
    print("          -> SearchResult -> source-aware candidate passages")
    print("These are retrieved candidates, not generated troubleshooting answers.")
    print("Similarity scores are not confidence guarantees.")
    print("Keep the same shared environment and workshop schema for Repos 3-4.")
    print("=" * 70)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", help="A question for one live retrieval")
    parser.add_argument("--limit", type=int, default=3, choices=range(1, 6))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Offline configuration checks only")
    modes.add_argument("--verify", action="store_true", help="Verify stored data and three live retrieval scenarios")
    args = parser.parse_args()
    if args.question is not None and not args.question.strip():
        parser.error("Question must not be empty.")
    if args.question is not None and (args.check or args.verify):
        parser.error("Use either a question, --check, or --verify.")
    if not args.question and not (args.check or args.verify):
        parser.error("Supply a question, --check, or --verify.")
    if not preflight():
        return 1
    if args.check:
        print("\nOffline checks passed. Live retrieval has NOT been verified yet.")
        print("No embeddings generated or database connections/writes performed.")
        return 0

    if args.verify:
        # This supplied, solved foundation validates actual existing data.
        from ingestion_pipeline.run_ingestion import preflight as ingestion_preflight
        from ingestion_pipeline.run_ingestion import verify_database
        print("\nChecking the completed ingestion foundation and stored corpus...")
        foundation = ingestion_preflight()
        if foundation is None:
            raise RuntimeError("Completed ingestion foundation was changed. See README.md.")
        _, expected = foundation
        verify_database(expected)
        for label, question, doc_id, page, phrases in SCENARIOS:
            # A wider, bounded candidate set avoids scoring an exact rank.
            response = await search_support_knowledge(question, limit=5)
            verify_results(response, expected, limit=5)
            verify_scenario(response, doc_id, page, phrases)
            print(f"[PASS] {label}: supporting text, SDK mappings and source references.")
        print_feedback()
        return 0

    response = await search_support_knowledge(args.question, limit=args.limit)
    display_results(args.question, response)
    print("\nRun --verify to check all scenarios and earn completion feedback.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nStopped. Retrieval does not insert or delete document rows.")
        sys.exit(130)
    except Exception as error:
        print(f"\n[ERROR] {type(error).__name__}: {error}")
        print("No Repo 2 congratulations: retrieval verification has not passed.")
        sys.exit(1)
