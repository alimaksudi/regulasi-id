// 1536-dimension model, matches document_nodes.embedding vector(1536).
const EMBEDDING_MODEL = "text-embedding-3-small"

type OpenAIEmbeddingResponse = {
  data: { embedding: number[] }[]
}

// Generate a query embedding via the OpenAI REST API. No SDK (Workers runtime).
export async function generateEmbedding(text: string, apiKey: string): Promise<number[]> {
  const res = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ model: EMBEDDING_MODEL, input: text }),
  })

  if (!res.ok) {
    throw new Error(`OpenAI embeddings failed: ${res.status} ${await res.text()}`)
  }

  const json = (await res.json()) as OpenAIEmbeddingResponse
  return json.data[0].embedding
}
