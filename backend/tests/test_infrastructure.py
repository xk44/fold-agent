"""Tests for infrastructure stubs — GPU worker, encryption, Celery, container scanning."""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# GPU Worker
# ---------------------------------------------------------------------------

from backend.app.gpu_worker import (
    DEFAULT_GPU_PROFILES,
    GPUWorkerConfig,
    check_gpu_availability,
    get_worker_profile,
)


class TestGPUProfiles:
    def test_known_backends_present(self):
        for backend in ("colabfold", "alphafold2_local", "alphafold3_local", "mock"):
            assert backend in DEFAULT_GPU_PROFILES

    def test_colabfold_profile(self):
        p = DEFAULT_GPU_PROFILES["colabfold"]
        assert p.gpu_required is True
        assert p.gpu_type == "nvidia"
        assert p.min_vram_gb == 8

    def test_alphafold2_profile(self):
        p = DEFAULT_GPU_PROFILES["alphafold2_local"]
        assert p.gpu_required is True
        assert p.gpu_type == "nvidia"
        assert p.min_vram_gb == 16

    def test_alphafold3_profile(self):
        p = DEFAULT_GPU_PROFILES["alphafold3_local"]
        assert p.gpu_required is True
        assert p.gpu_type == "nvidia"
        assert p.min_vram_gb == 24

    def test_mock_profile_no_gpu(self):
        p = DEFAULT_GPU_PROFILES["mock"]
        assert p.gpu_required is False
        assert p.min_vram_gb == 0

    def test_get_worker_profile_found(self):
        p = get_worker_profile("colabfold")
        assert isinstance(p, GPUWorkerConfig)
        assert p.gpu_type == "nvidia"

    def test_get_worker_profile_missing(self):
        assert get_worker_profile("nonexistent_backend") is None


class TestGPUAvailability:
    def test_returns_expected_keys(self):
        result = check_gpu_availability()
        assert "available" in result
        assert "gpu_count" in result
        assert "driver_version" in result

    def test_available_is_bool(self):
        result = check_gpu_availability()
        assert isinstance(result["available"], bool)

    def test_gpu_count_is_int(self):
        result = check_gpu_availability()
        assert isinstance(result["gpu_count"], int)
        assert result["gpu_count"] >= 0

    def test_driver_version_type(self):
        result = check_gpu_availability()
        assert result["driver_version"] is None or isinstance(result["driver_version"], str)


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------

from backend.app.encryption import (
    check_encryption_status,
    decrypt_data,
    derive_key,
    encrypt_data,
)


class TestEncryptionRoundtrip:
    def test_encrypt_decrypt_roundtrip(self):
        key = b"0123456789abcdef0123456789abcdef"  # 32 bytes
        plaintext = b"foldagent test payload"
        ciphertext = encrypt_data(plaintext, key)
        assert ciphertext != plaintext
        recovered = decrypt_data(ciphertext, key)
        assert recovered == plaintext

    def test_encrypt_produces_different_bytes(self):
        key = b"0123456789abcdef0123456789abcdef"
        plaintext = b"hello"
        ct = encrypt_data(plaintext, key)
        assert ct != plaintext

    def test_derive_key_returns_bytes(self):
        salt = os.urandom(16)
        key = derive_key("password", salt)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_derive_key_deterministic(self):
        salt = b"\x00" * 16
        k1 = derive_key("password", salt)
        k2 = derive_key("password", salt)
        assert k1 == k2

    def test_derive_key_salt_sensitive(self):
        k1 = derive_key("password", b"\x00" * 16)
        k2 = derive_key("password", b"\x01" * 16)
        assert k1 != k2


class TestEncryptionStatus:
    def test_returns_expected_keys(self):
        status = check_encryption_status()
        for key in ("configured", "algorithm", "key_derivation", "crypto_library_available", "key_set"):
            assert key in status

    def test_configured_is_bool(self):
        status = check_encryption_status()
        assert isinstance(status["configured"], bool)

    def test_crypto_library_available_is_bool(self):
        status = check_encryption_status()
        assert isinstance(status["crypto_library_available"], bool)

    def test_key_derivation_value(self):
        status = check_encryption_status()
        assert "PBKDF2" in status["key_derivation"]


# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------

from backend.app.celery_config import (
    CELERY_TASK_REGISTRY,
    CeleryConfig,
    check_celery_status,
    get_celery_config,
)


class TestCeleryConfig:
    def test_returns_celery_config(self):
        cfg = get_celery_config()
        assert isinstance(cfg, CeleryConfig)

    def test_default_broker_contains_redis(self):
        cfg = get_celery_config()
        assert "redis" in cfg.broker_url or cfg.broker_url.startswith("redis")

    def test_task_serializer_is_json(self):
        cfg = get_celery_config()
        assert cfg.task_serializer == "json"

    def test_accept_content_is_list(self):
        cfg = get_celery_config()
        assert isinstance(cfg.accept_content, list)
        assert "json" in cfg.accept_content


class TestCeleryTaskRegistry:
    def test_expected_tasks_present(self):
        for task in ("run_pipeline", "run_alphafold", "generate_report", "export_data", "cleanup_expired"):
            assert task in CELERY_TASK_REGISTRY

    def test_descriptions_are_strings(self):
        for name, desc in CELERY_TASK_REGISTRY.items():
            assert isinstance(desc, str) and len(desc) > 0


class TestCeleryStatus:
    def test_returns_expected_keys(self):
        status = check_celery_status()
        for key in ("celery_importable", "broker_url", "result_backend", "broker_reachable"):
            assert key in status

    def test_celery_importable_is_bool(self):
        status = check_celery_status()
        assert isinstance(status["celery_importable"], bool)


# ---------------------------------------------------------------------------
# Container scanning
# ---------------------------------------------------------------------------

from backend.app.container_scanning import (
    DEFAULT_SCAN_CONFIG,
    ContainerScanConfig,
    build_scan_command,
    check_scanner_available,
    parse_scan_results,
)


class TestContainerScanCommandGeneration:
    def test_trivy_command_contains_image(self):
        cmd = build_scan_command("myimage:latest", DEFAULT_SCAN_CONFIG)
        assert "myimage:latest" in cmd
        assert "trivy" in cmd

    def test_trivy_command_contains_severity(self):
        cmd = build_scan_command("myimage:latest", DEFAULT_SCAN_CONFIG)
        assert "CRITICAL" in cmd

    def test_grype_command(self):
        cfg = ContainerScanConfig(scanner="grype", fail_on_severity="HIGH", ignore_unfixed=False)
        cmd = build_scan_command("myimage:latest", cfg)
        assert "grype" in cmd
        assert "myimage:latest" in cmd

    def test_none_scanner(self):
        cfg = ContainerScanConfig(scanner="none", fail_on_severity="CRITICAL", ignore_unfixed=False)
        cmd = build_scan_command("myimage:latest", cfg)
        assert "myimage:latest" in cmd

    def test_ignore_unfixed_trivy(self):
        cfg = ContainerScanConfig(scanner="trivy", fail_on_severity="HIGH", ignore_unfixed=True)
        cmd = build_scan_command("img:tag", cfg)
        assert "--ignore-unfixed" in cmd

    def test_parse_scan_results_stub(self):
        result = parse_scan_results("CRITICAL: CVE-2023-0001\nHIGH: CVE-2023-0002")
        assert "vulnerability_count" in result
        assert "raw_output" in result
        assert isinstance(result["vulnerability_count"], int)


class TestScannerAvailability:
    def test_returns_expected_keys(self):
        result = check_scanner_available()
        for key in ("trivy_available", "grype_available", "any_available", "available_scanners"):
            assert key in result

    def test_available_scanners_is_list(self):
        result = check_scanner_available()
        assert isinstance(result["available_scanners"], list)

    def test_any_available_consistent(self):
        result = check_scanner_available()
        expected = result["trivy_available"] or result["grype_available"]
        assert result["any_available"] == expected


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


class TestInfrastructureAPI:
    def test_gpu_profiles_endpoint(self, client):
        r = client.get("/infrastructure/gpu-profiles")
        assert r.status_code == 200
        data = r.json()
        assert "profiles" in data
        assert "colabfold" in data["profiles"]
        assert "mock" in data["profiles"]

    def test_gpu_status_endpoint(self, client):
        r = client.get("/infrastructure/gpu-status")
        assert r.status_code == 200
        data = r.json()
        assert "available" in data
        assert "gpu_count" in data

    def test_encryption_status_endpoint(self, client):
        r = client.get("/infrastructure/encryption-status")
        assert r.status_code == 200
        data = r.json()
        assert "configured" in data
        assert "algorithm" in data

    def test_celery_status_endpoint(self, client):
        r = client.get("/infrastructure/celery-status")
        assert r.status_code == 200
        data = r.json()
        assert "celery_importable" in data

    def test_celery_tasks_endpoint(self, client):
        r = client.get("/infrastructure/celery-tasks")
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data
        assert "run_pipeline" in data["tasks"]

    def test_container_scan_status_endpoint(self, client):
        r = client.get("/infrastructure/container-scan/status")
        assert r.status_code == 200
        data = r.json()
        assert "trivy_available" in data

    def test_container_scan_build_command_trivy(self, client):
        r = client.post(
            "/infrastructure/container-scan/build-command",
            json={"image": "nginx:latest", "scanner": "trivy", "fail_on_severity": "CRITICAL"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "command" in data
        assert "nginx:latest" in data["command"]
        assert data["scanner"] == "trivy"

    def test_container_scan_build_command_grype(self, client):
        r = client.post(
            "/infrastructure/container-scan/build-command",
            json={"image": "alpine:3.18", "scanner": "grype", "fail_on_severity": "HIGH"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "grype" in data["command"]
        assert "alpine:3.18" in data["command"]
