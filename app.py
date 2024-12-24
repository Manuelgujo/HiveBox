from datetime import datetime, timedelta, UTC
from statistics import mean
from flask import Flask, jsonify
import requests
from config import config
import os


def get_box_data(box_id):
    """Fetch data for a specific senseBox."""
    url = f"{app.config['OPENSENSEMAP_BASE_URL']}/boxes/{box_id}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        return response.json()
    return None


def get_temperature_from_box(box_data):
    """Extract temperature data from a box's sensor data."""
    if not box_data or "sensors" not in box_data:
        return None

    current_time = datetime.now(UTC)

    for sensor in box_data["sensors"]:
        if (
            (
                "temperature" in sensor["title"].lower()
                or "temperatur" in sensor["title"].lower()
            )
            and "lastMeasurement" in sensor
            and sensor["lastMeasurement"]
        ):
            measurement_time = datetime.fromisoformat(
                sensor["lastMeasurement"]["createdAt"].replace("Z", "+00:00")
            )

            if current_time - measurement_time <= timedelta(hours=1):
                try:
                    return float(sensor["lastMeasurement"]["value"])
                except (ValueError, TypeError):
                    continue

    return None


def get_temperature_status(temp):
    """Determine temperature status based on value."""
    if temp < 10:
        return "Too Cold"
    elif temp <= 36:
        return "Good"
    else:
        return "Too Hot"


def create_app(config_name=None):
    """Application factory function."""
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    @app.route("/version")
    def version():
        """Return the API version."""
        return jsonify({"version": app.config["APP_VERSION"]})

    @app.route("/temperature")
    def temperature():
        """Return the average temperature and status from all senseBoxes."""
        temperatures = []

        for box_id in app.config["SENSEBOX_IDS"]:
            if not box_id:  # Skip empty strings
                continue
            data = get_box_data(box_id)
            if data:
                temp = get_temperature_from_box(data)
                if temp is not None:
                    temperatures.append(temp)

        if not temperatures:
            return jsonify({"error": "No temperature data available"}), 404

        avg_temperature = round(mean(temperatures), 2)
        status = get_temperature_status(avg_temperature)

        return jsonify({"temperature": avg_temperature, "status": status})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
