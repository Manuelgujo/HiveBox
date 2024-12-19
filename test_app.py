import os
import requests
from app import app


def test_version():
    """Test the version endpoint directly."""
    response = requests.get("http://localhost:5000/version")
    assert response.status_code == 200
    assert response.json() == {"version": "v0.0.1"}


def test_temperature():
    """Test the temperature endpoint using Flask test client."""
    # Configure test SenseBox IDs
    os.environ["SENSEBOX_IDS"] = (
        "5e6d01eeee48fc001db20a8e,"
        "5c633de5a100840019a290b7,"
        "5c633d60a100840019a26f69"
    )

    with app.test_client() as client:
        response = client.get("/temperature")
        assert response.status_code == 200

        # Check JSON response
        data = response.get_json()
        assert "average_temperature" in data
        assert isinstance(data["average_temperature"], float)
