import os
import secrets
os.environ["DATABASE_URL"] = "sqlite:///./test_assetly.db"
os.environ["ASSETLY_TESTING"] = "1"
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_dashboard_and_catalog():
    assert client.get("/").status_code == 200
    response = client.get("/assets")
    assert response.status_code == 200
    assert "Dell Inspiron" in response.text

def test_api_and_pages():
    assert client.get("/api/dashboard").json()["asset_count"] >= 3
    for path in ("/consumables", "/lending", "/reports", "/query-lab"):
        assert client.get(path).status_code == 200

def test_search_and_filter():
    response = client.get("/assets?q=Inspiron")
    assert response.status_code == 200
    assert "Dell Inspiron" in response.text
    
    response = client.get("/consumables?q=biscuits")
    assert response.status_code == 200
    assert "Oat biscuits" in response.text

def test_qr_generator():
    response = client.get("/qr/1.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in response.text

def test_query_lab_and_custom_sql():
    # Catalog query
    response = client.get("/api/query-lab?query=asset_overview")
    assert response.status_code == 200
    data = response.json()
    assert "rows" in data
    assert "columns" in data
    assert isinstance(data["rows"], list)

    # Safe custom query
    response = client.post("/api/query-lab/custom", json={"sql": "SELECT 1 AS num, 'test' AS label"})
    assert response.status_code == 200
    assert response.json()["rows"][0]["num"] == 1

    # Mutation query blocked
    response = client.post("/api/query-lab/custom", json={"sql": "DROP TABLE users"})
    assert response.status_code == 400

def test_sync_outbox():
    cid = f"test-{secrets.token_hex(6)}"
    response = client.post("/api/sync", json={"operations":[{"operation":"UPSERT","entity":"asset","id":99,"client_id":cid}]})
    assert response.json()["processed"] == 1

def test_insights_and_category_exclusion():
    # Full insights
    res_all = client.get("/api/insights?mode=monthwise")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert "monthly_data" in data_all
    assert len(data_all["monthly_data"]) >= 3
    assert "sql_query" in data_all
    total_val_all = data_all["summary"]["total_valuation"]

    # Exclude Electronics
    res_ex = client.get("/api/insights?mode=total&exclude=Electronics")
    assert res_ex.status_code == 200
    data_ex = res_ex.json()
    assert "category_data" in data_ex
    cat_names = [c["category"] for c in data_ex["category_data"]]
    assert "Electronics" not in cat_names
    assert "c.name NOT IN ('Electronics')" in data_ex["sql_query"]
    # Total valuation without Electronics is significantly lower (demonstrating unskewing)
    assert data_ex["summary"]["total_valuation"] < total_val_all

def test_snack_recommendations():
    response = client.get("/consumables")
    assert response.status_code == 200
    assert "RESTOCK RECOMMENDATIONS" in response.text
    assert "Oat biscuits" in response.text


def test_aiven_url_and_vercel_entrypoint():
    from app.main import prepare_db_url_and_args
    from api.index import app as vercel_app

    assert vercel_app is app
    aiven_uri = "mysql://avnadmin:AVNS_secret@mysql-demo.a.aivencloud.com:21450/defaultdb?ssl-mode=REQUIRED"
    normalized_url, connect_args = prepare_db_url_and_args(aiven_uri)
    assert normalized_url == "mysql+pymysql://avnadmin:AVNS_secret@mysql-demo.a.aivencloud.com:21450/defaultdb"
    assert "ssl-mode" not in normalized_url
    assert "ssl" in connect_args


