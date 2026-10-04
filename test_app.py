import io
import json
import os
import tempfile
import unittest

from app import APIHandler
from db import Database


class InMemoryClient:
    def __init__(self, db):
        class MockServer:
            pass

        self.server = MockServer()
        self.server.db = db

    def request(self, method, path, body=None):
        body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""

        headers = [
            f"{method} {path} HTTP/1.1",
            "Host: localhost",
            f"Content-Length: {len(body_bytes)}",
        ]
        if body is not None:
            headers.append("Content-Type: application/json")

        req_bytes = "\r\n".join(headers).encode("utf-8") + b"\r\n\r\n" + body_bytes

        class DummySocket:
            def __init__(self, data):
                self._r = io.BytesIO(data)
                self._w = io.BytesIO()

            def makefile(self, mode, *args, **kwargs):
                return self._r if "r" in mode else self._w

            def sendall(self, b):
                self._w.write(b)

            def get_data(self):
                return self._w.getvalue()

        sock = DummySocket(req_bytes)
        APIHandler(sock, ("127.0.0.1", 9999), self.server)

        output = sock.get_data()
        status_line, rest = output.split(b"\r\n", 1)
        status_code = int(status_line.decode().split(" ")[1])

        _, _, body_bytes = rest.partition(b"\r\n\r\n")
        resp_json = json.loads(body_bytes.decode()) if body_bytes else None
        return status_code, resp_json


class TestNetworkRoutes(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        self.db = Database(self.temp_path)
        self.client = InMemoryClient(self.db)

    def tearDown(self):
        self.db.close()
        try:
            os.close(self.temp_fd)
            os.remove(self.temp_path)
        except OSError:
            pass

    # Nodes
    def test_add_node(self):
        status, data = self.client.request("POST", "/nodes", {"name": "ServerA"})
        self.assertEqual(status, 201)
        self.assertEqual(data["name"], "ServerA")
        self.assertIn("id", data)

    def test_add_duplicate_node(self):
        self.client.request("POST", "/nodes", {"name": "ServerA"})
        status, data = self.client.request("POST", "/nodes", {"name": "ServerA"})
        self.assertEqual(status, 400)
        self.assertIn("already exists", data["error"])

    def test_add_node_validation(self):
        status, _ = self.client.request("POST", "/nodes", {})
        self.assertEqual(status, 400)

        status, _ = self.client.request("POST", "/nodes", {"name": "   "})
        self.assertEqual(status, 400)

    # Edges
    def test_add_edge(self):
        self.client.request("POST", "/nodes", {"name": "ServerA"})
        self.client.request("POST", "/nodes", {"name": "ServerB"})

        status, data = self.client.request("POST", "/edges", {
            "source": "ServerA",
            "destination": "ServerB",
            "latency": 12.5,
        })
        self.assertEqual(status, 201)
        self.assertEqual(data["source"], "ServerA")
        self.assertEqual(data["destination"], "ServerB")
        self.assertEqual(data["latency"], 12.5)

    def test_add_edge_missing_node(self):
        self.client.request("POST", "/nodes", {"name": "ServerA"})
        status, data = self.client.request("POST", "/edges", {
            "source": "ServerA",
            "destination": "GhostServer",
            "latency": 10.0,
        })
        self.assertEqual(status, 400)
        self.assertIn("GhostServer", data["error"])

    def test_add_edge_invalid_latency(self):
        self.client.request("POST", "/nodes", {"name": "ServerA"})
        self.client.request("POST", "/nodes", {"name": "ServerB"})

        status, _ = self.client.request("POST", "/edges", {
            "source": "ServerA",
            "destination": "ServerB",
            "latency": -2.0,
        })
        self.assertEqual(status, 400)

        status, _ = self.client.request("POST", "/edges", {
            "source": "ServerA",
            "destination": "ServerB",
            "latency": 0,
        })
        self.assertEqual(status, 400)

    def test_add_duplicate_edge(self):
        self.client.request("POST", "/nodes", {"name": "ServerA"})
        self.client.request("POST", "/nodes", {"name": "ServerB"})

        self.client.request("POST", "/edges", {"source": "ServerA", "destination": "ServerB", "latency": 12.5})
        status, data = self.client.request("POST", "/edges", {"source": "ServerA", "destination": "ServerB", "latency": 15.0})
        self.assertEqual(status, 400)
        self.assertIn("already exists", data["error"])

    # Shortest Route
    def test_shortest_route(self):
        for name in ["ServerA", "ServerB", "ServerC", "ServerD"]:
            self.client.request("POST", "/nodes", {"name": name})

        self.client.request("POST", "/edges", {"source": "ServerA", "destination": "ServerB", "latency": 12.5})
        self.client.request("POST", "/edges", {"source": "ServerB", "destination": "ServerD", "latency": 10.9})
        self.client.request("POST", "/edges", {"source": "ServerA", "destination": "ServerC", "latency": 20.0})
        self.client.request("POST", "/edges", {"source": "ServerC", "destination": "ServerD", "latency": 15.0})

        status, data = self.client.request("POST", "/routes/shortest", {
            "source": "ServerA",
            "destination": "ServerD",
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["total_latency"], 23.4)
        self.assertEqual(data["path"], ["ServerA", "ServerB", "ServerD"])

    def test_shortest_route_no_path(self):
        self.client.request("POST", "/nodes", {"name": "ServerA"})
        self.client.request("POST", "/nodes", {"name": "ServerD"})

        status, data = self.client.request("POST", "/routes/shortest", {
            "source": "ServerA",
            "destination": "ServerD",
        })
        self.assertEqual(status, 404)
        self.assertEqual(data["error"], "No path exists between ServerA and ServerD")

    # History
    def test_route_history(self):
        for name in ["ServerA", "ServerB", "ServerD"]:
            self.client.request("POST", "/nodes", {"name": name})

        self.client.request("POST", "/edges", {"source": "ServerA", "destination": "ServerB", "latency": 12.5})
        self.client.request("POST", "/edges", {"source": "ServerB", "destination": "ServerD", "latency": 10.9})

        self.client.request("POST", "/routes/shortest", {"source": "ServerA", "destination": "ServerD"})

        status, history = self.client.request("GET", "/routes/history")
        self.assertEqual(status, 200)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["source"], "ServerA")
        self.assertEqual(history[0]["destination"], "ServerD")
        self.assertEqual(history[0]["total_latency"], 23.4)
        self.assertEqual(history[0]["path"], ["ServerA", "ServerB", "ServerD"])

    # Deletions
    def test_delete_node_cascade(self):
        self.client.request("POST", "/nodes", {"name": "ServerA"})
        _, b = self.client.request("POST", "/nodes", {"name": "ServerB"})
        self.client.request("POST", "/edges", {"source": "ServerA", "destination": "ServerB", "latency": 10.0})

        status, _ = self.client.request("DELETE", f"/nodes/{b['id']}")
        self.assertEqual(status, 200)

        _, edges = self.client.request("GET", "/edges")
        self.assertEqual(len(edges), 0)


if __name__ == "__main__":
    unittest.main()
