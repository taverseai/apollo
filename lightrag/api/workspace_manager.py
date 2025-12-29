"""
Workspace Manager for Multi-Tenant LightRAG API.

This module provides dynamic workspace management, allowing the API to handle
multiple users with isolated data through workspace-specific LightRAG instances.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from lightrag import LightRAG
from lightrag.utils import logger
from lightrag.api.routers.document_routes import DocumentManager


@dataclass
class WorkspaceConfig:
    """Configuration for creating LightRAG instances."""

    working_dir: str
    llm_model_func: Callable
    llm_model_name: str
    llm_model_max_async: int
    summary_max_tokens: int
    summary_context_size: int
    chunk_token_size: int
    chunk_overlap_token_size: int
    llm_model_kwargs: Dict[str, Any]
    embedding_func: Any
    default_llm_timeout: int
    default_embedding_timeout: int
    kv_storage: str
    graph_storage: str
    vector_storage: str
    doc_status_storage: str
    vector_db_storage_cls_kwargs: Dict[str, Any]
    enable_llm_cache_for_entity_extract: bool
    enable_llm_cache: bool
    rerank_model_func: Optional[Callable]
    max_parallel_insert: int
    max_graph_nodes: int
    addon_params: Dict[str, Any]
    ollama_server_infos: Any
    input_dir: str
    supported_extensions: tuple = (
        ".txt",
        ".md",
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".rtf",
        ".odt",
        ".tex",
        ".epub",
        ".html",
        ".htm",
        ".csv",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".log",
        ".conf",
        ".ini",
        ".properties",
        ".sql",
        ".bat",
        ".sh",
        ".c",
        ".cpp",
        ".py",
        ".java",
        ".js",
        ".ts",
        ".swift",
        ".go",
        ".rb",
        ".php",
        ".css",
        ".scss",
        ".less",
    )


@dataclass
class WorkspaceInstance:
    """Holds a LightRAG instance and its associated DocumentManager."""

    rag: LightRAG
    doc_manager: DocumentManager


class WorkspaceManager:
    """
    Manages multiple LightRAG instances for different workspaces.

    This class provides thread-safe creation and caching of LightRAG instances,
    enabling multi-tenant support where each user/workspace has isolated data.
    """

    def __init__(self, config: WorkspaceConfig, default_workspace: str = ""):
        """
        Initialize the WorkspaceManager.

        Args:
            config: Configuration for creating LightRAG instances
            default_workspace: The default workspace to use when none is specified
        """
        self._config = config
        self._default_workspace = default_workspace
        self._instances: Dict[str, WorkspaceInstance] = {}
        self._lock = asyncio.Lock()
        self._init_locks: Dict[str, asyncio.Lock] = {}

    @property
    def default_workspace(self) -> str:
        """Get the default workspace name."""
        return self._default_workspace

    def _get_init_lock(self, workspace: str) -> asyncio.Lock:
        """Get or create an initialization lock for a specific workspace."""
        if workspace not in self._init_locks:
            self._init_locks[workspace] = asyncio.Lock()
        return self._init_locks[workspace]

    async def get_instance(self, workspace: Optional[str] = None) -> WorkspaceInstance:
        """
        Get or create a LightRAG instance for the specified workspace.

        Args:
            workspace: The workspace identifier. If None or empty, uses default workspace.

        Returns:
            WorkspaceInstance containing the LightRAG instance and DocumentManager
        """
        # Normalize workspace
        effective_workspace = (workspace or "").strip()
        if not effective_workspace:
            effective_workspace = self._default_workspace

        # Fast path: check if instance exists
        if effective_workspace in self._instances:
            return self._instances[effective_workspace]

        # Slow path: need to create instance with proper locking
        init_lock = self._get_init_lock(effective_workspace)
        async with init_lock:
            # Double-check after acquiring lock
            if effective_workspace in self._instances:
                return self._instances[effective_workspace]

            # Create new instance
            instance = await self._create_instance(effective_workspace)
            self._instances[effective_workspace] = instance

            logger.info(
                f"Created new LightRAG instance for workspace: '{effective_workspace}'"
            )
            return instance

    async def _create_instance(self, workspace: str) -> WorkspaceInstance:
        """
        Create a new LightRAG instance for the specified workspace.

        Args:
            workspace: The workspace identifier

        Returns:
            WorkspaceInstance with initialized LightRAG and DocumentManager
        """
        config = self._config

        # Create LightRAG instance with workspace
        rag = LightRAG(
            working_dir=config.working_dir,
            workspace=workspace,
            llm_model_func=config.llm_model_func,
            llm_model_name=config.llm_model_name,
            llm_model_max_async=config.llm_model_max_async,
            summary_max_tokens=config.summary_max_tokens,
            summary_context_size=config.summary_context_size,
            chunk_token_size=config.chunk_token_size,
            chunk_overlap_token_size=config.chunk_overlap_token_size,
            llm_model_kwargs=config.llm_model_kwargs,
            embedding_func=config.embedding_func,
            default_llm_timeout=config.default_llm_timeout,
            default_embedding_timeout=config.default_embedding_timeout,
            kv_storage=config.kv_storage,
            graph_storage=config.graph_storage,
            vector_storage=config.vector_storage,
            doc_status_storage=config.doc_status_storage,
            vector_db_storage_cls_kwargs=config.vector_db_storage_cls_kwargs,
            enable_llm_cache_for_entity_extract=config.enable_llm_cache_for_entity_extract,
            enable_llm_cache=config.enable_llm_cache,
            rerank_model_func=config.rerank_model_func,
            max_parallel_insert=config.max_parallel_insert,
            max_graph_nodes=config.max_graph_nodes,
            addon_params=config.addon_params,
            ollama_server_infos=config.ollama_server_infos,
        )

        # Initialize storages (Milvus, Neo4j, etc.) - CRITICAL!
        await rag.initialize_storages()

        # Process any pending documents from previous sessions
        try:
            await rag.apipeline_process_enqueue_documents()
            logger.info(f"Processed pending documents for workspace: '{workspace}'")
        except Exception as e:
            logger.warning(f"Error processing pending documents for workspace '{workspace}': {e}")

        # Create DocumentManager with workspace-specific directory
        doc_manager = DocumentManager(
            input_dir=config.input_dir,
            workspace=workspace,
            supported_extensions=config.supported_extensions,
        )

        return WorkspaceInstance(rag=rag, doc_manager=doc_manager)

    def get_rag(self, workspace: Optional[str] = None) -> Optional[LightRAG]:
        """
        Synchronously get a cached LightRAG instance if it exists.

        Args:
            workspace: The workspace identifier

        Returns:
            LightRAG instance if cached, None otherwise
        """
        effective_workspace = (workspace or "").strip() or self._default_workspace
        instance = self._instances.get(effective_workspace)
        return instance.rag if instance else None

    def get_doc_manager(self, workspace: Optional[str] = None) -> Optional[DocumentManager]:
        """
        Synchronously get a cached DocumentManager if it exists.

        Args:
            workspace: The workspace identifier

        Returns:
            DocumentManager if cached, None otherwise
        """
        effective_workspace = (workspace or "").strip() or self._default_workspace
        instance = self._instances.get(effective_workspace)
        return instance.doc_manager if instance else None

    def list_workspaces(self) -> list[str]:
        """
        List all currently loaded workspaces.

        Returns:
            List of workspace identifiers
        """
        return list(self._instances.keys())

    async def remove_instance(self, workspace: str) -> bool:
        """
        Remove a workspace instance from cache.

        Args:
            workspace: The workspace identifier to remove

        Returns:
            True if instance was removed, False if it didn't exist
        """
        effective_workspace = workspace.strip() if workspace else ""
        if not effective_workspace:
            effective_workspace = self._default_workspace

        init_lock = self._get_init_lock(effective_workspace)
        async with init_lock:
            if effective_workspace in self._instances:
                del self._instances[effective_workspace]
                logger.info(f"Removed LightRAG instance for workspace: '{effective_workspace}'")
                return True
            return False

    async def finalize_all(self):
        """Finalize all LightRAG instances (cleanup)."""
        for workspace, instance in self._instances.items():
            try:
                await instance.rag.finalize_storages()
                logger.info(f"Finalized storage for workspace: '{workspace}'")
            except Exception as e:
                logger.error(f"Error finalizing workspace '{workspace}': {e}")


# Global workspace manager instance (set during app startup)
_workspace_manager: Optional[WorkspaceManager] = None


def get_workspace_manager() -> WorkspaceManager:
    """Get the global workspace manager instance."""
    if _workspace_manager is None:
        raise RuntimeError("WorkspaceManager not initialized. Call set_workspace_manager first.")
    return _workspace_manager


def set_workspace_manager(manager: WorkspaceManager):
    """Set the global workspace manager instance."""
    global _workspace_manager
    _workspace_manager = manager
