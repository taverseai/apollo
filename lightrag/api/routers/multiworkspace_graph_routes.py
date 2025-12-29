"""
Multi-workspace graph routes for LightRAG API.

This module provides knowledge graph endpoints that support dynamic workspace
switching via the LIGHTRAG-WORKSPACE header for multi-tenant deployments.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from lightrag import LightRAG
from lightrag.utils import logger
from lightrag.api.utils_api import (
    get_combined_auth_dependency,
    get_workspace_rag,
)


router = APIRouter(tags=["graph"])


class EntityInfo(BaseModel):
    entity_name: str
    entity_type: Optional[str] = None
    description: Optional[str] = None
    source_id: Optional[str] = None


class RelationInfo(BaseModel):
    source: str
    target: str
    description: Optional[str] = None
    keywords: Optional[str] = None
    weight: Optional[float] = None


class EntityUpdateRequest(BaseModel):
    entity_name: str
    updated_data: Dict[str, Any]
    allow_rename: bool = False
    allow_merge: bool = False


class RelationUpdateRequest(BaseModel):
    source_id: str
    target_id: str
    updated_data: Dict[str, Any]


class EntityCreateRequest(BaseModel):
    entity_name: str = Field(..., description="Unique name for the new entity")
    entity_data: Dict[str, Any] = Field(
        ..., description="Dictionary containing entity properties"
    )


class RelationCreateRequest(BaseModel):
    source_entity: str = Field(..., description="Name of the source entity")
    target_entity: str = Field(..., description="Name of the target entity")
    relation_data: Dict[str, Any] = Field(
        ..., description="Dictionary containing relationship properties"
    )


def create_multiworkspace_graph_routes(api_key: Optional[str] = None):
    """
    Create graph routes that support dynamic workspace switching.

    These routes use the LIGHTRAG-WORKSPACE header to determine which
    workspace's knowledge graph to operate on.

    Args:
        api_key: Optional API key for authentication

    Returns:
        APIRouter with multi-workspace graph endpoints
    """
    combined_auth = get_combined_auth_dependency(api_key)

    @router.get(
        "/graph/label/list",
        dependencies=[Depends(combined_auth)],
        summary="List Graph Labels with Multi-Workspace Support",
        description="""
        Get all entity labels in the knowledge graph for the specified workspace.
        
        **Multi-Tenant Usage:**
        - Set `LIGHTRAG-WORKSPACE: user_123` header to access user_123's knowledge graph
        """,
    )
    async def get_graph_labels(
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Get all graph labels in the workspace."""
        try:
            return await rag.get_graph_labels()
        except Exception as e:
            logger.error(f"Error getting graph labels: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error getting graph labels: {str(e)}"
            )

    @router.get(
        "/graph/label/popular",
        dependencies=[Depends(combined_auth)],
        summary="Get Popular Labels with Multi-Workspace Support",
        description="Get most connected entities in the workspace's knowledge graph.",
    )
    async def get_popular_labels(
        limit: int = Query(300, ge=1, le=1000),
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Get popular labels by node degree."""
        try:
            return await rag.chunk_entity_relation_graph.get_popular_labels(limit)
        except Exception as e:
            logger.error(f"Error getting popular labels: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error getting popular labels: {str(e)}"
            )

    @router.get(
        "/graph/label/search",
        dependencies=[Depends(combined_auth)],
        summary="Search Labels with Multi-Workspace Support",
        description="Search for entity labels with fuzzy matching in the workspace.",
    )
    async def search_labels(
        q: str = Query(..., description="Search query string"),
        limit: int = Query(50, ge=1, le=100),
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Search labels with fuzzy matching."""
        try:
            return await rag.chunk_entity_relation_graph.search_labels(q, limit)
        except Exception as e:
            logger.error(f"Error searching labels: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error searching labels: {str(e)}"
            )

    @router.get(
        "/graphs",
        dependencies=[Depends(combined_auth)],
        summary="Get Knowledge Graph with Multi-Workspace Support",
        description="""
        Retrieve a connected subgraph from the workspace's knowledge graph.
        
        **Multi-Tenant Usage:**
        - Set `LIGHTRAG-WORKSPACE: user_123` header to access user_123's knowledge graph
        - Returns nodes and edges related to the specified label
        """,
    )
    async def get_knowledge_graph(
        label: str = Query(..., description="Label to get knowledge graph for"),
        max_depth: int = Query(3, ge=1),
        max_nodes: int = Query(1000, ge=1),
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Get knowledge graph for a label."""
        try:
            return await rag.get_knowledge_graph(
                node_label=label,
                max_depth=max_depth,
                max_nodes=max_nodes,
            )
        except Exception as e:
            logger.error(f"Error getting knowledge graph: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error getting knowledge graph: {str(e)}"
            )

    @router.get(
        "/graph/entity/exists",
        dependencies=[Depends(combined_auth)],
        summary="Check Entity Exists with Multi-Workspace Support",
    )
    async def check_entity_exists(
        name: str = Query(..., description="Entity name to check"),
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Check if an entity exists in the workspace."""
        try:
            exists = await rag.chunk_entity_relation_graph.has_node(name)
            return {"exists": exists, "entity_name": name}
        except Exception as e:
            logger.error(f"Error checking entity: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error checking entity: {str(e)}"
            )

    @router.get(
        "/graph/entity",
        dependencies=[Depends(combined_auth)],
        summary="Get Entity Details with Multi-Workspace Support",
    )
    async def get_entity(
        name: str = Query(..., description="Entity name"),
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Get entity details from the workspace."""
        try:
            entity = await rag.chunk_entity_relation_graph.get_node(name)
            if entity is None:
                raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
            return entity
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting entity: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error getting entity: {str(e)}"
            )

    @router.get(
        "/graph/entity/relations",
        dependencies=[Depends(combined_auth)],
        summary="Get Entity Relations with Multi-Workspace Support",
    )
    async def get_entity_relations(
        name: str = Query(..., description="Entity name"),
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Get all relations for an entity in the workspace."""
        try:
            edges = await rag.chunk_entity_relation_graph.get_node_edges(name)
            if edges is None:
                raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
            return {"entity": name, "relations": edges}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting entity relations: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error getting entity relations: {str(e)}"
            )

    @router.post(
        "/graph/entity",
        dependencies=[Depends(combined_auth)],
        summary="Create Entity with Multi-Workspace Support",
    )
    async def create_entity(
        request: EntityCreateRequest,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Create a new entity in the workspace's knowledge graph."""
        try:
            # Check if entity already exists
            exists = await rag.chunk_entity_relation_graph.has_node(request.entity_name)
            if exists:
                raise HTTPException(
                    status_code=400,
                    detail=f"Entity '{request.entity_name}' already exists",
                )

            # Create the entity
            await rag.chunk_entity_relation_graph.upsert_node(
                request.entity_name, request.entity_data
            )

            return {
                "status": "success",
                "message": f"Entity '{request.entity_name}' created successfully",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating entity: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error creating entity: {str(e)}"
            )

    @router.put(
        "/graph/entity",
        dependencies=[Depends(combined_auth)],
        summary="Update Entity with Multi-Workspace Support",
    )
    async def update_entity(
        request: EntityUpdateRequest,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Update an entity in the workspace's knowledge graph."""
        try:
            # Check if entity exists
            exists = await rag.chunk_entity_relation_graph.has_node(request.entity_name)
            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Entity '{request.entity_name}' not found",
                )

            # Update the entity
            await rag.chunk_entity_relation_graph.upsert_node(
                request.entity_name, request.updated_data
            )

            return {
                "status": "success",
                "message": f"Entity '{request.entity_name}' updated successfully",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating entity: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error updating entity: {str(e)}"
            )

    @router.delete(
        "/graph/entity",
        dependencies=[Depends(combined_auth)],
        summary="Delete Entity with Multi-Workspace Support",
    )
    async def delete_entity(
        name: str = Query(..., description="Entity name to delete"),
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Delete an entity from the workspace's knowledge graph."""
        try:
            # Check if entity exists
            exists = await rag.chunk_entity_relation_graph.has_node(name)
            if not exists:
                raise HTTPException(
                    status_code=404, detail=f"Entity '{name}' not found"
                )

            # Delete the entity
            await rag.chunk_entity_relation_graph.delete_node(name)

            return {
                "status": "success",
                "message": f"Entity '{name}' deleted successfully",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting entity: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error deleting entity: {str(e)}"
            )

    @router.post(
        "/graph/relation",
        dependencies=[Depends(combined_auth)],
        summary="Create Relation with Multi-Workspace Support",
    )
    async def create_relation(
        request: RelationCreateRequest,
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Create a new relation in the workspace's knowledge graph."""
        try:
            # Check if both entities exist
            source_exists = await rag.chunk_entity_relation_graph.has_node(
                request.source_entity
            )
            target_exists = await rag.chunk_entity_relation_graph.has_node(
                request.target_entity
            )

            if not source_exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Source entity '{request.source_entity}' not found",
                )
            if not target_exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Target entity '{request.target_entity}' not found",
                )

            # Create the relation
            await rag.chunk_entity_relation_graph.upsert_edge(
                request.source_entity, request.target_entity, request.relation_data
            )

            return {
                "status": "success",
                "message": f"Relation from '{request.source_entity}' to '{request.target_entity}' created",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating relation: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error creating relation: {str(e)}"
            )

    @router.get(
        "/graph/relation",
        dependencies=[Depends(combined_auth)],
        summary="Get Relation with Multi-Workspace Support",
    )
    async def get_relation(
        source: str = Query(..., description="Source entity name"),
        target: str = Query(..., description="Target entity name"),
        rag: LightRAG = Depends(get_workspace_rag),
    ):
        """Get relation details from the workspace."""
        try:
            edge = await rag.chunk_entity_relation_graph.get_edge(source, target)
            if edge is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Relation from '{source}' to '{target}' not found",
                )
            return edge
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting relation: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error getting relation: {str(e)}"
            )

    return router
