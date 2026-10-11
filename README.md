# Assetly - Home & Household Inventory

Offline-first home inventory system for households and students built with FastAPI, Jinja2, SQLAlchemy 2.0, and MySQL 8.0.

---

## ⚡ Quick Start Scripts (Windows)

Two 1-click startup files are provided in the project root:

### 1. First-Time Setup (`setup_first_time.bat` / `setup_first_time.ps1`)
Use this when setting up Assetly for the first time or completely resetting your environment:
- Interactively prompts for MySQL connection parameters (Host, Port, User, Password, DB Name) on the PC and safely creates/updates `.env` from `.env.example` (with special character URL encoding like `%40`).
- Drops any previous conflicting versions of the database schemas, tables, and views for a clean slate.
- Automatically provisions `.venv` and installs dependencies (`requirements.txt`).
- Builds normalized relational tables, applies MySQL 8.0 views & stored procedures, and seeds 12-month distributed demo inventory.
- Shows step-by-step console logs and automatically opens `http://127.0.0.1:8000` in your default browser.

```powershell
.\setup_first_time.bat
# or in PowerShell:
.\setup_first_time.ps1
```

### 2. Daily Application Launcher (`run_app.bat` / `run_app.ps1`)
Use this once the setup is completed to start the existing application directly:
- Starts the uvicorn server quietly in the background and launches your browser.
- Cleans the console and displays **only** the clean local link:
  ```
  ===============================================================================
    Assetly is running at: http://127.0.0.1:8000
    (Press Ctrl+C to stop the application)
  ===============================================================================
  ```

```powershell
.\run_app.bat
# or in PowerShell:
.\run_app.ps1
```

---

## 🛠 Features & Capabilities

### 1. Advanced Statistics & Sensitivity Analysis (`/reports`)
- **Month-wise vs Total Portfolio Modes**:
  - **Month-wise**: Groups acquisition transactions by calendar month (`YYYY-MM`), illustrating historical expenditure trends across the last 12 months with interactive SVG charts and monthly breakdown tables.
  - **Total Portfolio**: Displays full capital allocation percentages across all categories with horizontal proportion bars and asset valuations.
- **Category Exclusion (Skew Prevention)**:
  - High-ticket categories (such as **Electronics** with a ₹54,990 laptop) can disproportionately skew averages. Click category chips or the **"⚡ Exclude High-Cost (Electronics)"** button to dynamically recalculate baseline household spending.
- **Expandable Live MySQL Analytical Query**:
  - An interactive `<details>` accordion at the very bottom of the page exposes the exact parameterized MySQL 8.0 query executed for the current view (including dynamic `NOT IN (...)` clauses and window aggregates) with a **"📋 Copy SQL"** button.

### 2. Snack Restock Recommendation Engine (`/` and `/consumables`)
- **Smart Usage & Age Tracking**: Identifies snacks and consumable staples that have high historical consumption (&ge; 3 uses) and have not been purchased in over 60 days.
- **Dedicated Restock Banners**: Displays prominent reorder cards on the Home Dashboard and at the top of the Pantry & Groceries page.

### 3. Full Offline Capability (PWA Architecture)
- **Service Worker Shell Caching**: Caches HTML layouts, stylesheets, and scripts for offline access across all application pages.
- **IndexedDB Transaction Journal (`assetly-outbox`)**: When offline, changes (new assets, repairs, status transitions) are queued locally with cryptographic UUIDs.
- **Automatic Background Synchronization**: When internet connectivity resumes, the browser pushes pending mutations to `/api/sync`, committing them idempotently to MySQL.

### 4. Interactive MySQL Query Lab (`/query-lab`)
- **Responsive Table Results**: Executes live MySQL queries and formats rows into responsive, scrollable HTML tables with auto-detected columns, execution latency (`ms`), and record counts.
- **CSV Export**: Download table results as CSV files with a single click.
- **Interactive Custom SQL Runner**: Execute read-only SQL queries (`SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`) directly from the browser with syntax validation and quick preset pills.
- **Database Showcasing Views**: Inspect 7 pre-built queries covering `vw_asset_overview`, `vw_asset_tco` (lifetime cost), `vw_active_loans`, `vw_consumable_stock`, expiring warranties, repair histories, and photo storage.

### 5. Scannable QR Code Vector Generator (`/qr/{id}.svg`)
- Generates genuine, crisp SVG vector QR codes on the fly using `qrcode` for any item.
- Asset detail page includes **Download QR SVG** and **Print Asset Tag** buttons for physical labeling.
- Items without photos show rendered vector QR code previews in the asset catalog.

### 6. Image Upload & Database Record Showcasing
- **Photo Upload on Detail View**: Add, replace, or remove photos directly on existing asset detail pages (`/assets/{id}`) with instant MySQL update.
- **Live Database Record Inspector**: View the raw MySQL tuple (`SELECT * FROM assets WHERE id = ...`) with foreign keys, data types, and timestamps.

### 7. Multi-Field Inventory & Pantry Search
- **Global Topbar Search**: Quick-lookup search bar in the top navigation on every screen.
- **Catalog Search**: Filter across asset name, description, QR code, room/location, and category name simultaneously.
- **Pantry Search**: Search groceries and snacks by item name or brand.

---

## 🧪 Testing & Validation

```powershell
$env:ASSETLY_TESTING="1"
$env:DATABASE_URL="sqlite:///./test_assetly.db"
.\.venv\Scripts\pytest -v
.\.venv\Scripts\python -m compileall -q app scripts tests
```
