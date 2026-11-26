import math
import os

import httpx


class LocalQwenEmbeddings:
    def __init__(self):
        base_url = os.getenv(
            "OLLAMA_URL",
            "http://localhost:11434",
        ).rstrip("/")

        self.endpoint = base_url + "/api/embed"
        self.model = "qwen3-embedding:0.6b"
        self.dimension = 1024

    async def aembed_documents(self, texts):
        if not texts:
            return []

        if any(
            not isinstance(text, str) or not text.strip()
            for text in texts
        ):
            raise ValueError("Embedding input contains empty text.")

        vectors = []

        async with httpx.AsyncClient(timeout=300) as client:
            for start in range(0, len(texts), 8):
                batch = texts[start:start + 8]

                response = await client.post(
                    self.endpoint,
                    json={
                        "model": self.model,
                        "input": batch,
                        "truncate": False,
                    },
                )
                response.raise_for_status()

                batch_vectors = response.json()["embeddings"]

                if len(batch_vectors) != len(batch):
                    raise ValueError("Unexpected embedding count.")

                for vector in batch_vectors:
                    if len(vector) != self.dimension:
                        raise ValueError(
                            "Expected 1024-dimensional vectors."
                        )

                    if (
                        not all(math.isfinite(value) for value in vector)
                        or not any(vector)
                    ):
                        raise ValueError("Invalid embedding vector.")

                vectors.extend(batch_vectors)

        return vectors

    async def aembed_query(self, question):
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Query must not be empty.")

        query = (
            "Instruct: Retrieve relevant passages that answer "
            "the question.\nQuery: " + question
        )

        return (await self.aembed_documents([query]))[0]