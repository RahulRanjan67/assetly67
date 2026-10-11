import io
import os
import re
import secrets
import ssl
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import qrcode
import qrcode.image.svg
from fastapi import FastAPI, File, Form, Request, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session, joinedload
from .models import *
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass
base = Path(__file__).parent
static_uploads = base / "static" / "uploads"
uploads = Path("/tmp/uploads") if os.environ.get("VERCEL") else static_uploads
try:
    uploads.mkdir(parents=True, exist_ok=True)
except OSError:
    uploads = Path("/tmp/uploads")
    uploads.mkdir(parents=True, exist_ok=True)


def prepare_db_url_and_args(raw_url: str):
    clean = raw_url.strip().strip('"').strip("'")
    if clean.startswith("mysql://"):
        clean = "mysql+pymysql://" + clean[len("mysql://"):]
    if clean.startswith("sqlite"):
        return clean, {"check_same_thread": False}
    parts = urlsplit(clean)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    filtered_query = []
    ssl_requested = False
    for k, v in query_pairs:
        if k.lower() in ("ssl-mode", "ssl_mode", "ssl"):
            if v.upper() not in ("DISABLED", "FALSE", "0", "NONE"):
                ssl_requested = True
        else:
            filtered_query.append((k, v))
    host = (parts.hostname or "").lower()
    netloc = parts.netloc
    if host in ("127.0.0.1", "localhost") and (parts.username or "") == "assetly_user":
        netloc = netloc.replace("assetly_user", "root", 1)
    if host and host not in ("127.0.0.1", "localhost"):
        ssl_requested = True
    normalized_url = urlunsplit((parts.scheme, netloc, parts.path, urlencode(filtered_query), parts.fragment))
    connect_args = {}
    if ssl_requested:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_ctx
    return normalized_url, connect_args


raw_url = os.environ.get("DATABASE_URL", "")
testing = os.environ.get("ASSETLY_TESTING") == "1"
if not raw_url:
    raise RuntimeError("DATABASE_URL is required; use a MySQL 8.0 SQLAlchemy URL")
url, connect_args = prepare_db_url_and_args(raw_url)
if not url.startswith("mysql+pymysql://") and not testing:
    raise RuntimeError("Assetly runtime requires MySQL 8.0 through DATABASE_URL")
engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, pool_recycle=280)
Base.metadata.create_all(engine)


def ensure_mysql_views(force: bool = False):
    if engine.dialect.name != "mysql":
        return
    schema_path = base.parent / "sql" / "mysql_schema.sql"
    if not schema_path.exists():
        return
    try:
        with engine.connect() as conn:
            if not force:
                existing = {
                    row[0]
                    for row in conn.exec_driver_sql("SHOW FULL TABLES WHERE Table_type = 'VIEW'").fetchall()
                }
                required = {
                    "vw_asset_overview",
                    "vw_asset_tco",
                    "vw_active_loans",
                    "vw_overdue_loans",
                    "vw_consumable_stock",
                }
                if required.issubset(existing):
                    return
            content = schema_path.read_text()
            parts = re.split(r"DELIMITER\s+//", content, flags=re.IGNORECASE)
            regular_part = parts[0]
            procedure_part = parts[1] if len(parts) > 1 else ""
            for stmt in regular_part.split(";"):
                clean_lines = [l for l in stmt.splitlines() if not l.strip().startswith("--")]
                clean_stmt = "\n".join(clean_lines).strip()
                if clean_stmt:
                    conn.exec_driver_sql(clean_stmt)
            if procedure_part:
                proc_body = re.split(r"//\s*DELIMITER\s*;?", procedure_part, flags=re.IGNORECASE)[0].strip()
                if proc_body:
                    try:
                        conn.exec_driver_sql(proc_body)
                    except Exception:
                        pass
            conn.commit()
    except Exception:
        pass


ensure_mysql_views()
app = FastAPI(title="Assetly - Home inventory")


@app.get("/static/uploads/{filename}")
def serve_uploaded_photo(filename: str):
    safe_name = Path(filename).name
    for folder in (uploads, static_uploads):
        candidate = folder / safe_name
        if candidate.is_file():
            return FileResponse(candidate)
    raise HTTPException(404, "Photo not found")


app.mount("/static", StaticFiles(directory=base / "static"), name="static")
templates = Jinja2Templates(directory=base / "templates")
categories = ["Furniture", "Snacks", "Books", "Miscellaneous", "Stationery", "Daily Use", "Kitchen & Grocery", "Documents", "Electronics", "Vehicles", "Clothing"]
category_fields = {"Electronics": ["manufacturer", "model_number", "serial_number", "warranty_end"], "Vehicles": ["manufacturer", "model_number", "serial_number", "registration_number"], "Documents": ["document_number", "issuer", "expiry_date"], "Clothing": ["size", "color"], "Snacks": ["brand", "unit", "expiry_date"], "Kitchen & Grocery": ["brand", "unit", "expiry_date"]}
category_icons = {"Furniture": "🪑", "Snacks": "🍪", "Books": "📚", "Miscellaneous": "🧩", "Stationery": "✏️", "Daily Use": "🧴", "Kitchen & Grocery": "🍳", "Documents": "📄", "Electronics": "💻", "Vehicles": "🚲", "Clothing": "🧥"}
def seed(force: bool = False):
    """Backfill a useful demo dataset without touching user-created records."""
    with Session(engine) as db:
        if not force and (db.scalar(select(func.count(Asset.id))) or 0) >= 30:
            return
        owner = db.scalar(select(User).where(User.email == "aarav@assetly.local"))
        if not owner:
            owner = User(name="Aarav Mehta", email="aarav@assetly.local")
            db.add(owner)
        cats = {}
        for name in categories:
            cats[name] = db.scalar(select(Category).where(Category.name == name))
            if not cats[name]:
                cats[name] = Category(name=name)
                db.add(cats[name])
        locations = ["Bedroom", "Study desk", "Cupboard", "Kitchen", "Garage", "Entry shelf"]
        locs = {}
        for name in locations:
            locs[name] = db.scalar(select(Location).where(Location.name == name))
            if not locs[name]:
                locs[name] = Location(name=name)
                db.add(locs[name])
        people = {}
        for name, contact in [("Maya", "maya@example.com"), ("Rohan", "rohan@example.com"), ("Neha", "neha@example.com")]:
            people[name] = db.scalar(select(Person).where(Person.name == name))
            if not people[name]:
                people[name] = Person(name=name, contact=contact)
                db.add(people[name])
        db.flush()
        examples = {"Furniture": ["Study chair", "Bedside table", "Floor lamp"], "Snacks": ["Snack basket", "Lunch snacks", "Tea tin"], "Books": ["Python cookbook", "The Alchemist", "Math notes"], "Miscellaneous": ["Umbrella", "Backpack", "Board game"], "Stationery": ["Blue pens", "Sketchbook", "Stapler"], "Daily Use": ["Water bottle", "Yoga mat", "Keys tray"], "Kitchen & Grocery": ["Mixer grinder", "Lunch box", "Coffee press"], "Documents": ["Passport folder", "House papers", "Certificates"], "Electronics": ["Dell Inspiron 14", "LG monitor", "Bluetooth speaker"], "Vehicles": ["City bicycle", "Helmet", "Scooter cover"], "Clothing": ["Winter jacket", "Rain coat", "Running shoes"]}
        places = ["Bedroom", "Study desk", "Cupboard", "Kitchen", "Garage", "Entry shelf"]
        
        # Explicit date & valuation distribution across the last 12 months
        # (Recent 0-5 months dense, older items up to 365 days back; Electronics has high value to showcase category skew)
        item_meta = {
            "Dell Inspiron 14": (35, 54990.0, "Dell Official Store"),
            "LG monitor": (75, 14500.0, "Amazon India"),
            "Bluetooth speaker": (120, 2499.0, "Croma Electronics"),
            "Floor lamp": (15, 1650.0, "Pepperfry"),
            "Study chair": (60, 4200.0, "IKEA"),
            "Bedside table": (330, 2100.0, "Urban Ladder"),
            "City bicycle": (140, 8500.0, "Decathlon"),
            "Helmet": (140, 1200.0, "Decathlon"),
            "Scooter cover": (280, 650.0, "AutoWorld"),
            "Coffee press": (18, 1150.0, "Blue Tokai"),
            "Mixer grinder": (100, 3100.0, "Philips Home"),
            "Lunch box": (310, 450.0, "Milton Store"),
            "Python cookbook": (45, 1299.0, "BookStore"),
            "Math notes": (155, 180.0, "University Press"),
            "The Alchemist": (345, 350.0, "Crossword"),
            "Snack basket": (22, 650.0, "FabIndia"),
            "Lunch snacks": (52, 280.0, "HyperMarket"),
            "Tea tin": (110, 320.0, "Tea Estate"),
            "Blue pens": (10, 120.0, "Stationery Hub"),
            "Sketchbook": (70, 380.0, "Art Corner"),
            "Stapler": (360, 195.0, "Stationery Hub"),
            "Water bottle": (25, 550.0, "Sports Fit"),
            "Yoga mat": (135, 890.0, "Decathlon"),
            "Keys tray": (350, 250.0, "Home Centre"),
            "Running shoes": (40, 2800.0, "Puma Store"),
            "Rain coat": (95, 1250.0, "Quechua"),
            "Winter jacket": (270, 3499.0, "Wildcraft"),
            "Umbrella": (85, 450.0, "City Mart"),
            "Backpack": (150, 1850.0, "Wildcraft"),
            "Board game": (325, 999.0, "Toy World"),
            "Passport folder": (200, 350.0, "Leather Works"),
            "Certificates": (300, 0.0, "University"),
            "House papers": (365, 0.0, "Official Registry")
        }

        for cat_name, names in examples.items():
            for i, name in enumerate(names):
                asset = db.scalar(select(Asset).where(Asset.user_id == owner.id, Asset.name == name, Asset.category_id == cats[cat_name].id))
                if not asset:
                    asset = Asset(user=owner, name=name, category=cats[cat_name], location=locs[places[i % len(places)]], status="AVAILABLE", description=f"Handy {cat_name.lower()} item", qr_code=f"ASSET-{1000 + categories.index(cat_name) * 10 + i}")
                    db.add(asset)
                    db.flush()
                meta = item_meta.get(name, (180, 450.0, "Local shop"))
                if not asset.purchases:
                    asset.purchases.append(Purchase(purchase_date=date.today() - timedelta(days=meta[0]), base_price=meta[1], seller=meta[2], invoice_number=f"DEMO-{asset.id}"))
                if cat_name in {"Electronics", "Vehicles"} and not asset.warranties:
                    asset.warranties.append(Warranty(provider="Demo Care", start_date=date.today() - timedelta(days=60), end_date=date.today() + timedelta(days=305), terms="Demonstration warranty"))
                if cat_name in {"Electronics", "Vehicles", "Furniture"} and not asset.maintenance:
                    asset.maintenance.append(Maintenance(maintenance_type="Routine check", maintenance_date=date.today() - timedelta(days=25), next_due_date=date.today() + timedelta(days=155), cost=125, service_provider="Home service"))
                if cat_name in {"Electronics", "Vehicles"} and not asset.expenses:
                    asset.expenses.append(Expense(expense_date=date.today() - timedelta(days=12), amount=75, expense_type="Care", notes="Demo accessory or service"))
                if cat_name == "Documents" and not db.scalar(select(Document.id).where(Document.asset_id == asset.id)):
                    db.add(Document(asset_id=asset.id, filename=f"{name.lower().replace(' ', '-')}.pdf", file_type="application/pdf", file_size=24576, storage_path=None))
        db.flush()
        consumables_seed = [
            ("Oat biscuits", "Grain House", "Snacks", 3, 5, 75, 10, 85.0),
            ("Roasted almonds", "NutriFarm", "Snacks", 2, 4, 65, 8, 220.0),
            ("Masala chips", "Snack Box", "Snacks", 4, 8, 10, 10, 40.0),
            ("Dark chocolate", "Cocoa Craft", "Snacks", 1, 2, 14, 5, 120.0),
            ("Green tea", "Hill Garden", "Kitchen & Grocery", 2, 12, 5, 15, 160.0)
        ]
        for name, brand, cat_name, reorder, used, age, init_qty, unit_cost in consumables_seed:
            item = db.scalar(select(Consumable).where(Consumable.name == name))
            bought = date.today() - timedelta(days=age)
            if not item:
                item = Consumable(name=name, brand=brand, category=cats[cat_name], location=locs["Cupboard"], unit="pack", reorder_level=reorder, last_bought_at=bought, use_count=used)
                db.add(item)
                db.flush()
            if not item.batches:
                batch = ConsumableBatch(purchase_date=bought, initial_quantity=init_qty, unit_cost=unit_cost, expiry_date=date.today() + timedelta(days=45))
                batch.movements.extend([
                    StockMovement(movement_type="PURCHASE", quantity_change=init_qty, movement_date=bought),
                    StockMovement(movement_type="USED", quantity_change=-used, movement_date=date.today())
                ])
                item.batches.append(batch)
        db.flush()
        lent = db.scalar(select(Asset).where(Asset.name == "City bicycle", Asset.user_id == owner.id))
        free_person, paid_person = people["Maya"], people["Rohan"]
        if lent and not db.scalar(select(Borrowing.id).where(Borrowing.asset_id == lent.id, Borrowing.person_id == free_person.id, Borrowing.status == "ACTIVE")):
            db.add(Borrowing(asset=lent, person=free_person, borrowed_date=date.today() - timedelta(days=8), expected_return_date=date.today() - timedelta(days=1), payment_type="FREE", amount=0, payment_status="NOT_REQUIRED", notes="Friendly demo loan"))
            lent.status = "LENT"
        returned = db.scalar(select(Asset).where(Asset.name == "Study chair", Asset.user_id == owner.id))
        if returned and not db.scalar(select(Borrowing.id).where(Borrowing.asset_id == returned.id, Borrowing.person_id == paid_person.id, Borrowing.payment_type == "PAID")):
            db.add(Borrowing(asset=returned, person=paid_person, borrowed_date=date.today() - timedelta(days=35), expected_return_date=date.today() - timedelta(days=20), actual_return_date=date.today() - timedelta(days=21), status="RETURNED", payment_type="PAID", amount=250, payment_status="PAID", notes="Returned paid demo loan"))
        db.commit()

def get_snack_recommendations(db):
    """Identify snacks and consumables due for restock based on high usage frequency and purchase age."""
    snacks = db.scalars(select(Consumable).options(joinedload(Consumable.category)).where(Consumable.category.has(name="Snacks"))).unique().all()
    cutoff_date = date.today() - timedelta(days=60)
    return [
        x for x in snacks 
        if (x.use_count or 0) >= 3 and (not x.last_bought_at or x.last_bought_at <= cutoff_date)
    ]

seed()
def page(request, name, **data):
    return templates.TemplateResponse(request=request, name=name, context={"request": request, "today": date.today(), **data})
def metrics(db):
    assets = db.scalars(select(Asset).options(joinedload(Asset.purchases))).unique().all()
    total = sum((p.base_price + p.shipping_cost for a in assets for p in a.purchases), 0)
    loans = db.scalar(select(func.count(Borrowing.id)).where(Borrowing.status == "ACTIVE")) or 0
    overdue = db.scalar(select(func.count(Borrowing.id)).where(Borrowing.status == "ACTIVE", Borrowing.expected_return_date < date.today())) or 0
    expiring = db.scalar(select(func.count(Warranty.id)).where(Warranty.end_date <= date.today() + timedelta(days=30), Warranty.end_date >= date.today())) or 0
    low = 0
    for c in db.scalars(select(Consumable).options(joinedload(Consumable.batches).joinedload(ConsumableBatch.movements))).unique():
        low += sum(m.quantity_change for b in c.batches for m in b.movements) <= c.reorder_level
    return {"asset_count": len(assets), "total_value": total, "loans": loans, "overdue": overdue, "expiring": expiring, "low_stock": low, "today": date.today()}
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with Session(engine) as db:
        alerts = db.scalars(select(Borrowing).options(joinedload(Borrowing.asset), joinedload(Borrowing.person)).where(Borrowing.status == "ACTIVE").order_by(Borrowing.expected_return_date)).all()
        recommend = get_snack_recommendations(db)
        cats = db.scalars(select(Category).where(Category.assets.any()).order_by(Category.name)).all()
        return page(request, "dashboard.html", title="Home", metrics=metrics(db), alerts=alerts[:5], categories=cats, category_icons=category_icons, recommendations=recommend)
@app.get("/assets", response_class=HTMLResponse)
def assets(request: Request, q: str = "", status: str = "", category: str = "", location: str = ""):
    with Session(engine) as db:
        stmt = select(Asset).options(joinedload(Asset.category), joinedload(Asset.location), joinedload(Asset.purchases))
        if q:
            term = f"%{q.strip()}%"
            stmt = stmt.join(Asset.category, isouter=True).join(Asset.location, isouter=True)
            stmt = stmt.where(
                Asset.name.ilike(term) |
                Asset.description.ilike(term) |
                Asset.qr_code.ilike(term) |
                Category.name.ilike(term) |
                Location.name.ilike(term)
            )
        if status:
            stmt = stmt.where(Asset.status == status)
        if category:
            stmt = stmt.join(Asset.category, isouter=True).where(Category.name == category)
        if location:
            stmt = stmt.join(Asset.location, isouter=True).where(Location.name == location)
        rows = db.scalars(stmt.order_by(Asset.name)).unique().all()
        loc_rows = db.scalars(select(Location.name).order_by(Location.name)).all()
        return page(request, "assets.html", title="My things", assets=rows, q=q, status=status, category=category, selected_location=location, categories=categories, locations=loc_rows)
@app.get("/assets/new", response_class=HTMLResponse)
def new_asset(request: Request, category: str = "Miscellaneous"):
    if category not in categories:
        category = "Miscellaneous"
    with Session(engine) as db:
        locations = db.scalars(select(Location).order_by(Location.name)).all()
    return page(request, "asset_new.html", title="Add a thing", categories=categories, selected_category=category, locations=locations, fields=category_fields.get(category, []))
@app.get("/lost", response_class=HTMLResponse)
def lost_items(request: Request, status: str = ""):
    with Session(engine) as db:
        stmt = select(Asset).options(joinedload(Asset.category), joinedload(Asset.location), joinedload(Asset.purchases)).where(Asset.status.in_(["LOST", "DESTROYED"]))
        if status in {"LOST", "DESTROYED"}:
            stmt = stmt.where(Asset.status == status)
        rows = db.scalars(stmt.order_by(Asset.updated_at.desc())).unique().all()
        loc_rows = db.scalars(select(Location.name).order_by(Location.name)).all()
        return page(request, "assets.html", title="Lost and damaged", assets=rows, q="", status=status, category="", selected_location="", categories=categories, locations=loc_rows)
@app.get("/assets/{asset_id}", response_class=HTMLResponse)
def asset_detail(request: Request, asset_id: int):
    with Session(engine) as db:
        a = db.scalar(select(Asset).options(joinedload(Asset.category), joinedload(Asset.location), joinedload(Asset.purchases), joinedload(Asset.warranties), joinedload(Asset.history), joinedload(Asset.maintenance), joinedload(Asset.repairs), joinedload(Asset.user)).where(Asset.id == asset_id))
        if not a:
            return HTMLResponse("Not found", status_code=404)
        return page(request, "asset_detail.html", title=a.name, asset=a, tco=sum((p.base_price + p.shipping_cost for p in a.purchases), 0), qr=a.qr_code or f"ASSET-{a.id}")
@app.post("/assets/{asset_id}/photo", response_class=RedirectResponse)
async def upload_asset_photo(asset_id: int, photo: UploadFile = File(...)):
    if not photo or not photo.filename:
        raise HTTPException(400, "No image file provided")
    suffix = Path(photo.filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise HTTPException(400, "Only JPG, PNG, WEBP, or GIF image formats are allowed")
    content = await photo.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Photo is larger than 8 MB")
    filename = f"{secrets.token_hex(8)}{suffix}"
    target = (uploads / filename).resolve()
    if uploads.resolve() not in target.parents:
        raise HTTPException(400, "Invalid file destination")
    target.write_bytes(content)
    path = f"/static/uploads/{filename}"
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "Asset not found")
        asset.photo_path = path
        asset.version_no += 1
        db.commit()
    return RedirectResponse(f"/assets/{asset_id}", status_code=303)
@app.post("/assets/{asset_id}/photo/remove", response_class=RedirectResponse)
def remove_asset_photo(asset_id: int):
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "Asset not found")
        asset.photo_path = None
        asset.version_no += 1
        db.commit()
    return RedirectResponse(f"/assets/{asset_id}", status_code=303)
@app.post("/assets", response_class=RedirectResponse)
async def create_asset(name: str = Form(...), category: str = Form("Miscellaneous"), location: str = Form("Entry shelf"), price: float = Form(0), condition: str = Form("Good"), description: str = Form(""), photo: UploadFile | None = File(None), purchase_date: date | None = Form(None), warranty_provider: str = Form(""), warranty_end: date | None = Form(None)):
    with Session(engine) as db:
        owner = db.scalar(select(User))
        cat = db.scalar(select(Category).where(Category.name == category)) or Category(name=category)
        loc = db.scalar(select(Location).where(Location.name == location)) or Location(name=location)
        db.add_all([cat, loc])
        db.flush()
        path = None
        if photo and photo.filename:
            suffix = Path(photo.filename).suffix.lower()
            if suffix in {".jpg", ".jpeg", ".png", ".webp"} and (photo.content_type or "").startswith("image/"):
                filename = f"{secrets.token_hex(8)}{suffix}"
                content = await photo.read()
                if len(content) > 8 * 1024 * 1024:
                    raise HTTPException(413, "photo is larger than 8 MB")
                target = (uploads / filename).resolve()
                if uploads.resolve() not in target.parents:
                    raise HTTPException(400, "invalid upload path")
                target.write_bytes(content)
                path = f"/static/uploads/{filename}"
        a = Asset(user=owner, name=name[:160], category=cat, location=loc, condition=condition[:40], description=description[:2000], photo_path=path, qr_code=f"ASSET-{secrets.token_hex(4).upper()}", purchases=[Purchase(purchase_date=purchase_date or date.today(), base_price=price)])
        if warranty_provider and warranty_end:
            a.warranties.append(Warranty(provider=warranty_provider[:160], start_date=purchase_date or date.today(), end_date=warranty_end))
        db.add(a)
        db.commit()
    return RedirectResponse("/assets", status_code=303)
@app.get("/consumables", response_class=HTMLResponse)
def consumables(request: Request, category: str = "", q: str = ""):
    with Session(engine) as db:
        stmt = select(Consumable).options(joinedload(Consumable.category), joinedload(Consumable.location), joinedload(Consumable.batches).joinedload(ConsumableBatch.movements))
        if category in {"Snacks", "Kitchen & Grocery"}:
            stmt = stmt.where(Consumable.category.has(name=category))
        if q:
            term = f"%{q.strip()}%"
            stmt = stmt.where(Consumable.name.ilike(term) | Consumable.brand.ilike(term))
        items = db.scalars(stmt).unique().all()
        rows = [(c, sum(m.quantity_change for b in c.batches for m in b.movements), min((b.expiry_date for b in c.batches if b.expiry_date), default=None)) for c in items]
        recs = get_snack_recommendations(db) if category in {"", "Snacks"} else []
        return page(request, "consumables.html", title=category or "Groceries", items=rows, selected_category=category, q=q, recommendations=recs)
@app.get("/snacks", response_class=HTMLResponse)
def snacks(request: Request, q: str = ""):
    return consumables(request, "Snacks", q=q)
@app.get("/kitchen-grocery", response_class=HTMLResponse)
def kitchen_grocery(request: Request, q: str = ""):
    return consumables(request, "Kitchen & Grocery", q=q)
@app.get("/lending", response_class=HTMLResponse)
def lending(request: Request):
    with Session(engine) as db:
        loans = db.scalars(select(Borrowing).options(joinedload(Borrowing.asset), joinedload(Borrowing.person)).order_by(Borrowing.expected_return_date)).all()
        people = db.scalars(select(Person).order_by(Person.name)).all()
        assets = db.scalars(select(Asset).where(Asset.status == "AVAILABLE").order_by(Asset.name)).all()
        return page(request, "lending.html", title="Borrowing", loans=loans, people=people, assets=assets)
@app.post("/lending")
def create_loan(asset_id: int = Form(...), person_id: int = Form(...), expected_return_date: date = Form(...), payment_type: str = Form("FREE"), amount: float = Form(0), payment_status: str = Form("NOT_REQUIRED"), notes: str = Form("")):
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        loan = Borrowing(asset=asset, person_id=person_id, borrowed_date=date.today(), expected_return_date=expected_return_date, payment_type=payment_type, amount=amount, payment_status=payment_status, notes=notes)
        db.add(loan)
        if asset:
            asset.status = "LENT"
        db.commit()
    return RedirectResponse("/lending", status_code=303)
@app.post("/lending/{loan_id}/return")
def return_asset(loan_id: int):
    with Session(engine) as db:
        loan = db.get(Borrowing, loan_id)
        if loan and loan.status == "ACTIVE":
            loan.status = "RETURNED"
            loan.actual_return_date = date.today()
            loan.asset.status = "AVAILABLE"
            db.commit()
    return RedirectResponse("/lending", status_code=303)
@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request):
    with Session(engine) as db:
        cats = db.scalars(select(Category.name).order_by(Category.name)).all()
        assets = db.scalars(select(Asset).options(joinedload(Asset.category), joinedload(Asset.purchases))).unique().all()
        bycat = {}
        for a in assets:
            key = a.category.name if a.category else "Other"
            bycat[key] = bycat.get(key, 0) + sum((p.base_price + (p.shipping_cost or 0) for p in a.purchases), 0)
        return page(request, "reports.html", title="Insights & Valuation", all_categories=cats, bycat=bycat, metrics=metrics(db))
@app.get("/api/insights")
def insights(mode: str = "monthwise", period: str = "all", exclude: str = ""):
    exclude_cats = set([x.strip() for x in exclude.split(",") if x.strip()])
    with Session(engine) as db:
        assets_q = select(Asset).options(joinedload(Asset.category), joinedload(Asset.purchases))
        if exclude_cats:
            assets_q = assets_q.join(Asset.category).where(~Category.name.in_(exclude_cats))
        assets_list = db.scalars(assets_q).unique().all()

        bycat = {}
        cat_counts = {}
        for a in assets_list:
            cname = a.category.name if a.category else "Miscellaneous"
            cat_counts[cname] = cat_counts.get(cname, 0) + 1
            for p in a.purchases:
                bycat[cname] = bycat.get(cname, 0.0) + float(p.base_price + (p.shipping_cost or 0))

        total_val = sum(bycat.values()) or 1.0
        category_data = [
            {
                "category": c,
                "count": cat_counts.get(c, 0),
                "total_value": round(val, 2),
                "pct": round((val / total_val) * 100, 1)
            }
            for c, val in sorted(bycat.items(), key=lambda x: x[1], reverse=True)
        ]

        cutoff = date.today() - timedelta(days=31) if period == "month" else None
        monthly = {}
        for a in assets_list:
            for p in a.purchases:
                if not p.purchase_date:
                    continue
                if cutoff and p.purchase_date < cutoff:
                    continue
                m_key = p.purchase_date.strftime("%Y-%m")
                m_label = p.purchase_date.strftime("%b %Y")
                if m_key not in monthly:
                    monthly[m_key] = {"month_key": m_key, "label": m_label, "count": 0, "total": 0.0}
                monthly[m_key]["count"] += 1
                monthly[m_key]["total"] += float(p.base_price + (p.shipping_cost or 0))

        monthly_data = [
            {
                "month": v["month_key"],
                "label": v["label"],
                "item_count": v["count"],
                "total_spent": round(v["total"], 2)
            }
            for k, v in sorted(monthly.items(), key=lambda x: x[0])
        ]

        where_clauses = []
        if exclude_cats:
            cat_list_str = ", ".join(f"'{c}'" for c in sorted(exclude_cats))
            where_clauses.append(f"c.name NOT IN ({cat_list_str})")
        if period == "month" and mode == "monthwise":
            where_clauses.append("p.purchase_date >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY)")
        where_block = ("WHERE " + "\n  AND ".join(where_clauses) + "\n") if where_clauses else ""

        if mode == "monthwise":
            sql_query = (
                "SELECT \n"
                "    DATE_FORMAT(p.purchase_date, '%Y-%m') AS month_key,\n"
                "    DATE_FORMAT(p.purchase_date, '%b %Y') AS month_label,\n"
                "    COUNT(DISTINCT a.id) AS item_count,\n"
                "    ROUND(SUM(p.base_price + p.shipping_cost), 2) AS monthly_expenditure\n"
                "FROM purchases p\n"
                "JOIN assets a ON a.id = p.asset_id\n"
                "JOIN categories c ON c.id = a.category_id\n"
                f"{where_block}"
                "GROUP BY month_key, month_label\n"
                "ORDER BY month_key ASC;"
            )
        else:
            sql_query = (
                "SELECT \n"
                "    c.name AS category_name,\n"
                "    COUNT(DISTINCT a.id) AS asset_count,\n"
                "    ROUND(SUM(p.base_price + p.shipping_cost), 2) AS category_valuation,\n"
                "    ROUND(\n"
                "        SUM(p.base_price + p.shipping_cost) * 100.0 / \n"
                "        SUM(SUM(p.base_price + p.shipping_cost)) OVER (), \n"
                "        1\n"
                "    ) AS portfolio_percentage\n"
                "FROM categories c\n"
                "JOIN assets a ON a.category_id = c.id\n"
                "LEFT JOIN purchases p ON p.asset_id = a.id\n"
                f"{where_block}"
                "GROUP BY c.id, c.name\n"
                "ORDER BY category_valuation DESC;"
            )

        return {
            "mode": mode,
            "period": period,
            "excluded_categories": list(exclude_cats),
            "summary": {
                "asset_count": len(assets_list),
                "total_valuation": round(sum(bycat.values()), 2),
                "categories_included": len(bycat)
            },
            "category_data": category_data,
            "monthly_data": monthly_data,
            "points": [{"date": m["month"], "label": m["label"], "value": m["total_spent"]} for m in monthly_data],
            "sql_query": sql_query
        }
def query_catalog():
    return [
        {
            "id": "asset_overview",
            "title": "Asset Overview & Locations",
            "purpose": "Find every registered asset with its category, physical room, condition, status, and media tag",
            "sql": "SELECT a.id, a.name, c.name AS category, l.name AS location, a.condition, a.status, a.photo_path, a.qr_code FROM assets a LEFT JOIN categories c ON c.id=a.category_id LEFT JOIN locations l ON l.id=a.location_id ORDER BY a.name"
        },
        {
            "id": "asset_tco",
            "title": "Total Cost of Ownership (TCO View)",
            "purpose": "Aggregate total lifetime cost for each asset combining purchases, maintenance, repairs, and care expenses",
            "sql": "SELECT * FROM vw_asset_tco ORDER BY total_cost DESC"
        },
        {
            "id": "active_loans",
            "title": "Active & Overdue Borrowings",
            "purpose": "List all items currently lent out with borrower contacts, expected return dates, and payment status",
            "sql": "SELECT * FROM vw_active_loans ORDER BY expected_return_date ASC"
        },
        {
            "id": "low_stock",
            "title": "Pantry & Groceries Needing Restock",
            "purpose": "Aggregate consumable batch movements to identify items that have dropped below their reorder threshold",
            "sql": "SELECT * FROM vw_consumable_stock WHERE needs_reorder = 1 ORDER BY current_stock ASC"
        },
        {
            "id": "warranty_tracker",
            "title": "Equipment Warranties & Expiry",
            "purpose": "Find equipment warranties and calculate remaining active coverage days",
            "sql": "SELECT a.id AS asset_id, a.name AS asset_name, w.provider, w.end_date, DATEDIFF(w.end_date, CURRENT_DATE) AS days_remaining FROM warranties w JOIN assets a ON a.id = w.asset_id WHERE w.end_date >= CURRENT_DATE ORDER BY w.end_date ASC"
        },
        {
            "id": "repairs_log",
            "title": "Equipment Repair & Maintenance History",
            "purpose": "Track ongoing and completed repairs, service providers, and incurred repair costs",
            "sql": "SELECT r.id AS repair_id, a.name AS asset_name, r.issue, r.status, r.provider, r.cost, r.reported_date FROM repairs r JOIN assets a ON a.id = r.asset_id ORDER BY r.reported_date DESC"
        },
        {
            "id": "photo_inventory",
            "title": "Database Photo Storage vs QR Fallbacks",
            "purpose": "Inspect assets with uploaded photo paths in MySQL versus algorithmically assigned QR identifiers",
            "sql": "SELECT id, name, status, CASE WHEN photo_path IS NOT NULL THEN 'Uploaded Photo' ELSE 'QR Code' END AS visual_identifier, photo_path, qr_code, updated_at FROM assets ORDER BY photo_path DESC, name ASC"
        }
    ]
@app.get("/api/query-lab")
def api_query_lab(query: str = "asset_overview"):
    catalog = {item["id"]: item for item in query_catalog()}
    if query not in catalog:
        raise HTTPException(404, "unknown query")
    sql = catalog[query]["sql"]
    start = time.perf_counter()
    with engine.connect() as db:
        result = db.execute(text(sql))
        columns = list(result.keys()) if hasattr(result, "keys") else []
        rows = [dict(row._mapping) for row in result]
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    return {
        "id": query,
        "title": catalog[query].get("title", query),
        "purpose": catalog[query]["purpose"],
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "count": len(rows),
        "elapsed_ms": elapsed
    }
@app.post("/api/query-lab/custom")
async def api_custom_sql(request: Request):
    data = await request.json()
    query_sql = str(data.get("sql", "")).strip()
    if not query_sql:
        raise HTTPException(400, "SQL query cannot be empty")
    
    normalized = query_sql.strip().lower()
    if ";" in query_sql.rstrip(";"):
        raise HTTPException(400, "Multiple statements are not permitted for security.")
    
    allowed_prefixes = ("select", "show", "describe", "desc", "explain")
    if not any(normalized.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(400, "Only read-only queries (SELECT, SHOW, DESCRIBE, EXPLAIN) are permitted.")
    
    disallowed_keywords = {"drop", "delete", "update", "insert", "alter", "truncate", "create", "grant", "revoke", "replace", "call", "kill"}
    tokens = set(re.findall(r'\b[a-zA-Z]+\b', normalized))
    overlap = disallowed_keywords.intersection(tokens)
    if overlap:
        raise HTTPException(400, f"Query contains disallowed mutation keyword: {', '.join(k.upper() for k in overlap)}")
    
    start = time.perf_counter()
    try:
        with engine.connect() as db:
            result = db.execute(text(query_sql))
            columns = list(result.keys()) if hasattr(result, "keys") else []
            rows = [dict(row._mapping) for row in result]
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        return {
            "sql": query_sql,
            "columns": columns,
            "rows": rows,
            "count": len(rows),
            "elapsed_ms": elapsed
        }
    except Exception as err:
        raise HTTPException(400, f"MySQL Execution Error: {str(err)}")
@app.get("/api/categories/{category}/new-item")
def new_item_form(category: str):
    if category not in categories:
        raise HTTPException(404, "unknown category")
    return {"category": category, "fields": [{"name": "name", "type": "text", "required": True}, {"name": "location", "type": "text"}, {"name": "price", "type": "number"}, *[{"name": x, "type": "date" if "date" in x or "expiry" in x or "warranty" in x else "text"} for x in category_fields.get(category, [])]]}
@app.get("/api/assets/{asset_id}")
def api_asset(asset_id: int):
    with Session(engine) as db:
        asset = db.scalar(select(Asset).options(joinedload(Asset.category), joinedload(Asset.location), joinedload(Asset.purchases), joinedload(Asset.warranties)).where(Asset.id == asset_id))
        if not asset:
            raise HTTPException(404, "asset not found")
        purchase = max(asset.purchases, key=lambda x: x.purchase_date, default=None)
        return {"id": asset.id, "name": asset.name, "category": asset.category.name if asset.category else None, "location": asset.location.name if asset.location else None, "status": asset.status, "condition": asset.condition, "updated_at": asset.updated_at, "purchase": {"date": purchase.purchase_date, "price": purchase.base_price, "seller": purchase.seller} if purchase else None, "warranties": [{"provider": w.provider, "start_date": w.start_date, "end_date": w.end_date, "terms": w.terms} for w in asset.warranties], "qr_code": asset.qr_code or f"ASSET-{asset.id}", "photo_path": asset.photo_path}
@app.patch("/api/assets/{asset_id}")
async def update_asset(asset_id: int, request: Request):
    data = await request.json()
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "asset not found")
        for key in ("name", "condition", "description", "photo_path"):
            if key in data and data[key] is not None:
                setattr(asset, key, str(data[key])[:500])
        if "location" in data:
            location = db.scalar(select(Location).where(Location.name == str(data["location"]))) or Location(name=str(data["location"])[:100])
            db.add(location); db.flush(); asset.location = location
        asset.version_no += 1
        db.commit()
        return {"status": "UPDATED", "asset": asset_id, "version": asset.version_no}
@app.post("/api/assets/{asset_id}/status")
async def change_asset_status(asset_id: int, request: Request):
    data = await request.json()
    new_status = str(data.get("status", "")).upper()
    if new_status not in {"AVAILABLE", "LENT", "LOST", "DESTROYED"}:
        raise HTTPException(400, "invalid status")
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "asset not found")
        old = asset.status
        if old != new_status:
            asset.status = new_status
            asset.history.append(AssetStatusHistory(old_status=old, new_status=new_status, reason=str(data.get("reason", ""))[:255]))
            asset.version_no += 1
            db.commit()
        return {"status": asset.status, "changed": old != new_status}
@app.post("/api/assets/{asset_id}/lost")
async def mark_lost(asset_id: int, request: Request):
    data = await request.json()
    data["status"] = "LOST"
    request._body = __import__("json").dumps(data).encode()
    return await change_asset_status(asset_id, request)
@app.post("/api/assets/{asset_id}/destroyed")
async def mark_destroyed(asset_id: int, request: Request):
    data = await request.json()
    data["status"] = "DESTROYED"
    request._body = __import__("json").dumps(data).encode()
    return await change_asset_status(asset_id, request)
@app.get("/api/assets/{asset_id}/history")
def asset_history(asset_id: int):
    with Session(engine) as db:
        if not db.get(Asset, asset_id):
            raise HTTPException(404, "asset not found")
        history = db.scalars(select(AssetStatusHistory).where(AssetStatusHistory.asset_id == asset_id).order_by(AssetStatusHistory.changed_at.desc())).all()
        repairs = db.scalars(select(Repair).where(Repair.asset_id == asset_id).order_by(Repair.reported_date.desc())).all()
        return {"status_history": [{"old_status": x.old_status, "new_status": x.new_status, "reason": x.reason, "changed_at": x.changed_at} for x in history], "repairs": [repair_dict(x) for x in repairs]}
def repair_dict(repair):
    return {"id": repair.id, "issue": repair.issue, "status": repair.status, "reported_date": repair.reported_date, "completed_date": repair.completed_date, "provider": repair.provider, "cost": repair.cost, "notes": repair.notes}
@app.get("/api/assets/{asset_id}/repairs")
def list_repairs(asset_id: int):
    with Session(engine) as db:
        if not db.get(Asset, asset_id):
            raise HTTPException(404, "asset not found")
        return [repair_dict(x) for x in db.scalars(select(Repair).where(Repair.asset_id == asset_id).order_by(Repair.reported_date.desc())).all()]
@app.post("/api/assets/{asset_id}/repairs")
async def create_repair(asset_id: int, request: Request):
    data = await request.json()
    if not str(data.get("issue", "")).strip():
        raise HTTPException(422, "issue is required")
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "asset not found")
        repair = Repair(asset_id=asset_id, issue=str(data["issue"])[:255], status=str(data.get("status", "OPEN")).upper(), provider=str(data.get("provider", ""))[:160] or None, cost=data.get("cost", 0), notes=str(data.get("notes", ""))[:2000] or None)
        db.add(repair); db.commit(); db.refresh(repair)
        return repair_dict(repair)
@app.get("/api/consumables")
def api_consumables(category: str | None = None):
    with Session(engine) as db:
        stmt = select(Consumable).options(joinedload(Consumable.category), joinedload(Consumable.batches).joinedload(ConsumableBatch.movements))
        if category:
            if category not in {"Snacks", "Kitchen & Grocery"}:
                raise HTTPException(400, "category must be Snacks or Kitchen & Grocery")
            stmt = stmt.where(Consumable.category.has(name=category))
        return [{"id": c.id, "name": c.name, "category": c.category.name if c.category else None, "stock": sum(m.quantity_change for b in c.batches for m in b.movements), "unit": c.unit, "reorder_level": c.reorder_level} for c in db.scalars(stmt).unique().all()]
def generate_qr_svg_bytes(data: str) -> bytes:
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    stream = io.BytesIO()
    img.save(stream)
    return stream.getvalue()

@app.get("/qr/{asset_id}.svg")
@app.get("/qr/{asset_id}/svg")
def get_qr_svg(asset_id: int):
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "asset not found")
        data = asset.qr_code or f"ASSET-{asset.id}"
        return Response(content=generate_qr_svg_bytes(data), media_type="image/svg+xml")

@app.get("/qr/{asset_id}")
def qr_fallback(asset_id: int):
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "asset not found")
        data = asset.qr_code or f"ASSET-{asset.id}"
        return Response(content=generate_qr_svg_bytes(data), media_type="image/svg+xml")

@app.get("/qr/{asset_id}/download")
def download_qr(asset_id: int):
    with Session(engine) as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "asset not found")
        data = asset.qr_code or f"ASSET-{asset.id}"
        return Response(
            content=generate_qr_svg_bytes(data),
            media_type="image/svg+xml",
            headers={"Content-Disposition": f'attachment; filename="asset-{asset.id}-qr.svg"'}
        )
@app.get("/query-lab", response_class=HTMLResponse)
def query_lab(request: Request):
    return page(request, "query_lab.html", title="Query lab", queries=query_catalog())
@app.get("/api/dashboard")
def api_dashboard():
    with Session(engine) as db:
        return metrics(db)
@app.post("/api/sync")
async def sync(request: Request):
    payload = await request.json()
    with Session(engine) as db:
        accepted = []
        for item in payload.get("operations", []):
            client_id = str(item.get("client_id") or secrets.token_hex(12))
            if db.scalar(select(SyncLog.id).where(SyncLog.client_id == client_id)):
                continue
            entity = item.get("entity", "unknown")
            entity_id = item.get("id")
            data = item.get("data") or {}
            if entity == "asset" and item.get("operation") == "CREATE" and str(data.get("name", "")).strip():
                owner = db.scalar(select(User))
                cat = db.scalar(select(Category).where(Category.name == str(data.get("category", "Miscellaneous")))) or Category(name=str(data.get("category", "Miscellaneous"))[:80])
                loc = db.scalar(select(Location).where(Location.name == str(data.get("location", "Entry shelf")))) or Location(name=str(data.get("location", "Entry shelf"))[:100])
                db.add_all([cat, loc])
                db.flush()
                created = Asset(user=owner, name=str(data["name"])[:160], category=cat, location=loc, condition=str(data.get("condition", "Good"))[:40], description=str(data.get("description", ""))[:2000], qr_code=f"ASSET-{secrets.token_hex(4).upper()}", purchases=[Purchase(purchase_date=date.today(), base_price=data.get("price", 0))])
                db.add(created)
            if entity == "asset" and entity_id:
                asset = db.get(Asset, int(entity_id))
                if asset:
                    if item.get("operation") == "STATUS" and data.get("status") in {"AVAILABLE", "LENT", "LOST", "DESTROYED"}:
                        old = asset.status
                        asset.status = data["status"]
                        if old != asset.status:
                            asset.history.append(AssetStatusHistory(old_status=old, new_status=asset.status, reason="Offline sync"))
                    elif item.get("operation") in {"UPSERT", "UPDATE"}:
                        for key in ("name", "condition", "description"):
                            if key in data:
                                setattr(asset, key, str(data[key])[:500])
                    asset.version_no += 1
            if entity == "repair" and entity_id and item.get("operation") in {"UPSERT", "UPDATE"}:
                asset = db.get(Asset, int(entity_id))
                if asset and str(data.get("issue", "")).strip():
                    db.add(Repair(asset_id=asset.id, issue=str(data["issue"])[:255], provider=str(data.get("provider", ""))[:160] or None, cost=data.get("cost", 0), notes=str(data.get("notes", ""))[:2000] or None))
            db.add(SyncLog(operation=item.get("operation", "UPSERT"), entity=entity, entity_id=entity_id, client_id=client_id))
            accepted.append(client_id)
        db.commit()
    return JSONResponse({"status": "COMMITTED", "processed": len(accepted), "accepted": accepted, "idempotent": True})
