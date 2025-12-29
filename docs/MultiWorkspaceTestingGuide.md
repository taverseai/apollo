# Multi-User API Testing Guide

This guide provides step-by-step instructions for testing the multi-workspace (multi-tenant) API feature of LightRAG.

## 📋 Prerequisites

1. LightRAG server running with Milvus and Neo4j configured
2. `curl` installed (for command-line testing)
3. Optional: Python 3.10+ with `httpx` or `requests` library

## 🚀 Quick Start

### 1. Start LightRAG Server

```bash
# Navigate to LightRAG directory
cd /path/to/LightRAG

# Start the server
lightrag-server

# Or with Docker
docker-compose up -d
```

Verify the server is running:
```bash
curl http://localhost:9621/health
```

Expected response:
```json
{
  "status": "healthy",
  ...
}
```

### 2. Verify Multi-Workspace Endpoints

Check that `/v2` endpoints are available:
```bash
curl http://localhost:9621/docs
```

Look for endpoints starting with `/v2/` in the Swagger UI.

## 🧪 Test Scenarios

### Scenario 1: Basic User Isolation

This test verifies that two users cannot see each other's data.

#### Step 1: Create test documents

Create two text files for testing:

```bash
# Create document for User A
echo "Apple is a technology company founded by Steve Jobs. 
They make iPhones, iPads, and Mac computers.
Apple's headquarters is in Cupertino, California." > user_a_doc.txt

# Create document for User B  
echo "Google is a search engine company founded by Larry Page and Sergey Brin.
They developed Android, Chrome, and Google Cloud.
Google's parent company is Alphabet Inc." > user_b_doc.txt
```

#### Step 2: Upload documents for each user

```bash
# Upload for User A
curl -X POST 'http://localhost:9621/v2/documents/upload' \
  -H 'LIGHTRAG-WORKSPACE: user_A' \
  -F 'file=@user_a_doc.txt'

# Upload for User B
curl -X POST 'http://localhost:9621/v2/documents/upload' \
  -H 'LIGHTRAG-WORKSPACE: user_B' \
  -F 'file=@user_b_doc.txt'
```

Expected response for each:
```json
{
  "status": "queued",
  "message": "File 'user_a_doc.txt' uploaded and queued for processing",
  "document_id": "...",
  "file_path": "..."
}
```

#### Step 3: Wait for processing

Wait 10-30 seconds for document processing, then verify:

```bash
# Check User A's documents
curl -X GET 'http://localhost:9621/v2/documents/list' \
  -H 'LIGHTRAG-WORKSPACE: user_A'

# Check User B's documents  
curl -X GET 'http://localhost:9621/v2/documents/list' \
  -H 'LIGHTRAG-WORKSPACE: user_B'
```

#### Step 4: Query and verify isolation

```bash
# User A asks about Apple - should get results
curl -X POST 'http://localhost:9621/v2/query' \
  -H 'LIGHTRAG-WORKSPACE: user_A' \
  -H 'Content-Type: application/json' \
  -d '{"query": "Who founded Apple?", "mode": "mix"}'

# User A asks about Google - should NOT find anything (not in their docs)
curl -X POST 'http://localhost:9621/v2/query' \
  -H 'LIGHTRAG-WORKSPACE: user_A' \
  -H 'Content-Type: application/json' \
  -d '{"query": "Who founded Google?", "mode": "mix"}'

# User B asks about Google - should get results
curl -X POST 'http://localhost:9621/v2/query' \
  -H 'LIGHTRAG-WORKSPACE: user_B' \
  -H 'Content-Type: application/json' \
  -d '{"query": "Who founded Google?", "mode": "mix"}'

# User B asks about Apple - should NOT find anything
curl -X POST 'http://localhost:9621/v2/query' \
  -H 'LIGHTRAG-WORKSPACE: user_B' \
  -H 'Content-Type: application/json' \
  -d '{"query": "Who founded Apple?", "mode": "mix"}'
```

**Expected Results:**
- User A querying "Apple" → Returns info about Steve Jobs, iPhones, etc.
- User A querying "Google" → Returns "No relevant context found" or generic answer
- User B querying "Google" → Returns info about Larry Page, Android, etc.
- User B querying "Apple" → Returns "No relevant context found" or generic answer

---

### Scenario 2: Knowledge Graph Isolation

Verify that knowledge graphs are also isolated.

```bash
# Get User A's graph labels
curl -X GET 'http://localhost:9621/v2/graph/label/list' \
  -H 'LIGHTRAG-WORKSPACE: user_A'

# Get User B's graph labels
curl -X GET 'http://localhost:9621/v2/graph/label/list' \
  -H 'LIGHTRAG-WORKSPACE: user_B'
```

**Expected Results:**
- User A's labels should include: "Apple", "Steve Jobs", "iPhone", etc.
- User B's labels should include: "Google", "Larry Page", "Android", etc.
- No overlap between the two label sets

---

### Scenario 3: Document Deletion Isolation

Verify that deleting documents in one workspace doesn't affect others.

```bash
# List User A's documents and get a document ID
curl -X GET 'http://localhost:9621/v2/documents/list' \
  -H 'LIGHTRAG-WORKSPACE: user_A'

# Delete User A's document (replace DOC_ID with actual ID)
curl -X DELETE 'http://localhost:9621/v2/documents/DOC_ID' \
  -H 'LIGHTRAG-WORKSPACE: user_A'

# Verify User A's documents are gone
curl -X GET 'http://localhost:9621/v2/documents/list' \
  -H 'LIGHTRAG-WORKSPACE: user_A'

# Verify User B's documents are still intact
curl -X GET 'http://localhost:9621/v2/documents/list' \
  -H 'LIGHTRAG-WORKSPACE: user_B'
```

---

## 🐍 Python Test Script

Save this as `test_multiworkspace.py`:

```python
#!/usr/bin/env python3
"""
Multi-Workspace API Test Script

This script tests the multi-tenant functionality of LightRAG API.
"""

import asyncio
import httpx
import time
from typing import Optional

# Configuration
LIGHTRAG_URL = "http://localhost:9621"
TIMEOUT = 60.0

# Test users
USERS = {
    "alice": {
        "workspace": "user_alice",
        "document": """
        Machine Learning is a subset of artificial intelligence.
        It focuses on developing algorithms that can learn from data.
        Popular frameworks include TensorFlow, PyTorch, and scikit-learn.
        """,
        "query": "What is Machine Learning?",
        "negative_query": "What is quantum computing?",
    },
    "bob": {
        "workspace": "user_bob",
        "document": """
        Quantum Computing uses quantum mechanics principles.
        It leverages qubits instead of classical bits.
        Companies like IBM and Google are developing quantum computers.
        """,
        "query": "What is Quantum Computing?",
        "negative_query": "What is Machine Learning?",
    },
}


async def insert_text(client: httpx.AsyncClient, workspace: str, text: str) -> dict:
    """Insert text content for a workspace."""
    response = await client.post(
        f"{LIGHTRAG_URL}/v2/documents/text",
        headers={
            "LIGHTRAG-WORKSPACE": workspace,
            "Content-Type": "application/json",
        },
        json={"text": text, "description": f"Test document for {workspace}"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


async def query(client: httpx.AsyncClient, workspace: str, question: str) -> dict:
    """Query documents in a workspace."""
    response = await client.post(
        f"{LIGHTRAG_URL}/v2/query",
        headers={
            "LIGHTRAG-WORKSPACE": workspace,
            "Content-Type": "application/json",
        },
        json={"query": question, "mode": "mix", "include_references": True},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


async def list_documents(client: httpx.AsyncClient, workspace: str) -> dict:
    """List documents in a workspace."""
    response = await client.get(
        f"{LIGHTRAG_URL}/v2/documents/list",
        headers={"LIGHTRAG-WORKSPACE": workspace},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


async def get_graph_labels(client: httpx.AsyncClient, workspace: str) -> list:
    """Get graph labels for a workspace."""
    response = await client.get(
        f"{LIGHTRAG_URL}/v2/graph/label/list",
        headers={"LIGHTRAG-WORKSPACE": workspace},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


async def clear_workspace(client: httpx.AsyncClient, workspace: str) -> dict:
    """Clear all documents in a workspace."""
    response = await client.delete(
        f"{LIGHTRAG_URL}/v2/documents/clear",
        headers={"LIGHTRAG-WORKSPACE": workspace},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_result(label: str, result: any, success: Optional[bool] = None):
    """Print a formatted result."""
    status = ""
    if success is True:
        status = " ✅"
    elif success is False:
        status = " ❌"
    print(f"\n{label}{status}:")
    if isinstance(result, dict):
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False)[:500])
    else:
        print(str(result)[:500])


async def run_tests():
    """Run all multi-workspace tests."""
    async with httpx.AsyncClient() as client:
        # Test 1: Insert documents for each user
        print_header("TEST 1: Insert Documents")
        for name, config in USERS.items():
            result = await insert_text(client, config["workspace"], config["document"])
            print_result(f"Insert for {name}", result)
        
        # Wait for processing
        print("\n⏳ Waiting 15 seconds for document processing...")
        await asyncio.sleep(15)
        
        # Test 2: List documents
        print_header("TEST 2: List Documents")
        for name, config in USERS.items():
            result = await list_documents(client, config["workspace"])
            print_result(f"Documents for {name}", result)
        
        # Test 3: Query own documents (should succeed)
        print_header("TEST 3: Query Own Documents (Should Find Results)")
        for name, config in USERS.items():
            result = await query(client, config["workspace"], config["query"])
            has_content = len(result.get("response", "")) > 50
            print_result(f"Query '{config['query']}' for {name}", result, has_content)
        
        # Test 4: Query other's documents (should not find specific info)
        print_header("TEST 4: Query Other's Documents (Should NOT Find Specific Info)")
        for name, config in USERS.items():
            result = await query(client, config["workspace"], config["negative_query"])
            # Check if the response contains keywords from the other user's document
            response_lower = result.get("response", "").lower()
            
            # For alice querying quantum (should not find quantum specifics)
            # For bob querying ML (should not find ML specifics)
            if name == "alice":
                no_leak = "qubits" not in response_lower and "ibm" not in response_lower
            else:
                no_leak = "tensorflow" not in response_lower and "pytorch" not in response_lower
            
            print_result(f"Query '{config['negative_query']}' for {name}", result, no_leak)
        
        # Test 5: Graph isolation
        print_header("TEST 5: Knowledge Graph Isolation")
        for name, config in USERS.items():
            labels = await get_graph_labels(client, config["workspace"])
            print_result(f"Graph labels for {name}", labels)
        
        # Test 6: Clear workspaces
        print_header("TEST 6: Cleanup")
        for name, config in USERS.items():
            result = await clear_workspace(client, config["workspace"])
            print_result(f"Clear workspace for {name}", result)
        
        print_header("TESTS COMPLETED")
        print("\n✅ All tests executed. Check the results above for any failures.")


if __name__ == "__main__":
    print("\n🧪 LightRAG Multi-Workspace API Test Suite")
    print("=" * 60)
    asyncio.run(run_tests())
```

Run the test:
```bash
pip install httpx
python test_multiworkspace.py
```

---

## 📊 Expected Test Results Summary

| Test | Expected Result |
|------|-----------------|
| User A uploads document | Success, document queued |
| User B uploads document | Success, document queued |
| User A queries own topic | Returns relevant information |
| User A queries other's topic | Returns no specific info or generic response |
| User B queries own topic | Returns relevant information |
| User B queries other's topic | Returns no specific info or generic response |
| User A's graph labels | Contains only User A's entities |
| User B's graph labels | Contains only User B's entities |
| Delete User A's docs | Only User A's docs deleted |
| User B's docs after deletion | Still intact |

---

## 🔍 Debugging Tips

### Check Server Logs

```bash
# View real-time logs
tail -f lightrag.log

# Look for workspace-related messages
grep -i "workspace" lightrag.log
```

### Verify Storage

**Milvus Collections:**
```python
from pymilvus import connections, utility

connections.connect("default", host="localhost", port="19530")
collections = utility.list_collections()
print("Collections:", collections)
# Should show: user_A_entities, user_A_relationships, user_B_entities, etc.
```

**Neo4j Labels:**
```cypher
// Connect to Neo4j and run:
CALL db.labels() YIELD label RETURN label
// Should show: user_A, user_B, etc.
```

### Common Issues

1. **"Workspace manager not initialized"**
   - Check if server started correctly
   - Look for initialization errors in logs

2. **Empty query results**
   - Wait longer for document processing
   - Check document status: `GET /v2/documents/list`

3. **Data leaking between workspaces**
   - Verify you're including the header in ALL requests
   - Check header spelling (case-sensitive)

---

## 🎯 Performance Testing

Test with multiple concurrent users:

```python
import asyncio
import httpx
import time

async def simulate_user(user_id: int, num_queries: int = 10):
    """Simulate a user making multiple queries."""
    workspace = f"perf_test_user_{user_id}"
    
    async with httpx.AsyncClient() as client:
        # Insert a document
        await client.post(
            f"{LIGHTRAG_URL}/v2/documents/text",
            headers={"LIGHTRAG-WORKSPACE": workspace},
            json={"text": f"Test document for user {user_id} with some content."},
        )
        
        await asyncio.sleep(5)  # Wait for processing
        
        # Make queries
        times = []
        for i in range(num_queries):
            start = time.time()
            await client.post(
                f"{LIGHTRAG_URL}/v2/query",
                headers={"LIGHTRAG-WORKSPACE": workspace},
                json={"query": "What is in the document?", "mode": "naive"},
            )
            times.append(time.time() - start)
        
        avg_time = sum(times) / len(times)
        print(f"User {user_id}: avg query time = {avg_time:.3f}s")

async def run_performance_test(num_users: int = 5, queries_per_user: int = 10):
    """Run performance test with multiple concurrent users."""
    print(f"Testing with {num_users} concurrent users, {queries_per_user} queries each...")
    
    start = time.time()
    await asyncio.gather(*[
        simulate_user(i, queries_per_user) for i in range(num_users)
    ])
    total_time = time.time() - start
    
    total_queries = num_users * queries_per_user
    print(f"\nTotal: {total_queries} queries in {total_time:.2f}s")
    print(f"Throughput: {total_queries / total_time:.2f} queries/second")

asyncio.run(run_performance_test())
```

---

## 📝 Cleanup

After testing, clean up test workspaces:

```bash
# Clear all test workspaces
for user in user_A user_B user_alice user_bob; do
  curl -X DELETE "http://localhost:9621/v2/documents/clear" \
    -H "LIGHTRAG-WORKSPACE: $user"
done
```

---

## See Also

- [Multi-Workspace API Documentation](./MultiWorkspaceAPI.md)
- [Docker Deployment](./DockerDeployment.md)
- [API README](../lightrag/api/README.md)
