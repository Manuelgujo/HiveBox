import unittest
from app import create_app


class TestApp(unittest.TestCase):
    def setUp(self):
        """Set up test client before each test."""
        app = create_app("testing")
        self.app = app.test_client()

    def test_version(self):
        """Test version endpoint."""
        response = self.app.get("/version")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"version": "v0.0.1"})

    def test_metrics(self):
        """Test metrics endpoint."""
        response = self.app.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("temperature", response.data.decode())

    def test_temperature(self):
        """Test temperature endpoint."""
        response = self.app.get("/temperature")
        self.assertEqual(response.status_code, 200)
        self.assertIn("temperature", response.json)
        self.assertIn("status", response.json)


if __name__ == "__main__":
    unittest.main()
