"""
Multi-workspace query routes for LightRAG API.

This module provides query endpoints that support dynamic workspace switching
via the LIGHTRAG-WORKSPACE header for multi-tenant deployments.
"""

import json
from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from lightrag import LightRAG
from lightrag.base import QueryParam
from lightrag.utils import logger
from lightrag.api.utils_api import (
    get_combined_auth_dependency,
    get_workspace_rag,
)


router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    query: str = Field(
        min_length=3,
        description="The query text",
    )

    mode: Literal["local", "global", "hybrid", "naive", "mix", "bypass"] = Field(
        default="mix",
        description="Query mode",
    )

    only_need_context: Optional[bool] = Field(
        default=None,
        description="If True, only returns the retrieved context without generating a response.",
    )

    only_need_prompt: Optional[bool] = Field(
        default=None,
        description="If True, only returns the generated prompt without producing a response.",
    )

    response_type: Optional[str] = Field(
        min_length=1,
        default=None,
        description="Defines the response format. Examples: 'Multiple Paragraphs', 'Single Paragraph', 'Bullet Points'.",
    )

    top_k: Optional[int] = Field(
        ge=1,
        default=None,
        description="Number of top items to retrieve.",
    )

    chunk_top_k: Optional[int] = Field(
        ge=1,
        default=None,
        description="Number of text chunks to retrieve.",
    )

    max_entity_tokens: Optional[int] = Field(
        default=None,
        description="Maximum number of tokens allocated for entity context.",
        ge=1,
    )

    max_relation_tokens: Optional[int] = Field(
        default=None,
        description="Maximum number of tokens allocated for relationship context.",
        ge=1,
    )

    max_total_tokens: Optional[int] = Field(
        default=None,
        description="Maximum total tokens budget for the entire query context.",
        ge=1,
    )

    hl_keywords: list[str] = Field(
        default_factory=list,
        description="List of high-level keywords to prioritize in retrieval.",
    )

    ll_keywords: list[str] = Field(
        default_factory=list,
        description="List of low-level keywords to refine retrieval focus.",
    )

    conversation_history: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Stores past conversation history to maintain context.",
    )

    user_prompt: Optional[str] = Field(
        default=None,
        description="User-provided prompt for the query.",
    )

    enable_rerank: Optional[bool] = Field(
        default=None,
        description="Enable reranking for retrieved text chunks.",
    )

    include_references: Optional[bool] = Field(
        default=True,
        description="If True, includes reference list in responses.",
    )

    include_chunk_content: Optional[bool] = Field(
        default=False,
        description="If True, includes source chunk content in reference list.",
    )

    stream: Optional[bool] = Field(
        default=False,
        description="If True, returns a streaming response.",
    )

    @field_validator("conversation_history", mode="before")
    @classmethod
    def parse_conversation_history(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("conversation_history must be a valid JSON array")
        return v

    def to_query_params(self, stream: bool = False) -> QueryParam:
        """Convert request to QueryParam"""
        # Build kwargs, excluding None values to let QueryParam use its defaults
        kwargs = {
            "mode": self.mode,
            "only_need_context": self.only_need_context or False,
            "only_need_prompt": self.only_need_prompt or False,
            "response_type": self.response_type or "Multiple Paragraphs",
            "top_k": self.top_k or 60,
            "chunk_top_k": self.chunk_top_k or 60,
            "hl_keywords": self.hl_keywords,
            "ll_keywords": self.ll_keywords,
            "conversation_history": self.conversation_history or [],
            "user_prompt": self.user_prompt,
            "enable_rerank": self.enable_rerank,
            "stream": stream,
        }
        
        # Only include token limits if explicitly set (not None)
        if self.max_entity_tokens is not None:
            kwargs["max_entity_tokens"] = self.max_entity_tokens
        if self.max_relation_tokens is not None:
            kwargs["max_relation_tokens"] = self.max_relation_tokens
        if self.max_total_tokens is not None:
            kwargs["max_total_tokens"] = self.max_total_tokens
            
        return QueryParam(**kwargs)


class QueryResponse(BaseModel):
    response: str
    references: Optional[List[Dict[str, Any]]] = None


class QueryDataResponse(BaseModel):
    status: str
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = None


def create_multiworkspace_query_routes(api_key: Optional[str] = None, top_k: int = 60):
    """
    Create query routes that support dynamic workspace switching.

    These routes use the LIGHTRAG-WORKSPACE header to determine which
    workspace's data to query. Each workspace has isolated data.

    Args:
        api_key: Optional API key for authentication
        top_k: Default number of top results to retrieve

    Returns:
        APIRouter with multi-workspace query endpoints
    """
    combined_auth = get_combined_auth_dependency(api_key)

    @router.post(
        "/query",
        response_model=QueryResponse,
        dependencies=[Depends(combined_auth)],
        summary="RAG Query with Multi-Workspace Support",
        description="""
        Perform a RAG query on the workspace specified by the LIGHTRAG-WORKSPACE header.
        
        **Multi-Tenant Usage:**
        - Set `LIGHTRAG-WORKSPACE: user_123` header to query user_123's documents
        - Each workspace has completely isolated data
        - If no workspace header is provided, uses the default workspace
        
        **Query Modes:**
        - **mix**: Combines knowledge graph and vector search (recommended)
        - **local**: Focuses on specific entities
        - **global**: Analyzes broader patterns
        - **hybrid**: Combines local and global
        - **naive**: Simple vector search
        """,
    )
    async def query_text(
        request: QueryRequest,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """
        Query documents in the user's workspace.

        The workspace is determined by the LIGHTRAG-WORKSPACE header.
        """
        try:
            param = request.to_query_params(False)
            param.stream = False

            result = await rag.aquery_llm(request.query, param=param)

            llm_response = result.get("llm_response", {})
            data = result.get("data", {})
            references = data.get("references", [])

            response_content = llm_response.get("content", "")
            if not response_content:
                response_content = "No relevant context found for the query."

            if request.include_references and request.include_chunk_content:
                chunks = data.get("chunks", [])
                ref_id_to_content = {}
                for chunk in chunks:
                    ref_id = chunk.get("reference_id", "")
                    content = chunk.get("content", "")
                    if ref_id and content:
                        ref_id_to_content.setdefault(ref_id, []).append(content)

                enriched_references = []
                for ref in references:
                    ref_copy = ref.copy()
                    ref_id = ref.get("reference_id", "")
                    if ref_id in ref_id_to_content:
                        ref_copy["content"] = ref_id_to_content[ref_id]
                    enriched_references.append(ref_copy)
                references = enriched_references

            if request.include_references:
                return QueryResponse(response=response_content, references=references)
            else:
                return QueryResponse(response=response_content, references=None)
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/query/stream",
        dependencies=[Depends(combined_auth)],
        summary="Streaming RAG Query with Multi-Workspace Support",
        description="""
        Perform a streaming RAG query on the workspace specified by the LIGHTRAG-WORKSPACE header.
        
        Returns NDJSON (newline-delimited JSON) format for streaming responses.
        """,
    )
    async def query_stream(
        request: QueryRequest,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """
        Streaming query on the user's workspace.

        The workspace is determined by the LIGHTRAG-WORKSPACE header.
        """
        try:
            param = request.to_query_params(True)
            param.stream = True

            async def generate():
                try:
                    result = await rag.aquery_llm(request.query, param=param)

                    llm_response = result.get("llm_response", {})
                    data = result.get("data", {})
                    references = data.get("references", [])

                    # Send references first if requested
                    if request.include_references:
                        if request.include_chunk_content:
                            chunks = data.get("chunks", [])
                            ref_id_to_content = {}
                            for chunk in chunks:
                                ref_id = chunk.get("reference_id", "")
                                content = chunk.get("content", "")
                                if ref_id and content:
                                    ref_id_to_content.setdefault(ref_id, []).append(
                                        content
                                    )

                            enriched_references = []
                            for ref in references:
                                ref_copy = ref.copy()
                                ref_id = ref.get("reference_id", "")
                                if ref_id in ref_id_to_content:
                                    ref_copy["content"] = ref_id_to_content[ref_id]
                                enriched_references.append(ref_copy)
                            references = enriched_references

                        yield json.dumps({"references": references}) + "\n"

                    # Handle streaming response
                    response_iterator = llm_response.get("response_iterator")
                    if response_iterator:
                        async for chunk in response_iterator:
                            yield json.dumps({"response": chunk}) + "\n"
                    else:
                        content = llm_response.get("content", "")
                        yield json.dumps({"response": content}) + "\n"

                except Exception as e:
                    logger.error(f"Streaming error: {str(e)}", exc_info=True)
                    yield json.dumps({"error": str(e)}) + "\n"

            return StreamingResponse(
                generate(),
                media_type="application/x-ndjson",
            )
        except Exception as e:
            logger.error(f"Error processing stream query: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/query/data",
        response_model=QueryDataResponse,
        dependencies=[Depends(combined_auth)],
        summary="RAG Query returning structured data with Multi-Workspace Support",
        description="""
        Returns complete structured retrieval data including entities, relationships,
        chunks, and references from the workspace specified by the LIGHTRAG-WORKSPACE header.
        """,
    )
    async def query_data(
        request: QueryRequest,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """
        Get structured query data from the user's workspace.

        The workspace is determined by the LIGHTRAG-WORKSPACE header.
        """
        try:
            param = request.to_query_params(False)
            response = await rag.aquery_data(request.query, param=param)

            if isinstance(response, dict):
                return QueryDataResponse(**response)
            else:
                return QueryDataResponse(
                    status="failure",
                    message="Invalid response type",
                    data={},
                )
        except Exception as e:
            logger.error(f"Error processing data query: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return router
