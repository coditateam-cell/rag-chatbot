# Feature: rag-chatbot-application, Smoke Test: Docker health checks
# Validates: Requirements 8.5, 8.6, 8.7

import subprocess
import json
import time
import pytest

def test_docker_services_health() -> None:
    """Smoke test to verify all Docker services are running and healthy (Req 8.5, 8.6, 8.7)."""
    # Wait up to 60 seconds for services to report healthy
    timeout = 60.0
    start_time = time.time()
    
    services_to_check = {"qdrant", "minio", "postgres", "backend"}
    
    while time.time() - start_time < timeout:
        try:
            # Run docker compose ps to list containers
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse output
            output = result.stdout.strip()
            if not output:
                time.sleep(2)
                continue
                
            containers = []
            try:
                # Try loading as a JSON array
                containers = json.loads(output)
                if not isinstance(containers, list):
                    containers = [containers]
            except json.JSONDecodeError:
                # Try parsing line-by-line (some docker compose versions print line-delimited JSON)
                for line in output.splitlines():
                    if line.strip():
                        containers.append(json.loads(line))
            
            # Map service name to its health status
            healthy_services = set()
            for container in containers:
                service_name = container.get("Service") or container.get("Name")
                if service_name:
                    # Normalize service name (e.g. backend-1 -> backend)
                    service_name = service_name.split("-")[0].split(".")[0]
                
                status = container.get("State") or container.get("Status") or ""
                health = container.get("Health") or ""
                
                is_running = status.lower() == "running"
                # A container is healthy if its health status says healthy, or if no health is reported
                is_healthy = "healthy" in health.lower() or not health
                
                if service_name in services_to_check and is_running and is_healthy:
                    healthy_services.add(service_name)
                    
            if services_to_check.issubset(healthy_services):
                # All required services are healthy!
                return
                
        except Exception:
            # Ignore and retry if compose command transiently fails
            pass
            
        time.sleep(2)
        
    # Check if docker is available at all
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
    except Exception:
        pytest.skip("Docker daemon is not running. Skipping Docker smoke test.")
        
    pytest.fail(
        f"Docker services did not report healthy within {timeout} seconds. "
        f"Expected services: {services_to_check}."
    )
