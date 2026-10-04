import argparse
import json
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from db import Database
from routing import find_shortest_path


class APIHandler(BaseHTTPRequestHandler):
    @property
    def db(self):
        return self.server.db

    def send_json(self, status, data):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error(self, status, message):
        self.send_json(status, {"error": message})

    def parse_body(self):
        length = self.headers.get("Content-Length")
        if not length:
            return None, "Request body is missing"
        try:
            raw = self.rfile.read(int(length)).decode("utf-8")
            return json.loads(raw), None
        except Exception:
            return None, "Invalid JSON payload"

    # --- GET Handlers ---

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path in ("", "/health"):
            self.send_json(200, {"status": "ok"})
            return

        if path == "/nodes":
            self.send_json(200, self.db.list_nodes())
            return

        if path == "/edges":
            self.send_json(200, self.db.list_edges())
            return

        if path == "/routes/history":
            self.handle_history(params)
            return

        self.send_error(404, f"Endpoint {self.path} not found")

    def handle_history(self, params):
        source = params.get("source", [None])[0]
        destination = params.get("destination", [None])[0]

        limit = None
        if "limit" in params:
            try:
                limit = int(params["limit"][0])
                if limit <= 0:
                    self.send_error(400, "Limit must be a positive integer")
                    return
            except ValueError:
                self.send_error(400, "Invalid limit parameter")
                return

        date_from = params.get("date_from", [None])[0]
        date_to = params.get("date_to", [None])[0]
        for val, name in [(date_from, "date_from"), (date_to, "date_to")]:
            if val:
                try:
                    datetime.fromisoformat(val.replace("Z", "+00:00"))
                except ValueError:
                    self.send_error(400, f"Invalid date format for {name}")
                    return

        records = self.db.get_history(source, destination, limit, date_from, date_to)
        self.send_json(200, records)

    # --- POST Handlers ---

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")

        if path == "/nodes":
            self.handle_add_node()
        elif path == "/edges":
            self.handle_add_edge()
        elif path == "/routes/shortest":
            self.handle_shortest_route()
        else:
            self.send_error(404, f"Endpoint {self.path} not found")

    def handle_add_node(self):
        data, err = self.parse_body()
        if err:
            self.send_error(400, err)
            return

        name = data.get("name") if isinstance(data, dict) else None
        if not name or not isinstance(name, str) or not name.strip():
            self.send_error(400, "Node name is required")
            return

        name = name.strip()
        if self.db.get_node(name):
            self.send_error(400, f"Node '{name}' already exists")
            return

        node = self.db.add_node(name)
        self.send_json(201, node)

    def handle_add_edge(self):
        data, err = self.parse_body()
        if err:
            self.send_error(400, err)
            return

        source = data.get("source") if isinstance(data, dict) else None
        destination = data.get("destination") if isinstance(data, dict) else None
        latency = data.get("latency") if isinstance(data, dict) else None

        if not source or not isinstance(source, str) or not destination or not isinstance(destination, str):
            self.send_error(400, "Source and destination are required")
            return

        source, destination = source.strip(), destination.strip()

        if source.lower() == destination.lower():
            self.send_error(400, "Source and destination cannot be identical")
            return

        if latency is None or not isinstance(latency, (int, float)) or latency <= 0:
            self.send_error(400, "Latency must be a number greater than 0")
            return

        src_node = self.db.get_node(source)
        dst_node = self.db.get_node(destination)
        if not src_node or not dst_node:
            missing = [s for s, n in [(source, src_node), (destination, dst_node)] if not n]
            self.send_error(400, f"Node(s) not found: {', '.join(missing)}")
            return

        if self.db.get_edge(src_node["name"], dst_node["name"]):
            self.send_error(400, f"Edge from '{source}' to '{destination}' already exists")
            return

        edge = self.db.add_edge(src_node["name"], dst_node["name"], float(latency))
        self.send_json(201, edge)

    def handle_shortest_route(self):
        data, err = self.parse_body()
        if err:
            self.send_error(400, err)
            return

        source = data.get("source") if isinstance(data, dict) else None
        destination = data.get("destination") if isinstance(data, dict) else None

        if not source or not destination or not isinstance(source, str) or not isinstance(destination, str):
            self.send_error(400, "Valid source and destination are required")
            return

        source, destination = source.strip(), destination.strip()

        src_node = self.db.get_node(source)
        dst_node = self.db.get_node(destination)
        if not src_node or not dst_node:
            missing = [s for s, n in [(source, src_node), (destination, dst_node)] if not n]
            self.send_error(400, f"Node(s) not found: {', '.join(missing)}")
            return

        edges = self.db.list_edges()
        result = find_shortest_path(edges, src_node["name"], dst_node["name"])

        if result is None:
            self.send_error(404, f"No path exists between {src_node['name']} and {dst_node['name']}")
            return

        total_latency, path = result
        self.db.log_query(src_node["name"], dst_node["name"], total_latency, path)
        self.send_json(200, {"total_latency": total_latency, "path": path})

    # --- DELETE Handlers ---

    def do_DELETE(self):
        path = urlparse(self.path).path.rstrip("/")

        node_match = re.match(r"^/nodes/(\d+)$", path)
        if node_match:
            node_id = int(node_match.group(1))
            if self.db.delete_node(node_id):
                self.send_json(200, {"message": f"Node {node_id} deleted successfully"})
            else:
                self.send_error(404, f"Node {node_id} not found")
            return

        edge_match = re.match(r"^/edges/(\d+)$", path)
        if edge_match:
            edge_id = int(edge_match.group(1))
            if self.db.delete_edge(edge_id):
                self.send_json(200, {"message": f"Edge {edge_id} deleted successfully"})
            else:
                self.send_error(404, f"Edge {edge_id} not found")
            return

        self.send_error(404, f"Endpoint {self.path} not found")

    def log_message(self, format, *args):
        pass  # Suppress default noisy stderr server logs


def run_server(host="0.0.0.0", port=8000, db_path="network.db"):
    server = ThreadingHTTPServer((host, port), APIHandler)
    server.db = Database(db_path=db_path)
    print(f"Server running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="network.db")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, db_path=args.db)
