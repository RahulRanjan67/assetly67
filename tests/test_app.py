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
    assert client.get("/api/index").status_code == 200
    assert client.get("/api/index/assets").status_code == 200
    aiven_uri = "mysql://avnadmin:AVNS_secret@mysql-demo.a.aivencloud.com:21450/defaultdb?ssl-mode=REQUIRED"
    normalized_url, connect_args = prepare_db_url_and_args(aiven_uri)
    assert normalized_url == "mysql+pymysql://avnadmin:AVNS_secret@mysql-demo.a.aivencloud.com:21450/defaultdb"
    assert "ssl-mode" not in normalized_url
    assert "ssl" in connect_args

def test_nickname_and_like_search():
    # Nickname search on assets
    res = client.get("/assets?q=Laptop")
    assert res.status_code == 200
    assert "Dell Inspiron" in res.text
    assert "Work Laptop" in res.text

    # Edit nickname
    res_nick = client.post("/assets/1/nickname", data={"nickname": "My Test Nickname"}, follow_redirects=False)
    assert res_nick.status_code == 303
    res_detail = client.get("/assets/1")
    assert "My Test Nickname" in res_detail.text

    # LIKE search in Query Lab catalog
    res_ql = client.get("/api/query-lab?query=like_search")
    assert res_ql.status_code == 200
    assert "rows" in res_ql.json()

def test_grocery_shopping_list():
    # Live stock check
    res_check = client.get("/api/grocery-stock-check?q=tea")
    assert res_check.status_code == 200
    data_check = res_check.json()
    assert data_check["best_match"]["in_stock"] is True

    # Initial assets count
    initial_asset_count = client.get("/api/dashboard").json()["asset_count"]

    # Add item to grocery planning list
    res_add = client.post("/api/grocery-list", json={"name": "Organic Honey", "quantity": "2", "unit": "bottle", "notes": "Local bee farm"})
    assert res_add.status_code == 200
    item = res_add.json()
    assert item["name"] == "Organic Honey"

    # Grocery list is NOT automatically added into My Things (assets)
    after_asset_count = client.get("/api/dashboard").json()["asset_count"]
    assert after_asset_count == initial_asset_count
    res_things = client.get("/assets?q=Organic+Honey")
    assert "No items found" in res_things.text

    # Toggle grocery item checked
    res_toggle = client.post(f"/api/grocery-list/{item['id']}/toggle")
    assert res_toggle.status_code == 200
    assert res_toggle.json()["checked"] is True

    # Delete grocery item
    res_del = client.delete(f"/api/grocery-list/{item['id']}")
    assert res_del.status_code == 200




