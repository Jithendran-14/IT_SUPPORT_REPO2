import hashlib
import json
from pathlib import Path

from iat_rag_ingestion.components.indexers.base import BaseIndexer
from iat_rag_ingestion.components.indexers.oracle_indexer import (
    OracleVectorIndexer,
)
from iat_rag_ingestion.components.parsers.parser_processor import (
    ParserProcessor,
)
from iat_rag_ingestion.core.core import IATIngestionPipeline
from iat_rag_ingestion.models.document_models import (
    DocumentStructure,
    ParsedDocument,
)

from local_embeddings import LocalQwenEmbeddings


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "knowledge-base"
CLEANED = (KB / "cleaned").resolve()


def read_sources():
    sources = json.loads(
        (KB / "sources.json").read_text(
            encoding="utf-8-sig"
        )
    )

    document_ids = [
        source["document_id"]
        for source in sources
    ]

    if not sources or len(document_ids) != len(set(document_ids)):
        raise ValueError("Empty source register or duplicate IDs.")

    return sources


def parse_reviewed_document(raw_document):
    path = Path(raw_document.metadata["path"]).resolve()

    if path.parent != CLEANED:
        raise ValueError("Unexpected cleaned-document location.")

    matches = [
        source
        for source in read_sources()
        if (KB / source["ingestion_file"]).resolve() == path
    ]

    if len(matches) != 1:
        raise ValueError("Document must have one source-register entry.")

    source = matches[0]

    if not (
        source["approval_status"] == "APPROVED"
        and source["cleaned_review_status"] == "APPROVED"
        and source["ingestion_hold"] is False
    ):
        raise ValueError("Document is not approved for ingestion.")

    original = (KB / source["filename"]).resolve()

    if original.parent != KB.resolve():
        raise ValueError("Unexpected original-document location.")

    if (
        hashlib.sha256(original.read_bytes()).hexdigest()
        != source["file_hash"]
    ):
        raise ValueError("Original PDF hash mismatch.")

    content = raw_document.content

    if isinstance(content, str):
        content = content.encode("utf-8")

    if (
        hashlib.sha256(content).hexdigest()
        != source["ingestion_file_hash"]
    ):
        raise ValueError("Cleaned JSON hash mismatch.")

    payload = json.loads(content.decode("utf-8-sig"))

    if (
        payload["document_id"] != source["document_id"]
        or payload["original_filename"] != source["filename"]
        or payload["source_reference"] != source["source_reference"]
    ):
        raise ValueError("Document identity does not match sources.json.")

    pages = payload["pages"]
    page_numbers = [page["original_page"] for page in pages]

    if (
        not pages
        or page_numbers != source["retained_pdf_pages"]
        or len(page_numbers) != len(set(page_numbers))
    ):
        raise ValueError("Invalid original-page mapping.")

    metadata = {
        **source,
        "path": str(path),
    }

    structures = []

    for page in pages:
        text = page["text"]

        if not isinstance(text, str) or not text.strip():
            raise ValueError("Document contains empty page text.")

        structures.append(
            DocumentStructure(
                structure_type="text",
                content=text,
                metadata={
                    **metadata,
                    "page_number": page["original_page"],
                },
            )
        )

    return ParsedDocument(
        id=raw_document.id,
        structures=structures,
        metadata=metadata,
    )


class ReviewedJSONParser(ParserProcessor):
    def _parse_document(
        self,
        raw_doc,
        config,
        logging_config=None,
    ):
        document_id = str(raw_doc.id)
        path = str(raw_doc.metadata["path"])

        try:
            parsed = parse_reviewed_document(raw_doc)
            return document_id, path, parsed, None
        except Exception as error:
            return document_id, path, None, error


class LocalOracleIndexer(OracleVectorIndexer):
    def __init__(self, config, db_config):
        # Initialize the base component without constructing
        # OracleVectorIndexer's default OCI embedding client.
        BaseIndexer.__init__(self)

        self.config = config
        self.db_config = db_config
        self.db_table_name = db_config.embeddings_table_name

        self.embeddings = LocalQwenEmbeddings()
        self.lexical_config = None

        self.stats = {
            "total_chunks": 0,
            "indexed_chunks": 0,
            "failed_chunks": 0,
        }

    async def _embed_documents_with_auth_retry(self, texts):
        return await self.embeddings.aembed_documents(texts)

    def _reload_embeddings_client(self):
        self.embeddings = LocalQwenEmbeddings()

    async def cleanup(self):
        # The local adapter closes its HTTP client after each call.
        pass


class HelpdeskIngestionPipeline(IATIngestionPipeline):
    def with_parser(self):
        self._parser = ReviewedJSONParser(
            self.config_manager.parser_config,
            self.config_manager.validator_config,
            self._source_config,
            self.config_manager.logging_config,
        )
        return self

    def with_indexer(self):
        config = self.config_manager.indexing_config
        database = self.config_manager.config.databases[
            config.vector_store
        ]

        self._indexer = LocalOracleIndexer(
            config,
            database,
        )
        return self