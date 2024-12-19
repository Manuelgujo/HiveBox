from datetime import datetime, timedelta, UTC
from statistics import mean
from flask import Flask, jsonify
import requests

app = Flask(__name__)

# Configuration
SENSEBOX_IDS = [
    "5e6d01eeee48fc001db20a8e",
    "5c633de5a100840019a290b7",
    "5c633d60a100840019a26f69",
]
OPENSENSEMAP_BASE_URL = "https://api.opensensemap.org"
VERSION = "v0.0.1"


def get_box_data(box_id):
    """
    Fetch data for a specific senseBox including all its sensors and latest measurements.
    """
    url = f"{OPENSENSEMAP_BASE_URL}/boxes/{box_id}"
    response = requests.get(url, timeout=10)  # Added timeout
    if response.status_code == 200:
        return response.json()
    return None


def get_temperature_from_box(box_data):
    """
    Extract temperature data from a box's sensor data.
    Returns the most recent temperature reading if available and not older than 1 hour.
    """
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


@app.route("/version")
def version():
    """Return the API version."""
    return jsonify({"version": VERSION})


@app.route("/temperature")
def temperature():
    """Return the average temperature from all senseBoxes."""
    temperatures = []

    for box_id in SENSEBOX_IDS:
        data = get_box_data(box_id)
        if data:
            temp = get_temperature_from_box(data)
            if temp is not None:
                temperatures.append(temp)

    if not temperatures:
        return jsonify({"error": "No temperature data available"}), 404

    avg_temperature = round(mean(temperatures), 2)
    return jsonify({"temperature": avg_temperature})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
