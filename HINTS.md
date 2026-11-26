# Repo 2 hints - IAT Retrieval SDK

The completed ingestion foundation is supplied. Repair only the three marked
fields in `retrieval_pipeline/helpdesk_retrieval.py`. Do not change the
source documents, SDK versions, vector dimensions, query ranking or checks.

Run this after each repair:

```powershell
python -m retrieval_pipeline.test_retrieval --check
```

This builds the same SDK query configuration used by live retrieval, with
a synthetic vector for checking only. It does not contact Oracle or Ollama.

## R2-1 - Query embedding parameter

**Concept hint:** Oracle's vector-distance expression compares vectors, not
the original question string. The application has already generated the
query embedding before constructing the retrieval configuration.

<details>
<summary>Location hint</summary>

Inspect the `query_vector` entry in `RetrievalQueryConfig.params`. Compare
what is bound there with what `TO_VECTOR(:query_vector, ...)` expects and
the values available to `build_query_config()`.

</details>

## R2-2 - SDK content-column mapping

**Concept hint:** IAT constructs SearchResult objects by looking up the
configured names in the returned query columns. A physical table-column
name and its returned SQL alias do not have to be the same.

<details>
<summary>Location hint</summary>

Compare `content_col` with the SELECT alias for the text column. Keep the
provided SQL aliases and repair the SDK mapping.

</details>

## R2-3 - Additional metadata in SearchResult

**Concept hint:** Selecting a column in SQL does not automatically preserve
it in SearchResult.result_metadata. The SDK needs an explicit list of the
additional result columns that the application will consume.

<details>
<summary>Location hint</summary>

Inspect `additional_metadata_cols` and the later access to
`result.result_metadata`. The supplied document/page/source fields are
inside the database's JSON metadata column.

</details>

## After the checks pass

Try a live question, then run `--verify`. The verification suite checks the
stored corpus and real Retrieval SDK searches for VPN, account-access and
desktop-repair passages. Congratulations and explanatory feedback appear
only after all verification checks pass.

There is no single mandatory similarity score or exact candidate ordering
between closely related passages. Candidates are evidence to assess, not
generated answers or confidence guarantees.
