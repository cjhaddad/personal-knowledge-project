import os
import openai
from pinecone import Pinecone
from typing import List, Dict, Optional
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "knowledge-base")

        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found. Vector operations will be disabled.")
            return

        if not self.pinecone_api_key:
            logger.warning("PINECONE_API_KEY not found. Vector operations will be disabled.")
            return

        openai.api_key = self.openai_api_key

        try:
            self.pc = Pinecone(api_key=self.pinecone_api_key)

            # Check if index exists
            existing_indexes = [index.name for index in self.pc.list_indexes()]
            if self.index_name not in existing_indexes:
                logger.error(f"Index '{self.index_name}' not found. Available: {existing_indexes}")
                self.initialized = False
                return

            self.index = self.pc.Index(self.index_name)
            self.initialized = True
            logger.info(f"Vector store initialized with index: {self.index_name}")

        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {e}")
            self.initialized = False

    def is_available(self) -> bool:
        return hasattr(self, 'initialized') and self.initialized

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        if not self.is_available():
            return None

        try:
            response = openai.Embedding.create(
                model="text-embedding-3-small",
                input=text.replace("\n", " ")
            )
            return response['data'][0]['embedding']
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    async def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Get embeddings for multiple texts in a single API call"""
        if not self.is_available():
            return [None] * len(texts)

        if not texts:
            return []

        try:
            # Clean texts and prepare for batch processing
            cleaned_texts = [text.replace("\n", " ") for text in texts]

            # OpenAI allows up to 2048 inputs per request
            batch_size = 100  # Conservative batch size for stability
            all_embeddings = []

            for i in range(0, len(cleaned_texts), batch_size):
                batch = cleaned_texts[i:i + batch_size]

                response = openai.Embedding.create(
                    model="text-embedding-3-small",
                    input=batch
                )

                # Extract embeddings in the correct order
                batch_embeddings = [item['embedding'] for item in response['data']]
                all_embeddings.extend(batch_embeddings)

            return all_embeddings

        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            return [None] * len(texts)

    async def store_chunk_embedding(self, chunk_id: int, text: str, document_id: int, user_id: int) -> bool:
        if not self.is_available():
            return False

        embedding = await self.get_embedding(text)
        if not embedding:
            return False

        try:
            self.index.upsert([{
                "id": f"chunk_{chunk_id}",
                "values": embedding,
                "metadata": {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "user_id": user_id,
                    "text": text[:1000]  # Store truncated text for preview
                }
            }])
            return True
        except Exception as e:
            logger.error(f"Error storing embedding for chunk {chunk_id}: {e}")
            return False

    async def store_chunk_embeddings_batch(self, chunk_data: List[Dict]) -> List[bool]:
        """Store multiple chunk embeddings in batches"""
        if not self.is_available():
            return [False] * len(chunk_data)

        if not chunk_data:
            return []

        try:
            # Extract texts for batch embedding generation
            texts = [item["text"] for item in chunk_data]
            embeddings = await self.get_embeddings_batch(texts)

            # Prepare vectors for Pinecone upsert
            vectors = []
            results = []

            for i, (chunk_info, embedding) in enumerate(zip(chunk_data, embeddings)):
                if embedding is None:
                    results.append(False)
                    continue

                vectors.append({
                    "id": f"chunk_{chunk_info['chunk_id']}",
                    "values": embedding,
                    "metadata": {
                        "chunk_id": chunk_info["chunk_id"],
                        "document_id": chunk_info["document_id"],
                        "user_id": chunk_info["user_id"],
                        "text": chunk_info["text"][:1000]  # Store truncated text for preview
                    }
                })
                results.append(True)

            # Batch upsert to Pinecone
            if vectors:
                self.index.upsert(vectors)

            return results

        except Exception as e:
            logger.error(f"Error storing batch embeddings: {e}")
            return [False] * len(chunk_data)

    async def search_similar_chunks(
        self,
        query: str,
        user_id: int,
        top_k: int = 5,
        document_ids: Optional[List[int]] = None
    ) -> List[Dict]:
        if not self.is_available():
            return []

        query_embedding = await self.get_embedding(query)
        if not query_embedding:
            return []

        try:
            filter_dict = {"user_id": user_id}
            if document_ids:
                filter_dict["document_id"] = {"$in": document_ids}

            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=filter_dict
            )

            chunks = []
            for match in results.matches:
                chunks.append({
                    "chunk_id": match.metadata["chunk_id"],
                    "document_id": match.metadata["document_id"],
                    "text": match.metadata["text"],
                    "score": match.score
                })

            return chunks
        except Exception as e:
            logger.error(f"Error searching similar chunks: {e}")
            return []

    async def delete_document_embeddings(self, document_id: int, user_id: int) -> bool:
        if not self.is_available():
            return True  # Consider it successful if vector store is not available

        try:
            # Query all chunks for the document
            filter_dict = {"document_id": document_id, "user_id": user_id}
            results = self.index.query(
                vector=[0] * 1536,  # Dummy vector for filtering
                top_k=10000,  # Large number to get all chunks
                include_metadata=True,
                filter=filter_dict
            )

            # Delete all found embeddings
            if results.matches:
                chunk_ids = [f"chunk_{match.metadata['chunk_id']}" for match in results.matches]
                self.index.delete(ids=chunk_ids)

            return True
        except Exception as e:
            logger.error(f"Error deleting embeddings for document {document_id}: {e}")
            return False

vector_store = VectorStore()