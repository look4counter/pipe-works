import json
from urllib.request import urlopen

from pipeworks import MockSource, ObservabilityServer, Pipeline


def test_observability_server_serves_health_and_metrics() -> None:
    pipeline = Pipeline("http-health").source(MockSource("cam01"))
    pipeline.run()
    server = ObservabilityServer(pipeline).start()

    try:
        base_url = f"http://{server.address[0]}:{server.address[1]}"
        with urlopen(f"{base_url}/health") as response:
            health = json.loads(response.read())
        with urlopen(f"{base_url}/metrics") as response:
            metrics = response.read().decode("utf-8")

        assert health["status"] == "healthy"
        assert health["pipeline_name"] == "http-health"
        assert 'pipeworks_frames_processed{pipeline="http-health"} 1' in metrics
    finally:
        server.stop()
