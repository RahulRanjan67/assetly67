# Assetly — Manual Setup & Run Guide (`open.md`)

Use this step-by-step manual guide if you prefer running commands directly in **Command Prompt (CMD)** or **PowerShell**, or as a fallback if automated scripts (`setup_first_time.bat` / `run_app.bat`) are blocked by system policies.

---

## Prerequisites
1. **Python 3.10+** installed on your PC.
2. **MySQL Server 8.0+** installed and running on your PC (default port `3306`).

---

## Option A: Manual First-Time Setup in Command Prompt (CMD)

Open **Command Prompt (`cmd.exe`)** and run the following commands one by one:

### Step 1: Navigate to your extracted `Assetly` folder
Replace the path below with the location where you extracted the `Assetly` folder on your PC:
```cmd
cd /d "path\to\Assetly"
```

### Step 2: Remove any old `.venv` folder from another PC and create a fresh one
> **Important:** Python virtual environments (`.venv`) store the exact folder path of the PC where they were created. When moving or unzipping the project on a new PC, always delete the old `.venv` first and create a new one:
```cmd
if exist .venv rmdir /s /q .venv
python -m venv .venv
```
*(If `python` is not recognized, use `py -3 -m venv .venv` or `"C:\Path\To\Python\python.exe" -m venv .venv`)*

### Step 3: Install required Python packages into `.venv`
```cmd
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Step 4: Configure your MySQL connection & initialize the database
Run the interactive database setup script (it will ask for your MySQL host, port, username, and password, write `.env` automatically, create all tables, views, stored procedures, and seed the 12-month sample inventory):
```cmd
.venv\Scripts\python.exe scripts\init_db.py --setup
```

#### (Alternative) Manual `.env` configuration without interactive prompt:
If you prefer editing `.env` manually before running `init_db.py`:
1. Open `.env` in Notepad (`notepad .env`).
2. Set your MySQL username (usually `root`) and password:
   ```ini
   DATABASE_URL=mysql+pymysql://root:YOUR_MYSQL_PASSWORD@127.0.0.1:3306/assetly
   ```
   *(Note: If your MySQL password contains `@`, replace `@` with `%40` in the URL — for example `pass@123` becomes `pass%40123`).*
3. Then run:
   ```cmd
   .venv\Scripts\python.exe scripts\init_db.py
   ```

### Step 5: Start the Assetly web server manually
```cmd
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Once started, open your browser and visit:
**http://127.0.0.1:8000**

---

## Option B: Manual Daily Run (After First-Time Setup is Done)

Once you have completed First-Time Setup on your PC, you only need two commands in **CMD** to start the app anytime:

```cmd
cd /d "path\to\Assetly"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Then open **http://127.0.0.1:8000** in your browser.

---

## Option C: Manual Setup & Run in PowerShell

If you are using **Windows PowerShell**, run these commands one by one:

```powershell
# 1. Go to the Assetly folder
cd "path\to\Assetly"

# 2. Remove any old .venv from another PC and create a fresh one
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
python -m venv .venv

# 3. Install dependencies
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. Configure MySQL password, initialize schema, views, and seed data
.\.venv\Scripts\python.exe scripts\init_db.py --setup

# 5. Start the web server
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## Troubleshooting Common Issues on a New PC

| Issue / Symptom | Cause | Solution |
| :--- | :--- | :--- |
| `No Python at 'C:\Users\...\python.exe'` or script exits immediately | The `.venv` folder inside the zip was created on another PC with a different user path. | Run `rmdir /s /q .venv` and then `python -m venv .venv` (or simply run `setup_first_time.bat`, which now does this automatically). |
| `'python' is not recognized as an internal or external command` | Python was installed without checking *"Add Python to PATH"*. | Either run `setup_first_time.bat` and paste your `python.exe` path when prompted, or use `"C:\Users\<YourUser>\AppData\Local\Programs\Python\Python313\python.exe" -m venv .venv`. |
| `'cryptography' package is required for caching_sha2_password` | MySQL 8.0 requires `cryptography` for `root` login. | Run `.venv\Scripts\python.exe -m pip install cryptography` (now included automatically in `requirements.txt` and `init_db.py`). |
| `Access denied for user 'root'@'localhost'` | Incorrect MySQL `root` password entered. | Re-run `setup_first_time.bat` (or `.venv\Scripts\python.exe scripts\init_db.py --setup`) and enter your MySQL `root` password. |
| `Can't connect to MySQL server on '127.0.0.1'` | MySQL Windows service is stopped. | Open **Services** (`services.msc`) or an Administrator CMD and run `net start MySQL80`. |

---

## Option D: Cloud Deployment on Aiven (MySQL 8.0) + Vercel

Assetly is pre-configured with `vercel.json` and `api/index.py` for zero-config deployment on **Vercel** paired with **Aiven for MySQL**:

1. **Create an Aiven MySQL Service:**
   - Sign in at [console.aiven.io](https://console.aiven.io/), create a **MySQL** service (Free plan), and wait until its status shows **Running**.
   - Under **Connection information**, copy the **Service URI**:
     ```text
     mysql://avnadmin:YOUR_PASSWORD@mysql-xxxx.a.aivencloud.com:12345/defaultdb?ssl-mode=REQUIRED
     ```
2. **Deploy to Vercel:**
   - Push this folder to a GitHub repository (or run `npx vercel --prod` from the `Assetly` folder).
   - In the Vercel Dashboard, click **Add New... -> Project** and import your repository.
   - Open **Environment Variables** and add:
     - **Key:** `DATABASE_URL`
     - **Value:** *(Paste your Aiven Service URI directly — Assetly automatically converts `mysql://` to `mysql+pymysql://`, strips `?ssl-mode=REQUIRED`, and configures TLS/SSL encryption).*
   - Click **Deploy**. On the first visit, Assetly automatically provisions all tables, the 5 analytical MySQL views, and the 12-month demo dataset on Aiven!

