from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_dockerfile_supports_base_image_and_optional_extra() -> None:
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG BASE_IMAGE=python:3.11-slim" in dockerfile
    assert "FROM ${BASE_IMAGE}" in dockerfile
    assert "ARG PIPEWORKS_EXTRAS=" in dockerfile
    assert '".[${PIPEWORKS_EXTRAS}]"' in dockerfile


def test_compose_exposes_deployment_build_contract() -> None:
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "PIPEWORKS_BASE_IMAGE" in compose
    assert "PIPEWORKS_EXTRAS" in compose
    assert "start_period" in compose
