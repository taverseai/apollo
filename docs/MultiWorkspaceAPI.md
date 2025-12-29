# Multi-Workspace (Multi-Tenant) API Documentation

LightRAG supports multi-tenant deployments where each user has completely isolated data. This feature allows you to build applications where multiple users can upload their own documents and query only their own data.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [API Endpoints](#api-endpoints)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
- [Storage Isolation](#storage-isolation)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

The Multi-Workspace feature enables:

- **Data Isolation**: Each user/workspace has completely separated documents, entities, and relationships
- **Dynamic Workspace Switching**: Switch between workspaces per-request using HTTP headers
- **Single Server Instance**: No need to run multiple server instances for different users
- **Backward Compatibility**: Original `/` endpoints still work with the default workspace

### Key Concept: Workspace

A **workspace** is a logical container that isolates:
- Documents and their processing status
- Knowledge graph entities and relationships
- Vector embeddings for semantic search
- File storage directories

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        LightRAG Server                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   WorkspaceManager                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ Workspace A │  │ Workspace B │  │ Workspace C │ ...  │   │
│  │  │ (user_123)  │  │ (user_456)  │  │ (user_789)  │      │   │
│  │  │             │  │             │  │             │      │   │
│  │  │ - LightRAG  │  │ - LightRAG  │  │ - LightRAG  │      │   │
│  │  │ - DocMgr    │  │ - DocMgr    │  │ - DocMgr    │      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                      Storage Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  PostgreSQL  │  │    Neo4j     │  │  File Store  │          │
│  │ (KV/Vector/  │  │   (Graph)    │  │  (Documents) │          │
│  │  DocStatus)  │  │              │  │              │          │
│  │              │  │ Label:       │  │ /user_123/   │          │
│  │ workspace    │  │  user_123    │  │ /user_456/   │          │
│  │ column-based │  │  user_456    │  │ /user_789/   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## API Endpoints

All multi-workspace endpoints are available under the `/v2` prefix and require the `LIGHTRAG-WORKSPACE` header.

### Header

| Header | Type | Required | Description |
|--------|------|----------|-------------|
| `LIGHTRAG-WORKSPACE` | string | No | Workspace identifier. If not provided, uses the default workspace. |

### Query Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v2/query` | RAG query with non-streaming response |
| POST | `/v2/query/stream` | RAG query with streaming response (NDJSON) |
| POST | `/v2/query/data` | Get structured retrieval data (entities, relations, chunks) |

### Document Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v2/documents/list` | List all documents in the workspace |
| POST | `/v2/documents/upload` | Upload a document file |
| POST | `/v2/documents/text` | Insert text content directly |
| POST | `/v2/documents/scan` | Scan input directory for new files |
| GET | `/v2/documents/{id}` | Get document details |
| DELETE | `/v2/documents/{id}` | Delete a document |
| DELETE | `/v2/documents/clear` | Delete all documents in workspace |

### Graph Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v2/graph/label/list` | List all entity labels |
| GET | `/v2/graph/label/popular` | Get popular labels by degree |
| GET | `/v2/graph/label/search` | Search labels with fuzzy matching |
| GET | `/v2/graphs` | Get knowledge graph for a label |
| GET | `/v2/graph/entity` | Get entity details |
| GET | `/v2/graph/entity/exists` | Check if entity exists |
| GET | `/v2/graph/entity/relations` | Get entity's relations |
| POST | `/v2/graph/entity` | Create a new entity |
| PUT | `/v2/graph/entity` | Update an entity |
| DELETE | `/v2/graph/entity` | Delete an entity |
| GET | `/v2/graph/relation` | Get relation details |
| POST | `/v2/graph/relation` | Create a new relation |

## Usage Examples

### Python with httpx

```python
import httpx
import asyncio

LIGHTRAG_URL = "http://localhost:9621"

async def upload_document(user_id: str, file_path: str):
    """Upload a document for a specific user."""
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            response = await client.post(
                f"{LIGHTRAG_URL}/v2/documents/upload",
                headers={"LIGHTRAG-WORKSPACE": f"user_{user_id}"},
                files={"file": f}
            )
        return response.json()

async def query_documents(user_id: str, question: str):
    """Query documents for a specific user."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{LIGHTRAG_URL}/v2/query",
            headers={
                "LIGHTRAG-WORKSPACE": f"user_{user_id}",
                "Content-Type": "application/json"
            },
            json={
                "query": question,
                "mode": "mix",
                "include_references": True
            }
        )
        return response.json()

async def list_user_documents(user_id: str):
    """List all documents for a specific user."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{LIGHTRAG_URL}/v2/documents/list",
            headers={"LIGHTRAG-WORKSPACE": f"user_{user_id}"}
        )
        return response.json()

# Example usage
async def main():
    # User A uploads a document
    await upload_document("alice", "report.pdf")
    
    # User B uploads a different document
    await upload_document("bob", "notes.txt")
    
    # User A queries their documents (won't see Bob's data)
    result_a = await query_documents("alice", "What is in the report?")
    print(f"Alice's result: {result_a}")
    
    # User B queries their documents (won't see Alice's data)
    result_b = await query_documents("bob", "What are the notes about?")
    print(f"Bob's result: {result_b}")

asyncio.run(main())
```

### Python with requests (synchronous)

```python
import requests

LIGHTRAG_URL = "http://localhost:9621"

def query_for_user(user_id: str, question: str):
    """Query documents for a specific user."""
    response = requests.post(
        f"{LIGHTRAG_URL}/v2/query",
        headers={
            "LIGHTRAG-WORKSPACE": f"user_{user_id}",
            "Content-Type": "application/json"
        },
        json={
            "query": question,
            "mode": "mix"
        }
    )
    return response.json()

# Query for different users
result_alice = query_for_user("alice", "Summarize the document")
result_bob = query_for_user("bob", "What are the key points?")
```

### cURL Examples

```bash
# Upload document for user_123
curl -X POST 'http://localhost:9621/v2/documents/upload' \
  -H 'LIGHTRAG-WORKSPACE: user_123' \
  -F 'file=@/path/to/document.pdf'

# Query for user_123
curl -X POST 'http://localhost:9621/v2/query' \
  -H 'LIGHTRAG-WORKSPACE: user_123' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What is the main topic?",
    "mode": "mix",
    "include_references": true
  }'

# List documents for user_456
curl -X GET 'http://localhost:9621/v2/documents/list' \
  -H 'LIGHTRAG-WORKSPACE: user_456'

# Insert text for user_789
curl -X POST 'http://localhost:9621/v2/documents/text' \
  -H 'LIGHTRAG-WORKSPACE: user_789' \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "This is the content to be indexed...",
    "description": "My notes"
  }'

# Get knowledge graph for user_123
curl -X GET 'http://localhost:9621/v2/graphs?label=AI&max_depth=2' \
  -H 'LIGHTRAG-WORKSPACE: user_123'

# Delete a document
curl -X DELETE 'http://localhost:9621/v2/documents/doc-abc123' \
  -H 'LIGHTRAG-WORKSPACE: user_123'
```

### JavaScript/TypeScript (fetch)

```typescript
const LIGHTRAG_URL = "http://localhost:9621";

async function queryForUser(userId: string, question: string) {
  const response = await fetch(`${LIGHTRAG_URL}/v2/query`, {
    method: "POST",
    headers: {
      "LIGHTRAG-WORKSPACE": `user_${userId}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query: question,
      mode: "mix",
      include_references: true,
    }),
  });
  return response.json();
}

async function uploadDocument(userId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${LIGHTRAG_URL}/v2/documents/upload`, {
    method: "POST",
    headers: {
      "LIGHTRAG-WORKSPACE": `user_${userId}`,
    },
    body: formData,
  });
  return response.json();
}
```

## Configuration

### Environment Variables

For multi-workspace support with PostgreSQL, configure these storage settings:

```bash
# Storage backends for multi-workspace
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_GRAPH_STORAGE=Neo4JStorage

# PostgreSQL connection
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=lightrag
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password

# Neo4j connection (for graph storage)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

The default workspace is determined by the `WORKSPACE` environment variable or the `--workspace` command-line argument.

### Storage-Specific Workspace Variables

You can override the workspace for specific storage backends:

| Variable | Description |
|----------|-------------|
| `PG_WORKSPACE` | Override workspace for PostgreSQL storage (KV, Vector, DocStatus) |
| `NEO4J_WORKSPACE` | Override workspace for Neo4j graph storage |

## Storage Isolation

### PostgreSQL (KV, Vector, DocStatus)

All PostgreSQL tables use a `workspace` column for isolation. Data is stored in shared tables but filtered by workspace:

```sql
-- All workspaces share the same tables, filtered by workspace column
SELECT * FROM LIGHTRAG_DOC_STATUS WHERE workspace = 'user_123';
SELECT * FROM LIGHTRAG_VDB_ENTITIES WHERE workspace = 'user_123';
SELECT * FROM LIGHTRAG_VDB_RELATIONSHIPS WHERE workspace = 'user_123';
SELECT * FROM LIGHTRAG_VDB_CHUNKS WHERE workspace = 'user_123';
```

**Advantages of column-based isolation:**
- No collection limits (unlike Milvus free tier with 5 collection limit)
- Efficient storage with shared indexes
- Easy backup and migration
- Simple workspace cleanup with DELETE queries

### Neo4j (Graph Database)

Nodes use workspace labels:
```cypher
-- User 123's entities have label "user_123"
MATCH (n:`user_123` {entity_id: "AI"}) RETURN n

-- User 456's entities are separate
MATCH (n:`user_456` {entity_id: "AI"}) RETURN n
```

### File Storage

Documents are stored in workspace subdirectories:
```
inputs/
  ├── user_123/
  │   ├── document1.pdf
  │   └── document2.txt
  ├── user_456/
  │   └── notes.md
  └── user_789/
      └── report.docx
```

## Best Practices

### 1. Workspace Naming

Use consistent, URL-safe workspace names:
```python
# Good
workspace = f"user_{user_id}"
workspace = f"org_{org_id}_project_{project_id}"

# Avoid special characters
workspace = "user-123"  # OK
workspace = "user_123"  # OK
workspace = "user/123"  # Avoid
```

### 2. Error Handling

Always handle workspace-related errors:
```python
async def safe_query(user_id: str, question: str):
    try:
        response = await query_documents(user_id, question)
        if "error" in response:
            logger.error(f"Query error for {user_id}: {response['error']}")
            return None
        return response
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 500:
            logger.error(f"Server error for workspace {user_id}")
        raise
```

### 3. Middleware Integration

Create a middleware to automatically add workspace headers:
```python
from fastapi import Request

class WorkspaceMiddleware:
    async def __call__(self, request: Request, call_next):
        # Get user from authentication
        user = request.state.user
        
        # Forward to LightRAG with workspace header
        request.state.lightrag_workspace = f"user_{user.id}"
        
        return await call_next(request)
```

### 4. Rate Limiting per Workspace

Consider implementing rate limiting per workspace to prevent abuse:
```python
from collections import defaultdict
import time

class WorkspaceRateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.requests = defaultdict(list)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
    
    def is_allowed(self, workspace: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        self.requests[workspace] = [
            t for t in self.requests[workspace] if t > window_start
        ]
        
        if len(self.requests[workspace]) >= self.max_requests:
            return False
        
        self.requests[workspace].append(now)
        return True
```

## Troubleshooting

### Common Issues

#### 1. "Workspace manager not initialized"

**Cause**: The WorkspaceManager failed to initialize on server startup.

**Solution**: Check server logs for initialization errors. Ensure all required dependencies are installed.

#### 2. Empty results when querying

**Cause**: Querying a workspace that has no documents.

**Solution**: Verify documents were uploaded to the correct workspace. Check the workspace header spelling.

```bash
# Verify documents exist
curl -X GET 'http://localhost:9621/v2/documents/list' \
  -H 'LIGHTRAG-WORKSPACE: user_123'
```

#### 3. Cross-workspace data leakage

**Cause**: Not setting the workspace header consistently.

**Solution**: Always include `LIGHTRAG-WORKSPACE` header in all requests. If the header is missing, requests go to the default workspace.

#### 4. "Collection not found" in Milvus

**Cause**: First request to a new workspace before any documents are uploaded.

**Solution**: This is normal. The collection is created when the first document is inserted.

### Debug Mode

Enable debug logging to troubleshoot workspace issues:

```bash
# Set log level to DEBUG
export LOG_LEVEL=DEBUG
lightrag-server
```

Check logs for workspace-related messages:
```
[INFO] Created new LightRAG instance for workspace: 'user_123'
[DEBUG] Final namespace with workspace prefix: 'user_123_entities'
```

## API Reference

### Query Request Schema

```json
{
  "query": "string (required, min 3 chars)",
  "mode": "local|global|hybrid|naive|mix|bypass (default: mix)",
  "only_need_context": "boolean (default: false)",
  "only_need_prompt": "boolean (default: false)",
  "response_type": "string (default: 'Multiple Paragraphs')",
  "top_k": "integer (default: 60)",
  "chunk_top_k": "integer (default: 60)",
  "max_entity_tokens": "integer (optional)",
  "max_relation_tokens": "integer (optional)",
  "max_total_tokens": "integer (optional)",
  "hl_keywords": "array of strings (optional)",
  "ll_keywords": "array of strings (optional)",
  "conversation_history": "array of {role, content} (optional)",
  "user_prompt": "string (optional)",
  "enable_rerank": "boolean (optional)",
  "include_references": "boolean (default: true)",
  "include_chunk_content": "boolean (default: false)",
  "stream": "boolean (default: false)"
}
```

### Query Response Schema

```json
{
  "response": "string - The generated answer",
  "references": [
    {
      "reference_id": "1",
      "file_path": "/path/to/source.pdf",
      "content": ["chunk1", "chunk2"]  // Only if include_chunk_content=true
    }
  ]
}
```

### Document List Response Schema

```json
{
  "total": 42,
  "documents": [
    {
      "id": "doc-abc123",
      "file_path": "document.pdf",
      "status": "PROCESSED",
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:35:00Z",
      "chunk_count": 15,
      "error": null,
      "metadata": {}
    }
  ]
}
```

## See Also

- [Docker Deployment Guide](./DockerDeployment.md)
- [Offline Deployment Guide](./OfflineDeployment.md)
- [LightRAG API README](../lightrag/api/README.md)
