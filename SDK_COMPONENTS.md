# Repo 2: IAT Retrieval SDK components

## Scope and ownership

This repository uses **IAT Retrieval SDK 1.1.22** and its IAT Common SDK
database types. It retrieves candidate evidence from the local Oracle
vectors created by the completed Ingestion SDK foundation.

The shared environment also contains Agent and Service SDK packages for
later repos. This repository does not run an agent, chat LLM or HTTP service.
Read [README.md](README.md) for setup and [HINTS.md](HINTS.md) for progressive
exercise hints. This guide describes roles without providing a repaired
query-configuration function.

## 1. Data flow

```text
Employee question
        |
        v
LocalQwenEmbeddings.aembed_query()          Application adapter
        |
        v
1024-dimensional query vector
        |
        v
RetrievalQueryConfig                       Retrieval SDK model
  SQL + parameters + result mappings
        |
        v
IATRAGRetriever.fetch_result_single_retrieval()
        |
        v
OracleDB.dql()                            IAT Common SDK
        |
        v
Oracle vector-distance SQL against stored document vectors
        |
        v
SearchResult objects                      Retrieval SDK model
        |
        v
Application metadata decoding and candidate presentation
```

The runtime function is
[`search_support_knowledge()`](retrieval_pipeline/helpdesk_retrieval.py).
Its `build_query_config()` helper constructs the same SDK configuration
examined by the offline exercise check.

## 2. Database configuration: IATDBConfig

`IATDBConfig` belongs to `iat_common.models.database`, the IAT Common SDK
dependency used alongside retrieval. It describes the database username,
password, DSN and connection-pool limits.

This application reads credentials from `IAT_IT_USER`, `IAT_IT_PASSWORD` and
`IAT_IT_DSN`, then passes their values to the model. The workshop destination
is `IT_SUPPORT_WORKSHOP.IT_SUPPORT_EMBEDDINGS` in `FREEPDB1`.

Local credentials are explicitly supplied. This setup does not require an
OCI profile, wallet or OCI authentication configuration; the wrapper passes
`auth_config=None`. This is an application connection choice, not a special
Ollama option inside the Retrieval SDK.

**Why it matters:** the correct query against the wrong schema would not
retrieve the intended workshop corpus. Both the wrapper's connection guard
and the stored-data verification check the workshop destination.

## 3. Database access: OracleDB

`OracleDB` belongs to `iat_common.db`. The application constructs it from
`IATDBConfig` and supplies that database object to `IATRAGRetriever`.

The retriever calls its asynchronous `dql()` method to execute SQL with bind
parameters. In this SDK path, query results are represented as a DataFrame
whose returned columns are consumed by the retriever. The wrapper closes
the database pool in a `finally` block, including when retrieval fails.

**Why it matters:** connection/pool management and query execution are
separate responsibilities from choosing embeddings or interpreting support
documentation. Database credentials are setup, not exercise defects.

## 4. Query configuration: RetrievalQueryConfig

This Retrieval SDK model is the contract between the application-provided
SQL and the SDK's result construction.

| Field | Meaning in this repo |
| --- | --- |
| `query` | Oracle SQL that selects chunk ID, text, similarity and JSON metadata. |
| `params` | Bind values, including the serialized query vector and result limit. |
| `id_col` | Returned column that becomes `SearchResult.id`. |
| `content_col` | Returned column that becomes `SearchResult.content`. |
| `score_col` | Returned column that becomes `SearchResult.score`. |
| `additional_metadata_cols` | Extra returned columns to retain in `SearchResult.result_metadata`. |
| `retrieval_source` | Descriptive source label, not a schema selector or table name. |
| `retrieval_method` | Method label; this repo uses semantic retrieval. |

Mappings refer to **returned SQL column names**, including aliases. A table
column may have a different name from the alias in the result DataFrame.
An additional column selected by SQL also needs to be selected for inclusion
in `result_metadata` if the application expects to read it there.

**Why it matters:** the SDK executes the query and maps its output according
to this contract. Successful SQL alone does not prove SearchResult has the
content and metadata needed by the rest of the application.

## 5. Retriever: IATRAGRetriever

The application calls:

`IATRAGRetriever(db=database).fetch_result_single_retrieval(query_config)`

This SDK method executes `database.dql(query, params)` and constructs a
`SearchResult` for each returned row using the configured column mappings.

It does not generate the query embedding in this demonstrated path, write
the supplied SQL for the developer, or decide whether every retrieved
passage answers the question. It returns structured candidates.

Other SDK capabilities such as multiple-retrieval racing, caching and
hybrid fusion are outside this small single-semantic-query exercise.

## 6. Result model: SearchResult

| Field | Role |
| --- | --- |
| `id` | Identifier mapped from the returned chunk-ID column. |
| `content` | Text mapped from the configured content column. |
| `score` | Numeric value returned by the configured score expression. |
| `result_metadata` | Dictionary of the explicitly requested extra columns. |
| `retrieval_source` | Source label carried from the retrieval configuration. |
| `retrieval_method` | Retrieval method label. |

Here the database stores source information inside one JSON metadata column.
The application receives that selected value in `result_metadata`, decodes
it and exposes `document_id`, `original_page`, `source_reference` and other
fields in its returned candidate dictionaries.

The row ID, document ID and original PDF page are different identifiers.
The original page comes from stored `page_number` metadata, not from the
candidate's rank or the database row number.

## 7. Supplied local embedding adapter

[`LocalQwenEmbeddings`](local_embeddings.py) is application code. Its
`aembed_query()` method prefixes the question with a retrieval instruction
and calls the local `qwen3-embedding:0.6b` model through Ollama's `/api/embed`
endpoint. It returns a 1024-dimensional vector.

The same embedding model/dimensions were used for document ingestion.
Converting a question into a compatible query vector is different from
passing that vector correctly into `RetrievalQueryConfig.params`.

The `qwen3:4b` chat model is not called for retrieval. No conversational
answer is generated by this repository.

## 8. Supplied Oracle semantic SQL

The SQL converts the bound vector using `TO_VECTOR` and computes cosine
distance against each stored embedding. This application returns
`1 - VECTOR_DISTANCE(...)` as a similarity score and orders higher scores
first. The result limit bounds the candidate set.

The SQL and scoring policy are supplied application configuration, not SQL
automatically created by IAT. Ranking is left correct in the starter so
the three defects focus on SDK parameters and result contracts.

Similarity is not a confidence probability. A high-scoring candidate still
needs applicability and content assessment. Multiple returned candidates
are search evidence, not multiple proposed final answers.

## 9. Metadata decoding and applicability

`decode_metadata()` is application code supplied working. It accepts a
Python dictionary, serialized JSON or a readable LOB value. This accommodates
the representations database access may return.

The wrapper preserves document title, original page, URL, product,
applicable/excluded operating systems and specialist-review markers.
Returning this metadata does not by itself enforce applicability or support
restrictions. Their use in the conversational assistant belongs to later
application stages.

## 10. Completed ingestion foundation and verification

`ingestion_pipeline/` is the solved Repo 1 stage. It is included for
bootstrapping and independently verifying the expected corpus; it is not
another repair task. Original PDFs and cleaned JSON remain supplied because
the source hashes and expected chunks are checked.

[`test_retrieval.py`](retrieval_pipeline/test_retrieval.py) is workshop
application code, not an SDK component. Its modes are:

| Mode | Activity |
| --- | --- |
| `--check` | Builds the SDK query configuration using a synthetic vector and checks the three exercise contracts offline. No Oracle/Ollama calls. |
| A question, optionally `--limit` | Generates a real query embedding, searches Oracle through IAT and displays candidates. No document writes. |
| `--verify` | Verifies the existing 16-chunk corpus, then runs real searches for VPN, account fallback and desktop repair. Prints explanatory congratulations only after all checks pass. |

The full check validates result text/document/page associations, source
references, distinct IDs, finite descending scores and required supporting
passages. It does not require exact similarity scores or a particular first
result. Its bounded verification searches request up to five candidates.

Independent corpus checking uses the Python Oracle driver through the
completed ingestion verifier. Actual search execution uses `OracleDB` and
`IATRAGRetriever`; the verifier does not replace that SDK path.

## Ownership at a glance

| Supplied by IAT | Supplied by the application/workshop |
| --- | --- |
| IAT Common SDK: `IATDBConfig`, `OracleDB` | Environment credential handling and workshop schema guard |
| Retrieval SDK: `RetrievalQueryConfig` | SQL, bind values, result aliases and mapping configuration |
| Retrieval SDK: `IATRAGRetriever` | The reusable `search_support_knowledge()` wrapper |
| Retrieval SDK: `SearchResult` | Metadata decoding and candidate presentation |
| Completed native Ingestion SDK processing | Reviewed-JSON/local-embedding adapters and stored-data checks |

Ollama and Oracle Database are external local services. Their compatible
setup is supplied before the exercise; participants repair the three marked
SDK integration fields rather than editing installed SDK source files.
