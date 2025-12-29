"""
Multi-workspace document routes for LightRAG API.

This module provides document management endpoints that support dynamic workspace
switching via the LIGHTRAG-WORKSPACE header for multi-tenant deployments.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import aiofiles

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field

from lightrag import LightRAG
from lightrag.base import DocStatus
from lightrag.utils import logger, compute_mdhash_id, generate_track_id
from lightrag.api.utils_api import (
    get_combined_auth_dependency,
    get_workspace_rag,
    get_workspace_instance,
)
from lightrag.api.workspace_manager import WorkspaceInstance
from lightrag.api.routers.document_routes import (
    pipeline_enqueue_file,
    sanitize_filename,
)


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


# Response models
class DocumentInfo(BaseModel):
    id: str
    file_path: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    chunk_count: Optional[int] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentInfo]


class UploadResponse(BaseModel):
    status: str
    message: str
    document_id: Optional[str] = None
    file_path: Optional[str] = None


class InsertTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text content to insert")
    description: Optional[str] = Field(
        default=None, description="Optional description for the document"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional metadata"
    )


class InsertTextResponse(BaseModel):
    status: str
    message: str
    document_id: str


class DeleteResponse(BaseModel):
    status: str
    message: str
    deleted_count: int = 0


def format_datetime(dt: Any) -> Optional[str]:
    """Format datetime to ISO format string"""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def create_multiworkspace_document_routes(api_key: Optional[str] = None):
    """
    Create document routes that support dynamic workspace switching.

    These routes use the LIGHTRAG-WORKSPACE header to determine which
    workspace to operate on. Each workspace has isolated documents.

    Args:
        api_key: Optional API key for authentication

    Returns:
        APIRouter with multi-workspace document endpoints
    """
    combined_auth = get_combined_auth_dependency(api_key)

    @router.get(
        "/list",
        response_model=DocumentListResponse,
        dependencies=[Depends(combined_auth)],
        summary="List Documents with Multi-Workspace Support",
        description="""
        List all documents in the workspace specified by the LIGHTRAG-WORKSPACE header.
        
        **Multi-Tenant Usage:**
        - Set `LIGHTRAG-WORKSPACE: user_123` header to list user_123's documents
        - Each workspace has completely isolated documents
        """,
    )
    async def list_documents(
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """
        List documents in the user's workspace.
        """
        try:
            # Get documents by status or all statuses
            if status:
                docs_dict = await rag.doc_status.get_docs_by_status(DocStatus(status))
            else:
                # Get all documents across all statuses
                docs_dict = {}
                for doc_status_enum in DocStatus:
                    status_docs = await rag.doc_status.get_docs_by_status(doc_status_enum)
                    docs_dict.update(status_docs)
            
            # Convert to list and apply pagination
            all_docs = list(docs_dict.items())
            total = len(all_docs)
            paginated_docs = all_docs[offset:offset + limit]

            documents = []
            for doc_id, doc_status in paginated_docs:
                # Handle status as either string or DocStatus enum
                status_value = doc_status.status.value if hasattr(doc_status.status, 'value') else doc_status.status
                documents.append(
                    DocumentInfo(
                        id=doc_id,
                        file_path=doc_status.file_path,
                        status=status_value,
                        created_at=format_datetime(doc_status.created_at),
                        updated_at=format_datetime(doc_status.updated_at),
                        chunk_count=doc_status.chunks_count,
                        error=doc_status.error_msg,
                        metadata=doc_status.metadata,
                    )
                )

            return DocumentListResponse(total=total, documents=documents)
        except Exception as e:
            logger.error(f"Error listing documents: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/upload",
        response_model=UploadResponse,
        dependencies=[Depends(combined_auth)],
        summary="Upload Document with Multi-Workspace Support",
        description="""
        Upload a document to the workspace specified by the LIGHTRAG-WORKSPACE header.
        
        **Multi-Tenant Usage:**
        - Set `LIGHTRAG-WORKSPACE: user_123` header to upload to user_123's workspace
        - Supported formats: txt, md, pdf, docx, pptx, xlsx, html, csv, json, xml, yaml
        """,
    )
    async def upload_document(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        instance: WorkspaceInstance = Depends(get_workspace_instance),
    ):
        """
        Upload a document to the user's workspace.
        """
        rag = instance.rag
        doc_manager = instance.doc_manager

        try:
            # Validate file
            if not file.filename:
                raise HTTPException(status_code=400, detail="No filename provided")

            if not doc_manager.is_supported_file(file.filename):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type. Supported: {doc_manager.supported_extensions}",
                )

            # Sanitize filename
            safe_filename = sanitize_filename(file.filename, doc_manager.input_dir)

            # Save file
            file_path = doc_manager.input_dir / safe_filename
            content = await file.read()

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)

            # Generate track ID and enqueue
            track_id = generate_track_id(safe_filename)

            async def process_file():
                try:
                    success, _ = await pipeline_enqueue_file(rag, file_path, track_id)
                    if success:
                        # Process the enqueued documents
                        await rag.apipeline_process_enqueue_documents()
                except Exception as e:
                    logger.error(f"Error processing file {safe_filename}: {str(e)}")

            background_tasks.add_task(process_file)

            return UploadResponse(
                status="queued",
                message=f"File '{safe_filename}' uploaded and queued for processing",
                document_id=track_id,
                file_path=str(file_path),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error uploading document: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/text",
        response_model=InsertTextResponse,
        dependencies=[Depends(combined_auth)],
        summary="Insert Text with Multi-Workspace Support",
        description="""
        Insert text content directly into the workspace specified by the LIGHTRAG-WORKSPACE header.
        
        **Multi-Tenant Usage:**
        - Set `LIGHTRAG-WORKSPACE: user_123` header to insert into user_123's workspace
        - Useful for inserting content from APIs, databases, or other sources
        """,
    )
    async def insert_text(
        request: InsertTextRequest,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """
        Insert text content into the user's workspace.
        """
        try:
            # Generate document ID from content
            doc_id = compute_mdhash_id(request.text, prefix="doc-")

            # Insert the text
            await rag.ainsert(
                request.text,
                ids=[doc_id],
                file_paths=[request.description or f"text-{doc_id}"],
            )

            return InsertTextResponse(
                status="success",
                message="Text content inserted successfully",
                document_id=doc_id,
            )
        except Exception as e:
            logger.error(f"Error inserting text: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete(
        "/{document_id}",
        response_model=DeleteResponse,
        dependencies=[Depends(combined_auth)],
        summary="Delete Document with Multi-Workspace Support",
        description="""
        Delete a document from the workspace specified by the LIGHTRAG-WORKSPACE header.
        
        **Multi-Tenant Usage:**
        - Set `LIGHTRAG-WORKSPACE: user_123` header to delete from user_123's workspace
        - This also removes associated entities and relationships from the knowledge graph
        """,
    )
    async def delete_document(
        document_id: str,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """
        Delete a document from the user's workspace.
        """
        try:
            result = await rag.adelete_by_doc_id(document_id)

            if result.status == "success":
                return DeleteResponse(
                    status="success",
                    message=f"Document '{document_id}' deleted successfully",
                    deleted_count=1,
                )
            elif result.status == "not_found":
                raise HTTPException(
                    status_code=404,
                    detail=f"Document '{document_id}' not found",
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=result.message,
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/{document_id}",
        response_model=DocumentInfo,
        dependencies=[Depends(combined_auth)],
        summary="Get Document Info with Multi-Workspace Support",
        description="""
        Get information about a specific document in the workspace.
        """,
    )
    async def get_document(
        document_id: str,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """
        Get document information from the user's workspace.
        """
        try:
            doc_data = await rag.doc_status.get_by_id(document_id)

            if not doc_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document '{document_id}' not found",
                )

            doc_status = doc_data.get("status", {})

            return DocumentInfo(
                id=document_id,
                file_path=doc_status.file_path if hasattr(doc_status, "file_path") else None,
                status=doc_status.status.value if hasattr(doc_status, "status") else "unknown",
                created_at=format_datetime(
                    doc_status.created_at if hasattr(doc_status, "created_at") else None
                ),
                updated_at=format_datetime(
                    doc_status.updated_at if hasattr(doc_status, "updated_at") else None
                ),
                chunk_count=doc_status.chunks_count if hasattr(doc_status, "chunks_count") else None,
                error=doc_status.error_message if hasattr(doc_status, "error_message") else None,
                metadata=doc_status.metadata if hasattr(doc_status, "metadata") else None,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting document: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/scan",
        dependencies=[Depends(combined_auth)],
        summary="Scan Directory with Multi-Workspace Support",
        description="""
        Scan the input directory for new files and queue them for processing.
        
        Each workspace has its own input directory for file isolation.
        """,
    )
    async def scan_directory(
        background_tasks: BackgroundTasks,
        instance: WorkspaceInstance = Depends(get_workspace_instance),
    ):
        """
        Scan directory for new files in the user's workspace.
        """
        rag = instance.rag
        doc_manager = instance.doc_manager

        try:
            new_files = doc_manager.scan_directory_for_new_files()

            if not new_files:
                return {
                    "status": "no_new_files",
                    "message": "No new files found in the input directory",
                    "input_directory": str(doc_manager.input_dir),
                }

            async def process_files():
                success_count = 0
                for file_path in new_files:
                    try:
                        track_id = generate_track_id(file_path.name)
                        success, _ = await pipeline_enqueue_file(rag, file_path, track_id)
                        if success:
                            success_count += 1
                        doc_manager.mark_as_indexed(file_path)
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {str(e)}")
                
                # Process all enqueued documents after scanning
                if success_count > 0:
                    await rag.apipeline_process_enqueue_documents()

            background_tasks.add_task(process_files)

            return {
                "status": "queued",
                "message": f"Found {len(new_files)} new files, queued for processing",
                "files": [str(f.name) for f in new_files],
                "input_directory": str(doc_manager.input_dir),
            }
        except Exception as e:
            logger.error(f"Error scanning directory: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete(
        "/clear",
        response_model=DeleteResponse,
        dependencies=[Depends(combined_auth)],
        summary="Clear All Documents with Multi-Workspace Support",
        description="""
        Delete all documents from the workspace. Use with caution!
        
        This removes all documents, entities, and relationships from the workspace.
        """,
    )
    async def clear_all_documents(
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """
        Clear all documents from the user's workspace.
        """
        try:
            # Get all documents (including all statuses)
            all_docs = {}
            for status in DocStatus:
                docs = await rag.doc_status.get_docs_by_status(status)
                all_docs.update(docs)
            
            total = len(all_docs)
            if total == 0:
                return DeleteResponse(
                    status="success",
                    message="No documents to delete",
                    deleted_count=0,
                )

            # Delete each document
            deleted_count = 0
            for doc_id in all_docs.keys():
                try:
                    result = await rag.adelete_by_doc_id(doc_id)
                    if result.status == "success":
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete document {doc_id}: {str(e)}")

            return DeleteResponse(
                status="success",
                message=f"Deleted {deleted_count} of {total} documents",
                deleted_count=deleted_count,
            )
        except Exception as e:
            logger.error(f"Error clearing documents: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
