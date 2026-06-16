"""
RAG (Retrieval-Augmented Generation) service for orchestrating the complete pipeline.

This module provides:
- Complete RAG pipeline orchestration from query to response
- Query analysis with intent and entity extraction (simple keyword extraction for v1)
- Hybrid search execution via SearchService
- Context assembly from Top-K retrieved documents
- Prompt construction with context injection
- Streaming LLM response generation
- Source reference extraction and tracking
"""
import re
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.services.search_service import search_service
from app.services.genai.llm_service import llm_service, LLMService
from app.services.genai.embedding_service import embedding_service


class RAGError(Exception):
    """Base exception for RAG service errors"""
    pass


class RAGService:
    """
    Service for orchestrating the complete RAG pipeline.

    Pipeline stages:
    1. Query Analysis - Extract intent and entities
    2. Hybrid Search - Retrieve relevant documents
    3. Context Assembly - Combine and format retrieved content
    4. Prompt Construction - Build LLM prompt with context
    5. Response Generation - Stream LLM response
    6. Source Extraction - Track and return source references
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        top_k: int = None,
        semantic_top_k: int = 20,
        keyword_top_k: int = 20
    ):
        """
        Initialize RAG service.

        Args:
            llm_service: LLM service instance (defaults to global instance)
            top_k: Number of documents to retrieve (defaults to MAX_SEARCH_RESULTS)
            semantic_top_k: Number of semantic search results (default: 20)
            keyword_top_k: Number of keyword search results (default: 20)
        """
        # Use provided LLM service or global instance
        from app.services.genai.llm_service import llm_service as global_llm
        self.llm_service = llm_service or global_llm

        # Search parameters
        self.top_k = top_k if top_k is not None else settings.MAX_SEARCH_RESULTS
        self.semantic_top_k = semantic_top_k
        self.keyword_top_k = keyword_top_k

        logger.info(
            f"RAGService initialized with top_k={self.top_k}, "
            f"semantic_top_k={self.semantic_top_k}, keyword_top_k={self.keyword_top_k}"
        )

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze query to extract intent and entities (simple v1 implementation).

        For v1, uses simple keyword extraction:
        - Extract question type (what, how, why, when, where, who)
        - Extract key terms (nouns and important words)

        Args:
            query: User query text

        Returns:
            Dictionary with intent, entities, and query_type
        """
        query_lower = query.lower().strip()

        # Detect question type
        question_words = {
            "what": "definition",
            "how": "procedure",
            "why": "explanation",
            "when": "temporal",
            "where": "location",
            "who": "person"
        }

        query_type = "general"
        for word, qtype in question_words.items():
            if query_lower.startswith(word):
                query_type = qtype
                break

        # Simple keyword extraction - remove common words
        stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "what", "how", "why", "when", "where",
            "who", "which", "this", "that", "these", "those", "i", "you", "me"
        }

        # Extract words (alphanumeric tokens)
        words = re.findall(r'\b\w+\b', query_lower)
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        analysis = {
            "query_type": query_type,
            "keywords": keywords[:5],  # Top 5 keywords
            "intent": query_type,
            "original_query": query
        }

        logger.info(f"Query analysis: type={query_type}, keywords={keywords[:5]}")
        return analysis

    def assemble_context(self, documents: List[Dict[str, Any]]) -> str:
        """
        Assemble context from retrieved documents.

        Combines Top-K documents with metadata into formatted context string.

        Args:
            documents: List of retrieved documents from hybrid search

        Returns:
            Formatted context string for LLM prompt
        """
        if not documents:
            return "No relevant context found."

        context_parts = []

        for idx, doc in enumerate(documents, start=1):
            # Format each document with metadata
            doc_text = f"[Document {idx}]"

            # Add title if available
            if doc.get("title"):
                doc_text += f"\nTitle: {doc['title']}"

            # Add source type and URL if available
            if doc.get("source_type"):
                doc_text += f"\nSource: {doc['source_type']}"
            if doc.get("url"):
                doc_text += f"\nURL: {doc['url']}"

            # Add content
            doc_text += f"\nContent: {doc['content']}"

            # Add score for reference
            if doc.get("rrf_score"):
                doc_text += f"\n(Relevance Score: {doc['rrf_score']:.4f})"

            context_parts.append(doc_text)

        # Join all documents with separators
        context = "\n\n" + "\n---\n".join(context_parts)

        logger.info(f"Assembled context from {len(documents)} documents, {len(context)} chars")
        return context

    def extract_source_references(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract source references from retrieved documents.

        Args:
            documents: List of retrieved documents

        Returns:
            List of source reference dictionaries with title, url, source_type
        """
        sources = []
        seen_urls = set()

        for doc in documents:
            # Use URL as unique identifier, fall back to title
            url = doc.get("url", "")
            title = doc.get("title", "Untitled")

            # Skip duplicates (same URL)
            if url and url in seen_urls:
                continue

            source_ref = {
                "title": title,
                "url": url or None,
                "source_type": doc.get("source_type", "unknown"),
                "chunk_id": doc.get("chunk_id"),
                "score": doc.get("rrf_score") or doc.get("score", 0.0)
            }

            sources.append(source_ref)
            if url:
                seen_urls.add(url)

        logger.info(f"Extracted {len(sources)} unique source references")
        return sources

    async def generate_rag_response(
        self,
        db: AsyncSession,
        query: str,
        source_type: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate RAG response with full pipeline orchestration.

        Orchestrates:
        1. Query analysis
        2. Hybrid search
        3. Context assembly
        4. LLM response generation (streaming)
        5. Source reference extraction

        Args:
            db: Database session
            query: User query
            source_type: Optional source type filter
            temperature: Optional LLM temperature override
            max_tokens: Optional max tokens override

        Yields:
            Response chunks with metadata:
            - type: "metadata" (query analysis, sources) or "token" (LLM response)
            - data: metadata dict or token string

        Example:
            ```python
            async for chunk in rag_service.generate_rag_response(db, "What is RAG?"):
                if chunk["type"] == "metadata":
                    print(f"Metadata: {chunk['data']}")
                elif chunk["type"] == "token":
                    print(chunk["data"], end="", flush=True)
            ```
        """
        try:
            # Stage 1: Query Analysis
            logger.info(f"RAG Pipeline started for query: '{query[:100]}'")
            analysis = self.analyze_query(query)

            # Yield query analysis metadata
            yield {
                "type": "metadata",
                "stage": "query_analysis",
                "data": analysis
            }

            # Stage 2: Hybrid Search
            logger.info(f"Executing hybrid search (top_k={self.top_k})")
            documents = await search_service.hybrid_search(
                db=db,
                query=query,
                top_k=self.top_k,
                source_type=source_type,
                semantic_top_k=self.semantic_top_k,
                keyword_top_k=self.keyword_top_k
            )

            # Stage 3: Extract Source References
            sources = self.extract_source_references(documents)

            # Yield sources metadata
            yield {
                "type": "metadata",
                "stage": "sources",
                "data": {
                    "sources": sources,
                    "document_count": len(documents)
                }
            }

            # Stage 4: Assemble Context
            logger.info(f"Assembling context from {len(documents)} documents")
            context = self.assemble_context(documents)

            # Stage 5: Prepare documents for LLM
            # Convert to format expected by LLM service
            llm_documents = [
                {
                    "content": doc["content"],
                    "source": doc.get("title") or doc.get("url") or f"Document {idx}",
                    "metadata": {
                        "url": doc.get("url"),
                        "source_type": doc.get("source_type"),
                        "score": doc.get("rrf_score") or doc.get("score")
                    }
                }
                for idx, doc in enumerate(documents, start=1)
            ]

            # Stage 6: Generate LLM Response (streaming)
            logger.info("Generating LLM response with streaming")

            # Yield start of response
            yield {
                "type": "metadata",
                "stage": "response_start",
                "data": {"message": "Starting response generation"}
            }

            # Stream LLM tokens
            async for token in self.llm_service.generate_response(
                query=query,
                documents=llm_documents,
                temperature=temperature,
                max_tokens=max_tokens
            ):
                yield {
                    "type": "token",
                    "data": token
                }

            # Yield completion metadata
            yield {
                "type": "metadata",
                "stage": "complete",
                "data": {
                    "message": "Response generation complete",
                    "total_sources": len(sources)
                }
            }

            logger.info("RAG Pipeline completed successfully")

        except Exception as e:
            logger.error(f"RAG Pipeline failed: {e}")
            # Yield error metadata
            yield {
                "type": "error",
                "stage": "pipeline_error",
                "data": {
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            }
            raise RAGError(f"RAG pipeline failed: {e}")


# Global RAG service instance - lazy initialization
_rag_service_instance: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get or create the global RAG service instance."""
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RAGService()
    return _rag_service_instance


# Create instance only if not running under pytest
import sys
if 'pytest' not in sys.modules:
    rag_service = RAGService()
else:
    # In testing mode, create a placeholder
    rag_service = None  # type: ignore

