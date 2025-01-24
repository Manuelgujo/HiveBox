from datetime import datetime, timedelta, UTC
from statistics import mean
import json
import os
import time
from typing import Tuple, Dict, Optional
from io import BytesIO
from flask import Flask, jsonify, Response
import requests
from config import config
from prometheus_client import generate_latest, Counter, Histogram, Gauge
import redis
from minio import Minio
from apscheduler.schedulers.background import BackgroundScheduler

# Define Prometheus metrics
REQUEST_COUNT = Counter(
    "hivebox_http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "hivebox_request_duration_seconds", "HTTP request latency in seconds", ["endpoint"]
)
TEMPERATURE_GAUGE = Gauge(
    "hivebox_temperature_celsius", "Current temperature readings", ["box_id"]
)
SENSEBOX_UP = Gauge("hivebox_sensebox_up", "SenseBox availability status", ["box_id"])
CACHE_AGE = Gauge("hivebox_cache_age_seconds", "Age of the cache in seconds")


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    flask_app = Flask(__name__)
    flask_app.config.from_object(config[config_name])

    # Initialize Redis client
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))

    # Initialize MinIO client
    minio_host = os.getenv("MINIO_HOST", "localhost:9000")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    bucket_name = os.getenv("MINIO_BUCKET", "hivebox")

    try:
        redis_client = redis.Redis(
            host=redis_host, port=redis_port, decode_responses=True
        )

        minio_client = Minio(
            minio_host,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=False,
        )

        # Initialize MinIO bucket with retries
        try_count = 0
        max_retries = 3
        while try_count < max_retries:
            try:
                if not minio_client.bucket_exists(bucket_name):
                    minio_client.make_bucket(bucket_name)
                    flask_app.logger.info(f"Successfully created bucket: {bucket_name}")
                else:
                    flask_app.logger.info(f"Bucket already exists: {bucket_name}")
                break
            except Exception as e:
                try_count += 1
                flask_app.logger.warning(
                    f"Attempt {try_count} to create/check bucket failed: {e}"
                )
                if try_count == max_retries:
                    raise
                time.sleep(2)  # Wait 2 seconds before retrying

    except Exception as e:
        flask_app.logger.error(f"Failed to initialize services: {e}")
        # Don't crash, we'll handle connection issues in the endpoints

    def get_temperature_from_box(box_data: dict) -> float | None:
        """
        Extract temperature data from a SenseBox data dictionary.

        Args:
            box_data (dict): The JSON response from OpenSenseMap API for a box

        Returns:
            float | None: Temperature value if found, None otherwise
        """
        try:
            # Find the temperature sensor
            for sensor in box_data.get("sensors", []):
                if any(
                    keyword in sensor.get("title", "").lower()
                    for keyword in ["temp", "temperature"]
                ):
                    # Get the latest measurement
                    if sensor.get("lastMeasurement", {}).get("value"):
                        return float(sensor["lastMeasurement"]["value"])
            return None
        except (ValueError, TypeError, KeyError) as e:
            flask_app.logger.error(f"Error extracting temperature: {e}")
            return None

    def get_box_data(box_id: str) -> Optional[Dict]:
        try:
            url = f"{flask_app.config['OPENSENSEMAP_BASE_URL']}/boxes/{box_id}"
            flask_app.logger.info(f"Fetching data from: {url}")
            response = requests.get(url, timeout=2)
            flask_app.logger.info(f"Response status: {response.status_code}")
            if response.status_code == 200:
                SENSEBOX_UP.labels(box_id=box_id).set(1)
                data = response.json()
                flask_app.logger.info(
                    f"Data received for box {box_id}: {json.dumps(data)[:200]}..."
                )  # Log first 200 chars
                return data
            SENSEBOX_UP.labels(box_id=box_id).set(0)
            flask_app.logger.error(
                f"Failed to get data for box {box_id}. Status: {response.status_code}"
            )
            return None
        except Exception as e:
            SENSEBOX_UP.labels(box_id=box_id).set(0)
            flask_app.logger.error(f"Exception getting box {box_id} data: {str(e)}")
            return None

    def store_data_to_minio() -> None:
        try:
            data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "temperatures": {},
                "average_temperature": None,
            }

            flask_app.logger.info(f"SenseBox IDs: {flask_app.config['SENSEBOX_IDS']}")
            temperatures = []
            for box_id in flask_app.config["SENSEBOX_IDS"]:
                if not box_id:  # Skip empty box IDs
                    continue
                flask_app.logger.info(f"Processing box ID: {box_id}")
                box_data = get_box_data(box_id)
                if box_data:
                    temp = get_temperature_from_box(box_data)
                    if temp is not None:
                        data["temperatures"][box_id] = temp
                        temperatures.append(temp)
                        TEMPERATURE_GAUGE.labels(box_id=box_id).set(temp)

            if temperatures:
                data["average_temperature"] = mean(temperatures)

            json_data = json.dumps(data)
            data_bytes = json_data.encode("utf-8")
            data_stream = BytesIO(data_bytes)

            minio_client.put_object(
                bucket_name,
                f"temperatures/{data['timestamp']}.json",
                data_stream,
                len(data_bytes),
                content_type="application/json",
            )

            redis_client.set("temperature_data", json_data)
            redis_client.set("last_temperature_update", data["timestamp"])

        except Exception as e:
            flask_app.logger.error(f"Failed to store data: {e}")

    def check_sensebox_health() -> Tuple[int, int]:
        try:
            cached_health = redis_client.get("sensebox_health")
            if cached_health:
                health_data = json.loads(cached_health)
                cache_time = datetime.fromisoformat(health_data["timestamp"])
                if datetime.now(UTC) - cache_time < timedelta(minutes=1):
                    return health_data["accessible"], health_data["total"]
        except Exception:
            pass

        accessible_boxes = 0
        total_boxes = len([bid for bid in flask_app.config["SENSEBOX_IDS"] if bid])

        if total_boxes == 0:
            return 0, 0

        for box_id in flask_app.config["SENSEBOX_IDS"]:
            if not box_id:  # Skip empty box IDs
                continue
            if get_box_data(box_id) is not None:
                accessible_boxes += 1

        try:
            health_data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "accessible": accessible_boxes,
                "total": total_boxes,
            }
            redis_client.setex("sensebox_health", 60, json.dumps(health_data))
        except Exception:
            pass

        return accessible_boxes, total_boxes

    def check_cache_freshness() -> bool:
        try:
            last_update = redis_client.get("last_temperature_update")
            if last_update is None:
                return False

            last_update_time = datetime.fromisoformat(last_update)
            return (datetime.now(UTC) - last_update_time) < timedelta(minutes=5)
        except Exception:
            return False

    @flask_app.route("/store")
    def store():
        try:
            store_data_to_minio()
            return jsonify({"status": "success", "message": "Data stored successfully"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @flask_app.route("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype="text/plain")

    @flask_app.route("/readyz")
    def readyz():
        try:
            accessible_boxes, total_boxes = check_sensebox_health()
            cache_is_fresh = check_cache_freshness()

            min_required = (total_boxes // 2) + 1

            response = {
                "status": "ready",
                "details": {
                    "accessible_boxes": accessible_boxes,
                    "total_boxes": total_boxes,
                    "minimum_required": min_required,
                    "cache_fresh": cache_is_fresh,
                },
            }

            if accessible_boxes < min_required and not cache_is_fresh:
                response["status"] = "not ready"
                return response, 503

            return response, 200
        except Exception as e:
            flask_app.logger.error(f"Health check failed: {e}")
            return {"status": "error", "error": str(e)}, 500

    @flask_app.route("/version")
    def version():
        return jsonify({"version": flask_app.config["APP_VERSION"]})

    @flask_app.route("/temperature")
    def temperature():
        try:
            data = redis_client.get("temperature_data")
            if data:
                return Response(data, mimetype="application/json")
            return jsonify({"error": "No temperature data available"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Set up scheduler for periodic data storage
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(store_data_to_minio, "interval", minutes=5)
        scheduler.start()
    except Exception as e:
        flask_app.logger.error(f"Failed to start scheduler: {e}")

    return flask_app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
