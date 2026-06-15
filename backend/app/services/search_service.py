"""
Hybrid search service combining semantic (pgvector) and keyword (Elasticsearch) search.

This module provides:
- Parallel execution of semantic and keyword searches using asyncio.gather
- Semantic search using PostgreSQL pgvector with cosine distance (<=> operator)
- Keyword search using Elasticsearch multi_match on title and content fields
- Reciprocal Rank Fusion (RRF) algorithm for result combination
- Source type filtering across both search backends
- Configurable Top-K result limiting
"""
import asyncio
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models.document import DocumentChunk, Document
from app.models.source import DataSource
from app.utils.elasticsearch_client import elasticsearch_client
from app.services.genai.embedding_service import embedding_service


class SearchService:
    """
    Hybrid search service combining semantic (pgvector) and keyword (Elasticsearch) search.
    
    Uses Reciprocal Rank Fusion (RRF) to combine results from both search methods
    for optimal relevance and coverage.
    """
    
    def __init__(self, rrf_k: int = 60):
        """
        Initialize search service.
        
        Args:
            rrf_k: RRF constant parameter for rank fusion (default: 60)
        """
        self.rrf_k = rrf_k
        logger.info(f"SearchService initialized with RRF k={rrf_k}")
    
    async def semantic_search(
        self,
        db: AsyncSession,
        query_embedding: List[float],
        top_k: int = 20,
        source_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using pgvector cosine distance.
        
        Args:
            db: Database session
            query_embedding: Query embedding vector
            top_k: Number of results to return (default: 20)
            source_type: Optional source type filter (e.g., "confluence", "jira")
            
        Returns:
            List of search results with metadata and cosine distance scores
        """
        try:
            # Build query with vector similarity search
            # Using <=> operator for cosine distance in pgvector
            query = (
                select(
                    DocumentChunk.id,
                    DocumentChunk.content,
                    DocumentChunk.chunk_index,
                    DocumentChunk.meta,
                    Document.title,
                    Document.url,
                    DataSource.type.label("source_type"),
                    # Cosine distance: 0 = identical, 2 = opposite
                    # Convert to similarity score: 1 - (distance / 2)
                    (1 - (DocumentChunk.embedding.cosine_distance(query_embedding) / 2)).label("score")
                )
                .join(Document, DocumentChunk.document_id == Document.id)
                .join(DataSource, Document.source_id == DataSource.id)
            )
            
            # Apply source type filter if specified
            if source_type:
                query = query.where(DataSource.type == source_type)
            
            # Order by cosine distance (ascending) and limit results
            query = query.order_by(DocumentChunk.embedding.cosine_distance(query_embedding)).limit(top_k)
            
            result = await db.execute(query)
            rows = result.all()
            
            # Format results
            results = []
            for idx, row in enumerate(rows, start=1):
                results.append({
                    "chunk_id": str(row.id),
                    "content": row.content,
                    "title": row.title,
                    "url": row.url,
                    "source_type": row.source_type,
                    "chunk_index": row.chunk_index,
                    "metadata": row.meta or {},
                    "score": float(row.score),
                    "rank": idx,
                    "search_type": "semantic"
                })
            
            logger.info(f"Semantic search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    async def keyword_search(
        self,
        query: str,
        top_k: int = 20,
        source_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword search using Elasticsearch multi_match.
        
        Args:
            query: Search query text
            top_k: Number of results to return (default: 20)
            source_type: Optional source type filter
            
        Returns:
            List of search results with BM25 scores
        """
        try:
            # Build filters
            filters = {}
            if source_type:
                filters["source_type"] = source_type
            
            # Execute Elasticsearch keyword search
            es_results = await elasticsearch_client.keyword_search(
                query=query,
                size=top_k,
                filters=filters if filters else None
            )

            # Format results with rank
            results = []
            for idx, result in enumerate(es_results, start=1):
                results.append({
                    "chunk_id": result.get("chunk_id"),
                    "content": result.get("content"),
                    "title": result.get("title"),
                    "url": result.get("metadata", {}).get("url"),
                    "source_type": result.get("source_type"),
                    "chunk_index": result.get("metadata", {}).get("chunk_index"),
                    "metadata": result.get("metadata", {}),
                    "score": result.get("score", 0.0),
                    "rank": idx,
                    "search_type": "keyword"
                })

            logger.info(f"Keyword search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        semantic_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Combine search results using Reciprocal Rank Fusion (RRF) algorithm.

        RRF Score = sum(1 / (k + rank)) for each result across all result sets

        Args:
            semantic_results: Results from semantic search
            keyword_results: Results from keyword search
            k: RRF constant (default: uses self.rrf_k if not provided)

        Returns:
            Fused and ranked results
        """
        # Use instance rrf_k if k is not provided
        if k is None:
            k = self.rrf_k
        # Map chunk_id to combined result
        fused_results = {}

        # Process semantic search results
        for result in semantic_results:
            chunk_id = result["chunk_id"]
            rank = result["rank"]
            rrf_score = 1.0 / (k + rank)

            if chunk_id not in fused_results:
                fused_results[chunk_id] = {
                    **result,
                    "rrf_score": rrf_score,
                    "semantic_rank": rank,
                    "keyword_rank": None,
                    "search_type": "hybrid"
                }
            else:
                fused_results[chunk_id]["rrf_score"] += rrf_score
                fused_results[chunk_id]["semantic_rank"] = rank

        # Process keyword search results
        for result in keyword_results:
            chunk_id = result["chunk_id"]
            rank = result["rank"]
            rrf_score = 1.0 / (k + rank)

            if chunk_id not in fused_results:
                fused_results[chunk_id] = {
                    **result,
                    "rrf_score": rrf_score,
                    "semantic_rank": None,
                    "keyword_rank": rank,
                    "search_type": "hybrid"
                }
            else:
                fused_results[chunk_id]["rrf_score"] += rrf_score
                fused_results[chunk_id]["keyword_rank"] = rank

        # Sort by RRF score (descending)
        sorted_results = sorted(
            fused_results.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )

        logger.info(
            f"RRF fusion combined {len(semantic_results)} semantic + "
            f"{len(keyword_results)} keyword results into {len(sorted_results)} unique results"
        )

        return sorted_results

    async def hybrid_search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 10,
        source_type: Optional[str] = None,
        semantic_top_k: int = 20,
        keyword_top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining semantic and keyword search with RRF.

        Executes both searches in parallel using asyncio.gather for optimal performance.

        Args:
            db: Database session
            query: Search query text
            top_k: Number of final results to return (default: 10)
            source_type: Optional source type filter
            semantic_top_k: Number of results from semantic search (default: 20)
            keyword_top_k: Number of results from keyword search (default: 20)

        Returns:
            Top-K hybrid search results with RRF scores and source metadata
        """
        try:
            # Generate query embedding for semantic search
            logger.info(f"Generating embedding for query: '{query[:50]}...'")
            query_embedding = await embedding_service.generate_embedding(query, use_cache=True)

            # Execute both searches in parallel
            logger.info(f"Executing parallel semantic and keyword searches (Top-{semantic_top_k} each)")
            semantic_results, keyword_results = await asyncio.gather(
                self.semantic_search(
                    db=db,
                    query_embedding=query_embedding,
                    top_k=semantic_top_k,
                    source_type=source_type
                ),
                self.keyword_search(
                    query=query,
                    top_k=keyword_top_k,
                    source_type=source_type
                ),
                return_exceptions=False
            )

            # Apply Reciprocal Rank Fusion to combine results
            logger.info(f"Applying RRF fusion with k={self.rrf_k}")
            fused_results = self._reciprocal_rank_fusion(
                semantic_results=semantic_results,
                keyword_results=keyword_results,
                k=self.rrf_k
            )

            # Return top-K results
            top_results = fused_results[:top_k]

            logger.info(
                f"Hybrid search completed: returning Top-{top_k} results "
                f"(source_type={source_type or 'all'})"
            )

            return top_results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            raise


# Global search service instance
search_service = SearchService(rrf_k=60)

