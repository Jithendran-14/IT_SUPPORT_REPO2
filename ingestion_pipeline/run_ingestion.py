"""Completed Repo 1 ingestion foundation; bootstrap or verify workshop data.

--check validates the exercise and previews native SDK chunks without
calling Ollama, connecting to Oracle, or writing document records.
Normal mode also runs the real IAT pipeline and verifies stored data.
"""
import argparse
import asyncio
import json
import math
import os
import sys
import textwrap
from collections import Counter
from importlib.metadata import version

import oracledb
import yaml
from iat_rag_ingestion.components.chunkers.chunker_factory import ChunkerFactory
from iat_rag_ingestion.models.document_models import RawDocument

from ingestion_pipeline.helpdesk_pipeline import (
    CLEANED, KB, ROOT, HelpdeskIngestionPipeline, LocalOracleIndexer,
    parse_reviewed_document, read_sources,
)


CONFIG_PATH = ROOT / "ingestion_pipeline" / "ingestion_config.yaml"
WORKSHOP_USER = "IT_SUPPORT_WORKSHOP"
EXPECTED_COUNTS = {
    "MS_WINDOWS_VPN_001": 8,
    "MS_WINDOWS_INSTALL_001": 3,
    "MS_STORE_APPS_001": 2,
    "MS_WORK_ACCOUNT_001": 3,
}
SDK_VERSIONS = {
    "iat-agent-sdk": "2.6.3",
    "iat-rag-ingestion-sdk": "3.0.6",
    "iat-rag-retrieval-sdk": "1.1.22",
    "iat-service-sdk": "1.1.26",
}


def assemble_pipeline(pipeline):
    """This same assembly function is checked, then used by the real SDK."""
    return (
        pipeline
        .with_loader(source_name="reviewed_documents")
        .with_parser()
        .with_chunker()
        .with_indexer()

    )


class _AssemblyProbe:
    """Offline check of builder calls only; never substitutes for SDK ingestion."""
    def __init__(self):
        self.source_name = None
        self.components = []

    def with_loader(self, source_name=None):
        self.source_name = source_name
        self.components.append("loader")
        return self

    def with_parser(self):
        self.components.append("parser")
        return self

    def with_chunker(self):
        self.components.append("chunker")
        return self

    def with_indexer(self):
        self.components.append("indexer")
        return self


def preflight():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Use the shared Python 3.12 environment.")
    for package, expected in SDK_VERSIONS.items():
        if version(package) != expected:
            raise RuntimeError(f"Setup: {package} must be {expected}.")

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    sources = read_sources()
    if {s["document_id"] for s in sources} != set(EXPECTED_COUNTS):
        raise RuntimeError("The supplied source register was changed.")
    expected_files = {(KB / s["ingestion_file"]).resolve() for s in sources}
    if {p.resolve() for p in CLEANED.glob("*.json")} != expected_files:
        raise RuntimeError("The cleaned inputs do not match the source register.")

    parsed = []
    for source in sources:
        path = KB / source["ingestion_file"]
        raw = RawDocument(
            id=source["document_id"], content=path.read_bytes(),
            metadata={"path": str(path)}, format="json",
        )
        parsed.append(parse_reviewed_document(raw))
    print("[PASS] Supplied inputs: four approved documents; hashes and pages valid.")

    probe = assemble_pipeline(_AssemblyProbe())
    source = config["ingestion"]["sources"].get(probe.source_name)
    text = config["chunking"]["strategies"]["text"]
    checks = [
        ("R1-1", bool(source) and source.get("type") == "LocalStorage",
         "Loader source selection"),
        ("R1-2", text.get("type") == "recursive"
         and text.get("chunk_size") == 800
         and text.get("chunk_overlap") == 100,
         "Required recursive chunking policy"),
        ("R1-3", probe.components == ["loader", "parser", "chunker", "indexer"],
         "Loader, parser, chunker and indexer attached in order"),
    ]
    for challenge, passed, label in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {challenge}: {label}")
    if not all(passed for _, passed, _ in checks):
        print("\nExercise incomplete. See the matching sections in HINTS.md.")
        print("No embeddings generated, database connections or document writes.")
        return None

    if (ROOT / source["directory_path"]).resolve() != CLEANED:
        raise RuntimeError("Keep the supplied cleaned-input directory unchanged.")
    db = config["databases"][config["indexer"]["vector_store"]]
    if db["embeddings_table_name"] != "IT_SUPPORT_EMBEDDINGS":
        raise RuntimeError("Keep the supplied workshop table configuration.")

    chunker = ChunkerFactory.create_chunker("text", "recursive", text)
    expected = {}
    counts = Counter()
    for document in parsed:
        for structure in document.structures:
            for chunk in chunker.chunk_sync(structure, document.id):
                metadata = chunk.metadata
                key = (metadata["document_id"], metadata["page_number"], chunk.text)
                if key in expected:
                    raise RuntimeError("Duplicate expected chunk.")
                expected[key] = metadata
                counts[metadata["document_id"]] += 1
    if dict(counts) != EXPECTED_COUNTS:
        raise RuntimeError(f"Native SDK chunk preview mismatch: {dict(counts)}")
    print("[PASS] Native SDK parser/chunker preview: 16 chunks with source metadata.")
    return sources, expected


def connect_database():
    for name in ("IAT_IT_USER", "IAT_IT_PASSWORD", "IAT_IT_DSN"):
        if not os.environ.get(name):
            raise RuntimeError(f"Setup: missing {name}. See README.md.")
    if os.environ["IAT_IT_USER"].upper() != WORKSHOP_USER:
        raise RuntimeError("Use IT_SUPPORT_WORKSHOP; the main app's user is blocked.")
    connection = oracledb.connect(
        user=os.environ["IAT_IT_USER"], password=os.environ["IAT_IT_PASSWORD"],
        dsn=os.environ["IAT_IT_DSN"],
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT USER, SYS_CONTEXT('USERENV', 'CON_NAME') FROM dual")
            if cursor.fetchone() != (WORKSHOP_USER, "FREEPDB1"):
                raise RuntimeError("Use IT_SUPPORT_WORKSHOP in FREEPDB1.")
        return connection
    except Exception:
        connection.close()
        raise


def destination_count():
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM IT_SUPPORT_EMBEDDINGS")
            return cursor.fetchone()[0]


def decode_json(value):
    if hasattr(value, "read"):
        value = value.read()
    if isinstance(value, (str, bytes, bytearray)):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON metadata object.")
    return value


def verify_database(expected):
    counts = Counter()
    seen = set()
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT text, metadata, VECTOR_DIMENSION_COUNT(embedding), embedding
                FROM IT_SUPPORT_EMBEDDINGS
            """)
            for text, metadata, dimensions, vector in cursor:
                if hasattr(text, "read"):
                    text = text.read()
                metadata = decode_json(metadata)
                key = (metadata["document_id"], metadata["page_number"], text)
                if key not in expected or key in seen:
                    raise RuntimeError("Unexpected, modified or duplicate stored chunk.")
                if dimensions != 1024 or len(vector) != 1024:
                    raise RuntimeError("Stored vector dimension mismatch.")
                if not all(math.isfinite(float(v)) for v in vector) or not any(vector):
                    raise RuntimeError("Stored vector contains invalid values.")
                for field in (
                    "document_id", "title", "page_number", "source_reference",
                    "file_hash", "ingestion_file_hash", "approval_status",
                    "cleaned_review_status",
                ):
                    if metadata.get(field) != expected[key].get(field):
                        raise RuntimeError(f"Stored metadata mismatch: {field}.")
                seen.add(key)
                counts[metadata["document_id"]] += 1
    if seen != set(expected) or dict(counts) != EXPECTED_COUNTS:
        raise RuntimeError(f"Stored corpus incomplete: {dict(counts)}")
    print("\nDatabase verification passed.")
    for document_id, count in EXPECTED_COUNTS.items():
        print(f"{document_id}: {counts[document_id]} chunks")
    print("Total stored chunks:", len(seen))
    print("Vector dimensions: 1024")


def print_feedback():
    print("\n" + "=" * 70)
    print("Congratulations! You completed Repo 1: IAT Ingestion SDK.")
    explanations = [
        ("1. Source configuration and loader", """
         The starter loader referenced a name that did not match a declared
         source. IAT uses that name to select the source configuration,
         including its storage type, directory and file extensions. Your
         corrected assembly now selects the approved cleaned-document source.
         Verification confirmed the four supplied documents, their original
         PDF and cleaned-file hashes, and their original-page mappings.
         """),
        ("2. Chunking configuration", """
         The starter reversed chunk size and overlap. Overlap is the text
         carried between neighbouring chunks; it cannot be larger than the
         chunk it belongs to. The required 800-character size and 100-character
         overlap let IAT's recursive chunker create the intended text units.
         The native SDK preview and stored data agree on all 16 chunk texts,
         their document IDs and original pages, rather than only a row count.
         """),
        ("3. Indexer and pipeline assembly", """
         The starter assembled loading, parsing and chunking without attaching
         the indexer. Those earlier stages prepare documents but do not store
         embeddings. Attaching the supplied local Oracle indexer completes the
         SDK pipeline. Its application adapter calls qwen3-embedding:0.6b;
         IAT's Oracle indexing implementation stores the resulting vectors.
         Verification checked 16 unique stored chunks, finite nonzero vectors
         of 1024 dimensions, and their preserved source metadata.
         """),
    ]
    for heading, explanation in explanations:
        print("\n" + heading)
        print(textwrap.fill(textwrap.dedent(explanation).strip(), width=76))
    print("\nSDK flow: Loader -> Parser -> Chunker -> Indexer -> Oracle")
    print("The local embedding/indexer adapters are application code supplied")
    print("for this workshop; the IAT SDK itself was not edited.")
    print("Keep this environment and workshop schema for Repos 2-4.")
    print("=" * 70)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Offline exercise checks only")
    parser.add_argument("--verify", action="store_true", help="Read-only stored-data verification")
    args = parser.parse_args()
    os.chdir(ROOT)
    result = preflight()
    if result is None:
        return 1
    _, expected = result
    if args.check:
        print("\nPreflight passed. Database ingestion has NOT been verified yet.")
        print("No embeddings generated or database connections/writes performed.")
        return 0

    rows = destination_count()
    if args.verify or rows:
        print("\nVerifying existing workshop records; no inserts or deletions.")
    else:
        pipeline = assemble_pipeline(HelpdeskIngestionPipeline(config_path=CONFIG_PATH))
        toolkit = await pipeline.build()
        if not isinstance(toolkit.indexer, LocalOracleIndexer):
            raise RuntimeError("The real pipeline does not contain the supplied local indexer.")
        print("\nStarting the real IAT ingestion pipeline...")
        await toolkit.process_documents_in_batches()
        stats = toolkit.indexer.stats
        print("Indexer statistics:", stats)
        if stats["failed_chunks"] or stats["indexed_chunks"] != 16:
            raise RuntimeError("Indexing incomplete. No completion feedback will be shown.")
    verify_database(expected)
    print_feedback()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nStopped. Run again to inspect the workshop records.")
        sys.exit(130)
    except Exception as error:
        print(f"\n[ERROR] {type(error).__name__}: {error}")
        print("No congratulations: verification has not passed.")
        sys.exit(1)
