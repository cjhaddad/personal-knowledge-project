import os
import openai
from typing import List, Dict, Optional
from dotenv import load_dotenv
import logging
from sqlalchemy.orm import Session
from models import Document
from vector_store import vector_store

load_dotenv()

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found. RAG operations will be disabled.")
            self.available = False
            return

        openai.api_key = self.openai_api_key
        self.available = True
        logger.info("RAG service initialized")

    def is_available(self) -> bool:
        return hasattr(self, 'available') and self.available

    async def generate_answer(
        self,
        question: str,
        user_id: int,
        db: Session,
        document_ids: Optional[List[int]] = None,
        max_chunks: int = 5
    ) -> Dict:
        """Generate an answer using RAG approach"""
        if not self.is_available():
            return {
                "answer": "RAG service is not available. Please check OpenAI API configuration.",
                "sources": [],
                "question": question
            }

        # Step 1: Get relevant chunks using vector search
        chunks = await vector_store.search_similar_chunks(
            query=question,
            user_id=user_id,
            top_k=max_chunks,
            document_ids=document_ids
        )

        if not chunks:
            return {
                "answer": "I couldn't find any relevant information in your documents to answer this question.",
                "sources": [],
                "question": question
            }

        # Step 2: Get document titles for sources
        document_map = {}
        if chunks:
            doc_ids = list(set(chunk["document_id"] for chunk in chunks))
            documents = db.query(Document).filter(Document.id.in_(doc_ids)).all()
            document_map = {doc.id: doc.title for doc in documents}

        # Step 3: Prepare context for LLM
        context_text = "\n\n".join([
            f"Source {i+1} (Document: {document_map.get(chunk['document_id'], 'Unknown')}):\n{chunk['text']}"
            for i, chunk in enumerate(chunks)
        ])

        # Step 4: Create prompt for answer generation
        prompt = self._create_rag_prompt(question, context_text)

        try:
            # Step 5: Generate answer using OpenAI
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions based on provided context from documents. Always base your answers on the given context and be concise but comprehensive."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )

            answer = response.choices[0].message.content.strip()

            # Step 6: Prepare sources
            sources = []
            for chunk in chunks:
                sources.append({
                    "document_id": chunk["document_id"],
                    "title": document_map.get(chunk["document_id"], "Unknown"),
                    "chunk_id": chunk["chunk_id"]
                })

            return {
                "answer": answer,
                "sources": sources,
                "question": question
            }

        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return {
                "answer": f"I encountered an error while generating the answer: {str(e)}",
                "sources": [],
                "question": question
            }

    def _create_rag_prompt(self, question: str, context: str) -> str:
        """Create a prompt for RAG answer generation"""
        return f"""Based on the following context from the user's documents, please answer the question. If the context doesn't contain enough information to fully answer the question, say so and provide what information is available.

                Context:
                {context}

                Question: {question}

                Answer:"""

rag_service = RAGService()