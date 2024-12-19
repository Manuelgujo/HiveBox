from app import app


def test_version():
    """Test the version endpoint using Flask test client."""
    with app.test_client() as client:
        response = client.get("/version")
        assert response.status_code == 200
        assert response.json == {"version": "v0.0.1"}


def test_temperature():
    """Test the temperature endpoint using Flask test client."""
    with app.test_client() as client:
        response = client.get("/temperature")
        assert response.status_code == 200
        assert "average_temperature" in response.json
