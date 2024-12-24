from datetime import datetime, timedelta, UTC
from statistics import mean
from flask import Flask, jsonify, Response, request  # Added request
import requests
from config import config
import os
from prometheus_client import generate_latest, Counter, Histogram, Info
import time


# Define Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency in seconds", ["endpoint"]
)

TEMPERATURE_GAUGE = Histogram("temperature_celsius", "Current temperature in Celsius")

APP_INFO = Info("flask_app_info", "Information about the Flask application")


def create_app(config_name=None):
    """Application factory function."""
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    flask_app = Flask(__name__)  # Renamed from app to flask_app
    flask_app.config.from_object(config[config_name])

    # Set basic app info for Prometheus
    APP_INFO.info(
        {"version": flask_app.config["APP_VERSION"], "environment": config_name}
    )

    def get_box_data(box_id):
        """Fetch data for a specific senseBox."""
        url = f"{flask_app.config['OPENSENSEMAP_BASE_URL']}/boxes/{box_id}"
        response = requests.get(url, timeout=10)
        return response.json() if response.status_code == 200 else None

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
        if temp <= 36:  # Changed from elif to if
            return "Good"
        return "Too Hot"  # Removed else

    @flask_app.before_request
    def before_request():
        """Store the start time for the request."""
        flask_app.before_request_time = time.time()

    @flask_app.after_request
    def after_request(response):
        """Update metrics after each request."""
        request_latency = time.time() - flask_app.before_request_time
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.endpoint or "unknown",
            status=response.status_code,
        ).inc()

        if request.endpoint:
            REQUEST_LATENCY.labels(endpoint=request.endpoint).observe(request_latency)
        return response

    @flask_app.route("/version")
    def version():
        """Return the API version."""
        return jsonify({"version": flask_app.config["APP_VERSION"]})

    @flask_app.route("/temperature")
    def temperature():
        """Return the average temperature and status from all senseBoxes."""
        temperatures = []

        for box_id in flask_app.config["SENSEBOX_IDS"]:
            if not box_id:
                continue
            data = get_box_data(box_id)
            if data:
                temp = get_temperature_from_box(data)
                if temp is not None:
                    temperatures.append(temp)

        if not temperatures:
            return jsonify({"error": "No temperature data available"}), 404

        avg_temperature = round(mean(temperatures), 2)
        return jsonify(
            {
                "temperature": avg_temperature,
                "status": get_temperature_status(avg_temperature),
            }
        )

    @flask_app.route("/metrics")
    def metrics():
        """Return Prometheus metrics."""
        return Response(generate_latest(), mimetype="text/plain")

    return flask_app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
