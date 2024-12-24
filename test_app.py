from app import create_app


def test_version():
    """Test the version endpoint using Flask test client."""
    app = create_app("testing")

    with app.test_client() as client:
        response = client.get("/version")
        assert response.status_code == 200
        assert response.json == {"version": app.config["APP_VERSION"]}


def test_temperature():
    """Test the temperature endpoint using Flask test client."""
    app = create_app("testing")

    with app.test_client() as client:
        response = client.get("/temperature")
        assert response.status_code == 200
        assert "temperature" in response.json
        assert "status" in response.json
        assert response.json["status"] in ["Too Cold", "Good", "Too Hot"]
