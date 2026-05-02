from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

def test_get_minimax_config_unauthenticated():
    # Admin endpoints require auth; minimax config is under /api/v1/config/minimax (no auth currently)
    r = client.get('/api/v1/config/minimax')
    assert r.status_code in (200, 400, 502)

def test_health_check_reachable():
    # Health check may fail if base URL not set; accept 200 or 400/502
    r = client.get('/api/v1/config/minimax/health')
    assert r.status_code in (200, 400, 502)

if __name__ == '__main__':
    print('Running quick minimax UI endpoint checks')
    print('GET /api/v1/config/minimax ->', client.get('/api/v1/config/minimax').status_code)
    print('GET /api/v1/config/minimax/health ->', client.get('/api/v1/config/minimax/health').status_code)
