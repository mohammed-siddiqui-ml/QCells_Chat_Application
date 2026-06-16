"""
LLM service for generating chat responses using LangChain.

This module provides:
- Support for OpenAI (GPT-4 Turbo) and Ollama (llama2) based on LLM_PROVIDER env var
- Streaming response generation using async generators
- Prompt template management for system messages, context injection, and user queries
- Context window management (8k token limit)
- Retry logic with exponential backoff for API failures (max 3 retries)
- Configurable temperature and max_tokens parameters
"""
import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_community.llms import Ollama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
import tiktoken

from app.core.config import settings
from app.core.logging import logger


class LLMError(Exception):
    """Base exception for LLM service errors"""
    pass


class LLMService:
    """
    Service for generating chat responses using LLM providers.

    Supports:
    - OpenAI: GPT-4 Turbo (production)
    - Ollama: llama2 (local development)
    """

    # Context window limit in tokens
    MAX_CONTEXT_TOKENS = 8000

    # Default prompt templates
    SYSTEM_TEMPLATE = """You are an intelligent assistant for a knowledge retrieval system.
Your role is to provide accurate, helpful, and context-aware responses based on the provided context.

Guidelines:
- Answer questions accurately using the provided context
- If the context doesn't contain enough information, acknowledge it
- Be concise but comprehensive
- Cite sources when available
- Ask clarifying questions when the query is ambiguous"""

    CONTEXT_TEMPLATE = """Context information:
---
{context}
---"""

    USER_QUERY_TEMPLATE = """Based on the above context, please answer the following question:
{query}"""

    def __init__(
        self,
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ):
        """
        Initialize LLM service.

        Args:
            provider: LLM provider ("openai" or "ollama"). Defaults to LLM_PROVIDER env var
            temperature: Model temperature (0.0-1.0). Defaults to OPENAI_TEMPERATURE
            max_tokens: Maximum tokens in response. Defaults to OPENAI_MAX_TOKENS
        """
        self.provider = (provider or settings.LLM_PROVIDER).lower()
        self.temperature = temperature if temperature is not None else settings.OPENAI_TEMPERATURE
        self.max_tokens = max_tokens if max_tokens is not None else settings.OPENAI_MAX_TOKENS

        # Initialize tokenizer for context management
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

        # Initialize LLM based on provider
        self.llm = self._initialize_llm()

        logger.info(
            f"LLMService initialized with provider={self.provider}, "
            f"temperature={self.temperature}, max_tokens={self.max_tokens}"
        )

    def _initialize_llm(self) -> Any:
        """
        Initialize LLM based on configured provider.

        Returns:
            Initialized LLM instance

        Raises:
            LLMError: If initialization fails
        """
        try:
            if self.provider == "openai":
                return self._initialize_openai()
            elif self.provider == "ollama":
                return self._initialize_ollama()
            else:
                raise ValueError(
                    f"Unsupported LLM_PROVIDER: {self.provider}. Use 'openai' or 'ollama'"
                )
        except Exception as e:
            logger.error(f"Failed to initialize LLM provider {self.provider}: {e}")
            raise LLMError(f"Failed to initialize LLM: {e}")

    def _initialize_openai(self) -> ChatOpenAI:
        """Initialize OpenAI LLM."""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")

        logger.info(f"Initializing OpenAI with model: {settings.OPENAI_MODEL}")
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            openai_api_key=settings.OPENAI_API_KEY,
            streaming=True
        )

    def _initialize_ollama(self) -> Ollama:
        """Initialize Ollama LLM."""
        if not settings.OLLAMA_ENABLED and self.provider == "ollama":
            logger.warning("OLLAMA_ENABLED is False but provider is 'ollama'")

        logger.info(
            f"Initializing Ollama with model: {settings.OLLAMA_MODEL} "
            f"at {settings.OLLAMA_BASE_URL}"
        )
        return Ollama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=self.temperature,
            timeout=settings.OLLAMA_TIMEOUT
        )

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken.

        Args:
            text: Input text

        Returns:
            Number of tokens
        """
        try:
            return len(self.tokenizer.encode(text))
        except Exception as e:
            logger.warning(f"Token counting failed, using character estimate: {e}")
            # Fallback: rough estimate of 4 characters per token
            return len(text) // 4

    def truncate_context(
        self,
        documents: List[Dict[str, Any]],
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Truncate documents to fit within token limit.

        Args:
            documents: List of document dicts with 'content' and optionally 'source'
            max_tokens: Maximum tokens allowed. Defaults to MAX_CONTEXT_TOKENS

        Returns:
            Truncated context string
        """
        if max_tokens is None:
            max_tokens = self.MAX_CONTEXT_TOKENS

        context_parts = []
        total_tokens = 0

        for doc in documents:
            content = doc.get("content", "")
            source = doc.get("source", "")

            # Format document with source if available
            if source:
                doc_text = f"[Source: {source}]\n{content}\n"
            else:
                doc_text = f"{content}\n"

            doc_tokens = self.count_tokens(doc_text)

            # Check if adding this document exceeds limit
            if total_tokens + doc_tokens > max_tokens:
                # Try to add partial content
                remaining_tokens = max_tokens - total_tokens
                if remaining_tokens > 100:  # Only add if meaningful content fits
                    # Rough character estimate for remaining space
                    remaining_chars = remaining_tokens * 4
                    truncated_content = content[:remaining_chars] + "..."
                    if source:
                        doc_text = f"[Source: {source}]\n{truncated_content}\n"
                    else:
                        doc_text = f"{truncated_content}\n"
                    context_parts.append(doc_text)
                break

            context_parts.append(doc_text)
            total_tokens += doc_tokens

        context = "\n".join(context_parts)
        logger.debug(f"Context truncated to {total_tokens} tokens ({len(documents)} documents)")
        return context

    def build_prompt(
        self,
        query: str,
        context: Optional[str] = None,
        system_message: Optional[str] = None
    ) -> List[Any]:
        """
        Build prompt messages for LLM.

        Args:
            query: User query
            context: Optional context information
            system_message: Optional custom system message

        Returns:
            List of message objects
        """
        messages = []

        # Add system message
        system_msg = system_message or self.SYSTEM_TEMPLATE
        messages.append(SystemMessage(content=system_msg))

        # Add context if provided
        if context:
            context_msg = self.CONTEXT_TEMPLATE.format(context=context)
            messages.append(HumanMessage(content=context_msg))

        # Add user query
        query_msg = self.USER_QUERY_TEMPLATE.format(query=query)
        messages.append(HumanMessage(content=query_msg))

        return messages

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def _generate_with_retry(self, messages: List[Any]) -> AsyncGenerator[str, None]:
        """
        Generate response with retry logic.

        Args:
            messages: List of message objects

        Yields:
            Response tokens

        Raises:
            LLMError: If generation fails after retries
        """
        try:
            if self.provider == "openai":
                # OpenAI streaming
                async for chunk in self.llm.astream(messages):
                    if hasattr(chunk, 'content'):
                        yield chunk.content
            else:
                # Ollama streaming
                # Convert messages to string prompt for Ollama
                prompt = self._messages_to_prompt(messages)
                async for chunk in self.llm.astream(prompt):
                    yield chunk
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise LLMError(f"Failed to generate response: {e}")

    def _messages_to_prompt(self, messages: List[Any]) -> str:
        """
        Convert message objects to string prompt for Ollama.

        Args:
            messages: List of message objects

        Returns:
            Formatted prompt string
        """
        prompt_parts = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                prompt_parts.append(f"System: {msg.content}")
            elif isinstance(msg, HumanMessage):
                prompt_parts.append(f"Human: {msg.content}")
            elif isinstance(msg, AIMessage):
                prompt_parts.append(f"Assistant: {msg.content}")

        prompt_parts.append("Assistant:")
        return "\n\n".join(prompt_parts)

    async def generate_response(
        self,
        query: str,
        documents: Optional[List[Dict[str, Any]]] = None,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response for user query.

        Args:
            query: User query
            documents: Optional list of context documents
            system_message: Optional custom system message
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override

        Yields:
            Response tokens as they are generated

        Example:
            ```python
            async for token in llm_service.generate_response(
                query="What is RAG?",
                documents=[{"content": "RAG stands for...", "source": "doc1.pdf"}]
            ):
                print(token, end="", flush=True)
            ```
        """
        # Override parameters if provided
        if temperature is not None:
            self.llm.temperature = temperature
        if max_tokens is not None:
            self.llm.max_tokens = max_tokens

        # Prepare context from documents
        context = None
        if documents:
            context = self.truncate_context(documents)

        # Build prompt messages
        messages = self.build_prompt(
            query=query,
            context=context,
            system_message=system_message
        )

        # Log request
        logger.info(f"Generating response for query: {query[:100]}...")

        # Generate with retry logic
        async for token in self._generate_with_retry(messages):
            yield token


# Global LLM service instance - lazy initialization
_llm_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create the global LLM service instance."""
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
    return _llm_service_instance


# Create instance only if not running under pytest
import sys
if 'pytest' not in sys.modules:
    llm_service = LLMService()
else:
    # In testing mode, create a placeholder
    llm_service = None  # type: ignore

