from urllib.parse import quote


def test_list_trajets_default_pagination(client):
    response = client.get("/trajets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 25
    assert payload["total"] == 10
    assert payload["total_pages"] == 1
    assert len(payload["items"]) == 10

    first_item = payload["items"][0]
    assert first_item["id"]
    assert first_item["origin_stop_name"]
    assert first_item["destination_stop_name"]
    assert isinstance(first_item["distance_km"], float)


def test_list_trajets_filters_by_country_and_train_type(client):
    response = client.get(
        "/trajets",
        params={"country": "FR", "type_train": "electric", "page_size": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 3
    assert {item["country"] for item in payload["items"]} == {"FR"}
    assert {item["type_train"] for item in payload["items"]} == {"electric"}


def test_list_trajets_filters_by_origin_and_destination_text(client):
    response = client.get(
        "/trajets",
        params={"origin": "lyon", "destination": "dijon", "page_size": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    for item in payload["items"]:
        assert "lyon" in item["origin_stop_name"].lower()
        assert "dijon" in item["destination_stop_name"].lower()


def test_list_trajets_rejects_inconsistent_distance_bounds(client):
    response = client.get(
        "/trajets",
        params={"min_distance_km": 500, "max_distance_km": 100},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "HTTP_422"
    assert "min_distance_km" in error["message"]
    assert error["path"] == "/trajets"


def test_validation_errors_use_homogeneous_payload(client):
    response = client.get("/trajets", params={"page": 0})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Paramètres ou payload invalides"
    assert error["status_code"] == 422
    assert error["path"] == "/trajets"
    assert error["details"]


def test_get_trajet_by_stable_id_matches_list_item(client):
    list_response = client.get("/trajets", params={"page_size": 1})
    assert list_response.status_code == 200
    first_item = list_response.json()["items"][0]

    detail_response = client.get(f"/trajets/{quote(first_item['id'], safe='')}")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == first_item["id"]
    assert detail["route_id"] == first_item["route_id"]
    assert detail["origin_stop_name"] == first_item["origin_stop_name"]
    assert detail["destination_stop_name"] == first_item["destination_stop_name"]


def test_get_trajet_returns_404_for_unknown_id(client):
    response = client.get("/trajets/unknown-trip-id")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "HTTP_404"
    assert "introuvable" in error["message"]
    assert error["path"] == "/trajets/unknown-trip-id"


def test_stats_volumes_exposes_global_and_grouped_counts(client):
    response = client.get("/stats/volumes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_trajets"] == 10
    assert payload["total_countries"] == len(payload["by_country"])
    assert payload["total_routes"] == 10
    assert payload["total_distance_km"] > 0
    assert payload["total_kg_co2_emis"] > 0
    assert {item["key"] for item in payload["by_country"]} == {"DE", "FR"}
    assert {item["key"] for item in payload["by_type_train"]} == {"diesel", "electric"}
    assert sum(item["total_trajets"] for item in payload["by_country"]) == payload["total_trajets"]


def test_health_includes_dataset_models_and_timestamp(client):
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded", "unavailable"}
    assert payload["timestamp"].endswith("Z")
    assert payload["dataset"]["status"] == "ok"
    assert payload["dataset"]["rows"] == 10
    assert set(payload["models"]) == {"classification_substitution", "regression_co2"}
    assert payload["models"]["regression_co2"]["status"] in {"ok", "unavailable"}


def test_cors_allows_local_frontend_origin(client):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_metrics_exposes_prometheus_text(client):
    client.get("/health")
    client.get("/trajets", params={"page_size": 1})

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# TYPE obrail_http_requests_total counter" in body
    assert 'obrail_http_requests_total{method="GET",path="/health",status="200"}' in body
    assert 'obrail_http_requests_total{method="GET",path="/trajets",status="200"}' in body
    assert "# TYPE obrail_http_request_duration_seconds histogram" in body
    assert 'obrail_dependency_up{dependency="dataset"} 1' in body
    assert "obrail_dataset_rows" in body
