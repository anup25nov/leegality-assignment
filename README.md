# Network Route Optimization API

A lightweight REST API to model network servers, find lowest-latency routes using Dijkstra's algorithm, and track query history.

Built with Python 3 and SQLite (no external dependencies).

## Setup & Run

Start the server:
```bash
python3 app.py
```

Run tests:
```bash
python3 -m unittest test_app.py -v
```

---

## Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/nodes` | Add a server node |
| `POST` | `/edges` | Add a directed edge with latency |
| `POST` | `/routes/shortest` | Find lowest latency path (Dijkstra) |
| `GET` | `/routes/history` | View query history (filters: `source`, `destination`, `limit`, `date_from`, `date_to`) |
| `GET` | `/nodes` | List all nodes |
| `GET` | `/edges` | List all edges |
| `DELETE` | `/nodes/{id}` | Delete node (cascades edges) |
| `DELETE` | `/edges/{id}` | Delete edge |

---

## Quick Example

```bash
# 1. Add nodes
curl -X POST http://localhost:8000/nodes -H "Content-Type: application/json" -d '{"name": "ServerA"}'
curl -X POST http://localhost:8000/nodes -H "Content-Type: application/json" -d '{"name": "ServerB"}'
curl -X POST http://localhost:8000/nodes -H "Content-Type: application/json" -d '{"name": "ServerD"}'

# 2. Add edges
curl -X POST http://localhost:8000/edges -H "Content-Type: application/json" -d '{"source": "ServerA", "destination": "ServerB", "latency": 12.5}'
curl -X POST http://localhost:8000/edges -H "Content-Type: application/json" -d '{"source": "ServerB", "destination": "ServerD", "latency": 10.9}'

# 3. Shortest route (Returns: total_latency: 23.4, path: [ServerA, ServerB, ServerD])
curl -X POST http://localhost:8000/routes/shortest -H "Content-Type: application/json" -d '{"source": "ServerA", "destination": "ServerD"}'

# 4. View history
curl http://localhost:8000/routes/history
```
