# Repo 2 - IAT Retrieval SDK workshop

Repair three intentional defects in the SDK retrieval configuration. Reuse
the shared environment, local embedding model and workshop data from Repo 1.
There is no chat LLM, agent, service, frontend or evaluation exercise here.

## What you will learn

`Question -> local embedding -> RetrievalQueryConfig -> IATRAGRetriever`

`-> SearchResult -> text, score and source-aware candidate passages`

- `IATDBConfig` and `OracleDB` (IAT Common SDK) connect to local Oracle.
- `RetrievalQueryConfig` defines SQL, bind parameters and result mappings.
- `IATRAGRetriever.fetch_result_single_retrieval()` executes the configured
  search and constructs SDK `SearchResult` objects.
- `SearchResult.result_metadata` retains explicitly selected extra columns.
- The supplied application wrapper decodes metadata and exposes original
  document IDs, PDF pages, URLs and applicability information.

Read [SDK_COMPONENTS.md](SDK_COMPONENTS.md) for the component walkthrough and
[HINTS.md](HINTS.md) for progressive hints. Terminal feedback is part of the
verification code; no separate feedback Markdown file is used.

## Minimal contents

| Item | Purpose |
| --- | --- |
| `retrieval_pipeline/helpdesk_retrieval.py` | Reusable search implementation; the three marked defects are here. |
| `retrieval_pipeline/test_retrieval.py` | Offline checks, single-query CLI, verification suite and learning feedback. |
| `ingestion_pipeline/` | Completed Repo 1 foundation, supplied working. |
| `knowledge-base/` | Frozen approved documents and source register, used for independent verification or bootstrapping. |
| `local_embeddings.py` | Working qwen3-embedding:0.6b adapter. |
| `create_ingestion_table.py` | Workshop-only table setup if starting independently. |
| `requirements.txt` | Same full pinned shared environment baseline as Repo 1. |

## 1. Reuse your environment

Do not create a second venv or reinstall working dependencies. In a new
PowerShell terminal, activate the shared environment created during Repo 1:

```powershell
& (Join-Path $env:USERPROFILE "Desktop\IAT_Workshop\.venv\Scripts\Activate.ps1")
Set-Location -LiteralPath (Join-Path $env:USERPROFILE "Desktop\IT_SUPPORT_REPO2")
python -m pip check
```

Use your actual shared-environment path if different. An already activated
compatible environment can remain active when changing repositories. In VS
Code, select that same interpreter via Ctrl+Shift+P -> Python: Select
Interpreter -> Enter interpreter path. No venv is distributed in this repo.

Pinned SDK versions: Agent 2.6.3, Ingestion 3.0.6, Retrieval 1.1.22 and
Service 1.1.26, on Python 3.12. Only retrieval and its common dependencies
execute the live search; the other SDKs are installed for the shared workshop.

## 2. Reuse workshop credentials and data

Use `IT_SUPPORT_WORKSHOP` in `FREEPDB1`, with `IT_SUPPORT_EMBEDDINGS` holding
the 16 verified Repo 1 chunks. Keep Oracle and Ollama running. In each new
terminal, set the environment variables again:

```powershell
$env:IAT_IT_USER = "IT_SUPPORT_WORKSHOP"
$env:IAT_IT_DSN = "localhost:1521/FREEPDB1"
$securePassword = Read-Host "IT_SUPPORT_WORKSHOP password" -AsSecureString
$env:IAT_IT_PASSWORD = [System.Net.NetworkCredential]::new("", $securePassword).Password
Remove-Variable securePassword
```

Adjust only the DSN address if your local Oracle listener uses a different
host/port. `OLLAMA_URL` is optional and defaults to `http://localhost:11434`.
The embedding model is `qwen3-embedding:0.6b`, with 1024-dimensional vectors.
The chat model `qwen3:4b` is not called in this repository.

The main application's `IT_SUPPORT_APP` user is blocked. No new database
user or ingestion run is needed if Repo 1 data is already verified. The
completed ingestion files are included so this repo can be used independently.

## 3. Inspect and repair the three challenges

| ID | SDK integration to repair |
| --- | --- |
| R2-1 | Generated query-vector binding in `RetrievalQueryConfig.params` |
| R2-2 | Content-column mapping from SQL result into `SearchResult` |
| R2-3 | Additional metadata selection for `SearchResult.result_metadata` |

All three marked edits are in `build_query_config()` in
`retrieval_pipeline/helpdesk_retrieval.py`. The connection setup, SQL
aliases/ranking, local adapter, decoding, ingestion foundation and verification
are supplied correctly. Do not edit SDK files in site-packages.

Start with:

```powershell
python -m retrieval_pipeline.test_retrieval --check
```

The starter reports FAIL for R2-1, R2-2 and R2-3, exits nonzero and points
to HINTS.md. It makes no database connections or Ollama requests.
Fixes can be checked incrementally. Passing this offline check alone does
not produce congratulations or prove a live search works.

## 4. Run a live retrieval after the checks pass

```powershell
python -m retrieval_pipeline.test_retrieval "How do I connect to an existing VPN profile using Windows Settings?" --limit 3
```

Expected: a 1024-dimensional query vector, `CANDIDATES`, and up to three
results containing passage text, similarity, document ID, original page and
source URL. For the supplied corpus/model this query should include the
Windows Settings connection passage from `MS_WINDOWS_VPN_001`, page 4.
Do not expect identical scores across devices or require page 4 to rank first.

The candidates are debugging/inspection output for the retrieval component,
not multiple generated troubleshooting answers. Agent answer generation is
introduced in Repo 3.

## 5. Verify completion

```powershell
python -m retrieval_pipeline.test_retrieval --verify
```

This checks the completed ingestion foundation, independently reads and
verifies the 16 stored chunks/vectors, and runs three real SDK searches.
Each scenario requests up to five candidates so it does not depend on a
single exact rank. Its required supporting passage must still be present.

```text
[PASS] VPN connection: supporting text, SDK mappings and source references.
[PASS] Work-account administrator fallback: supporting text, SDK mappings and source references.
[PASS] Desktop application repair: supporting text, SDK mappings and source references.

Congratulations! You completed Repo 2: IAT Retrieval SDK.
```

The terminal then explains each defect, why the SDK component needed the
correction, and what verification proved. It validates approved text/page/URL
associations, distinct result IDs, finite descending scores and scenario
coverage. It does not grade exact numeric similarity scores or claim those
scores are confidence guarantees. No document rows are inserted or deleted.

## If starting without Repo 1 data

First create the dedicated workshop user in an administrative SQL client
connected to FREEPDB1, if it does not already exist. Replace the password
placeholder and never commit credentials:

```sql
CREATE USER IT_SUPPORT_WORKSHOP
    IDENTIFIED BY "<choose-your-workshop-password>"
    DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP
    QUOTA 100M ON USERS;
GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE TO IT_SUPPORT_WORKSHOP;
```

Activate the shared environment and set the workshop variables as above,
then use the supplied completed foundation:

```powershell
python .\create_ingestion_table.py
python -m ingestion_pipeline.run_ingestion --check
python -m ingestion_pipeline.run_ingestion
```

If no shared environment exists, create one outside the repos using Python
3.12 and install this same baseline once (internal-registry access required):

```powershell
$workshopRoot = Join-Path $env:USERPROFILE "Desktop\IAT_Workshop"
New-Item -ItemType Directory -Path $workshopRoot -Force
py -3.12 -m venv (Join-Path $workshopRoot ".venv")
& (Join-Path $workshopRoot ".venv\Scripts\Activate.ps1")
python -m pip install --index-url "https://artifactory.oci.oraclecorp.com/api/pypi/global-release-pypi/simple" -r requirements.txt
python -m pip check
```

Install the supplied embedding model in Ollama if missing. Do not rerun an
import into another schema to solve retrieval. Existing unexpected workshop
data is left unchanged; inspect setup with the organizer. Setup/bootstrap
requirements are not additional intentional defects.
