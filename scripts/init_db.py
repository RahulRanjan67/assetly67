"""
Assetly Database Initialization & First-Time Setup Script.
Uses 'root' as the local MySQL database user, prompts for the MySQL root password,
verifies connection, writes .env, cleans up any previous database versions,
creates normalized SQLAlchemy tables, applies MySQL 8.0 views and stored procedures,
and seeds initial inventory data.
"""
import os
import re
import ssl
import subprocess
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse, unquote, quote_plus

# Set working directory to project root
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure cryptography is installed for MySQL 8.0 caching_sha2_password authentication
try:
    import cryptography  # noqa: F401
except ImportError:
    print("[*] Installing required 'cryptography' package for MySQL 8.0 authentication...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptography"])

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass

import pymysql
from sqlalchemy import create_engine, text
from app.models import Base


def is_remote_host(host: str) -> bool:
    return bool(host) and host.lower() not in ("127.0.0.1", "localhost")


def get_ssl_kwargs(host: str) -> dict:
    if is_remote_host(host):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return {"ssl": ctx}
    return {}


def parse_mysql_url(raw_url: str):
    clean_url = raw_url.strip().strip('"').strip("'").replace("mysql+pymysql://", "mysql://")
    parsed = urlparse(clean_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    # Local MySQL always uses 'root'; remote cloud URIs (e.g. Aiven) preserve their URI user
    user = unquote(parsed.username or "root") if is_remote_host(host) else "root"
    password = unquote(parsed.password or "")
    if password == "YOUR_PASSWORD" or password == "change_me@local":
        password = ""
    db_name = (parsed.path.lstrip("/") or "assetly").split("?")[0]
    return host, port, user, password, db_name


def build_sqlalchemy_url(host: str, port: int, user: str, password: str, db_name: str) -> str:
    encoded_user = quote_plus(user)
    encoded_pass = quote_plus(password)
    return f"mysql+pymysql://{encoded_user}:{encoded_pass}@{host}:{port}/{db_name}"


def get_db_config():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        env_ex = ROOT_DIR / ".env.example"
        if env_ex.exists():
            for line in env_ex.read_text().splitlines():
                if line.strip().startswith("DATABASE_URL="):
                    url = line.strip().split("=", 1)[1].strip()
                    break
    if not url:
        url = "mysql+pymysql://root:@127.0.0.1:3306/assetly"

    host, port, user, password, db_name = parse_mysql_url(url)
    clean_sa_url = build_sqlalchemy_url(host, port, user, password, db_name)
    return clean_sa_url, host, port, user, password, db_name


def can_connect(host, port, user, password, db_name=None):
    try:
        kwargs = dict(host=host, port=port, user=user, password=password, connect_timeout=8, **get_ssl_kwargs(host))
        if db_name:
            kwargs["database"] = db_name
        conn = pymysql.connect(**kwargs)
        conn.close()
        return True, None
    except Exception as err:
        return False, err


def configure_env_interactively():
    print("\n------------------------------------------------------------")
    print("      MySQL Connection Configuration (User: root)           ")
    print("------------------------------------------------------------")
    url, def_host, def_port, def_user, def_pass, def_dbname = get_db_config()
    if not is_remote_host(def_host):
        def_user = "root"

    while True:
        print("\nPress Enter to accept [default] values or enter your MySQL root password:")
        print(f"  * MySQL Username: {def_user}")
        try:
            host_or_uri = input(f"  * MySQL Host [{def_host}]: ").strip() or def_host
            if host_or_uri.startswith(("mysql://", "mysql+pymysql://")):
                host, port, user, password, dbname = parse_mysql_url(host_or_uri)
            else:
                host = host_or_uri
                user = "root" if not is_remote_host(host) else def_user
                port_input = input(f"  * MySQL Port [{def_port}]: ").strip()
                try:
                    port = int(port_input) if port_input else def_port
                except ValueError:
                    port = def_port

                pass_hint = "leave blank to keep current" if def_pass else "enter your MySQL root password"
                entered_pass = input(f"  * MySQL Password for '{user}' ({pass_hint}): ").strip()
                password = entered_pass if entered_pass != "" else def_pass

                dbname = input(f"  * Database Name [{def_dbname}]: ").strip() or def_dbname
        except (EOFError, KeyboardInterrupt):
            print("\nUsing existing configuration.")
            host, port, user, password, dbname = def_host, def_port, def_user, def_pass, def_dbname

        ok_srv, err_srv = can_connect(host, port, user, password)
        ok_db, err_db = (True, None) if ok_srv else can_connect(host, port, user, password, dbname)

        if ok_srv or ok_db:
            new_url = build_sqlalchemy_url(host, port, user, password, dbname)
            env_file = ROOT_DIR / ".env"
            env_file.write_text(f"DATABASE_URL={new_url}\n")
            os.environ["DATABASE_URL"] = new_url
            print(f"[+] Connection verified as '{user}'! Saved configuration to {env_file.name}")
            return new_url, host, port, user, password, dbname
        else:
            print(f"\n[!] Could not connect to MySQL at {host}:{port} as '{user}':")
            print(f"    Error details: {err_srv}")
            print("    Tip: Ensure MySQL Server is running (services.msc -> MySQL80) and your root password is correct.")
            try:
                retry = input("    Try entering password/settings again? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                raise SystemExit(1)
            if retry == "n":
                raise SystemExit(1)
            def_host, def_port, def_user, def_dbname = host, port, user, dbname


def cleanup_previous_database(host, port, user, password, db_name):
    print(f"[*] Connecting to MySQL at {host}:{port} as user '{user}'...")
    ssl_kw = get_ssl_kwargs(host)
    if not is_remote_host(host):
        try:
            conn = pymysql.connect(host=host, port=port, user=user, password=password, autocommit=True, **ssl_kw)
            with conn.cursor() as cur:
                print(f"[*] Dropping previous database '{db_name}' if exists...")
                try:
                    cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
                    print(f"[+] Dropped previous database '{db_name}'.")
                except Exception as drop_err:
                    print(f"[!] Warning dropping database directly: {drop_err}. Will drop tables individually.")

                print(f"[*] Creating fresh database '{db_name}'...")
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
                print(f"[+] Database '{db_name}' ready.")
            conn.close()
            sqlite_test_file = ROOT_DIR / "test_assetly.db"
            if sqlite_test_file.exists():
                try:
                    sqlite_test_file.unlink()
                except Exception:
                    pass
            return
        except Exception as e:
            print(f"[!] Could not reset at server level: {e}")

    print(f"[*] Cleaning existing tables and views inside database '{db_name}'...")
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, autocommit=True, **ssl_kw)
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
        conn.close()
    except Exception:
        pass

    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db_name, autocommit=True, **ssl_kw)
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("SHOW FULL TABLES")
        tables = cur.fetchall()
        for table_name, table_type in tables:
            if table_type == "VIEW":
                cur.execute(f"DROP VIEW IF EXISTS `{table_name}`")
            else:
                cur.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        cur.execute("DROP PROCEDURE IF EXISTS sp_return_asset")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.close()
    print(f"[+] Cleaned all existing tables and views in '{db_name}'.")

    sqlite_test_file = ROOT_DIR / "test_assetly.db"
    if sqlite_test_file.exists():
        try:
            sqlite_test_file.unlink()
            print(f"[+] Cleaned up previous SQLite test artifact ({sqlite_test_file.name}).")
        except Exception:
            pass


def init_tables(url, host):
    print("[*] Creating normalized relational tables via SQLAlchemy models...")
    engine = create_engine(url, connect_args=get_ssl_kwargs(host), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    print("[+] All core tables provisioned successfully.")
    return engine


def apply_mysql_schema(host, port, user, password, db_name):
    schema_path = ROOT_DIR / "sql" / "mysql_schema.sql"
    if not schema_path.exists():
        print(f"[!] Warning: Schema file {schema_path} not found.")
        return

    print("[*] Applying MySQL 8 presentation layer, analytical views & stored procedures...")
    content = schema_path.read_text()

    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db_name, autocommit=True, **get_ssl_kwargs(host))
    with conn.cursor() as cur:
        parts = re.split(r'DELIMITER\s+//', content, flags=re.IGNORECASE)
        regular_part = parts[0]
        procedure_part = parts[1] if len(parts) > 1 else ''

        for stmt in regular_part.split(';'):
            clean_lines = [l for l in stmt.splitlines() if not l.strip().startswith('--')]
            clean_stmt = '\n'.join(clean_lines).strip()
            if clean_stmt:
                cur.execute(clean_stmt)

        if procedure_part:
            proc_body = re.split(r'//\s*DELIMITER\s*;?', procedure_part, flags=re.IGNORECASE)[0].strip()
            if proc_body:
                try:
                    cur.execute(proc_body)
                except Exception as proc_err:
                    print(f"[!] Note: Stored procedure creation skipped on managed cloud DB ({proc_err}).")

    conn.close()
    print("[+] Applied analytical views and stored procedure 'sp_return_asset'.")


def run_seed():
    print("[*] Seeding demo inventory with 12-month distributed timeline, warranties, and pantry items...")
    from app.main import seed
    seed(force=True)
    print("[+] Demo data seeded successfully.")


def verify_and_report(url, host):
    print("[*] Verifying database records...")
    engine = create_engine(url, connect_args=get_ssl_kwargs(host))
    with engine.connect() as conn:
        users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        categories_count = conn.execute(text("SELECT COUNT(*) FROM categories")).scalar()
        assets_count = conn.execute(text("SELECT COUNT(*) FROM assets")).scalar()
        purchases_count = conn.execute(text("SELECT COUNT(*) FROM purchases")).scalar()
        consumables_count = conn.execute(text("SELECT COUNT(*) FROM consumables")).scalar()
        loans_count = conn.execute(text("SELECT COUNT(*) FROM borrowings")).scalar()
        views = conn.execute(text("SHOW FULL TABLES WHERE Table_type = 'VIEW'")).fetchall()

    print("\n" + "=" * 60)
    print("  ASSETLY DATABASE INITIALIZATION SUMMARY")
    print("=" * 60)
    print(f"  * Users:             {users}")
    print(f"  * Categories:        {categories_count}")
    print(f"  * Registered Assets: {assets_count}")
    print(f"  * Purchase Records:  {purchases_count}")
    print(f"  * Pantry/Groceries:  {consumables_count}")
    print(f"  * Active/Demo Loans: {loans_count}")
    print(f"  * MySQL Views:       {len(views)} ({', '.join(v[0] for v in views)})")
    print("=" * 60 + "\n")


def check_ready():
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return False
    url, host, port, user, password, db_name = get_db_config()
    if not is_remote_host(host) and user != "root":
        return False
    ok_db, _ = can_connect(host, port, user, password, db_name)
    if not ok_db:
        return False
    try:
        engine = create_engine(url, connect_args=get_ssl_kwargs(host))
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM assets LIMIT 1"))
        return True
    except Exception:
        return False


def main():
    if "--check" in sys.argv:
        sys.exit(0 if check_ready() else 1)

    print("============================================================")
    print("           Assetly - Database Setup & Initialization        ")
    print("============================================================")
    interactive = ("--setup" in sys.argv or "--interactive" in sys.argv or not (ROOT_DIR / ".env").exists())
    if interactive:
        url, host, port, user, password, db_name = configure_env_interactively()
    else:
        url, host, port, user, password, db_name = get_db_config()
        ok_srv, _ = can_connect(host, port, user, password)
        ok_db, _ = (True, None) if ok_srv else can_connect(host, port, user, password, db_name)
        if not (ok_srv or ok_db):
            print("[!] Saved .env credentials could not connect to MySQL. Switching to interactive prompt...")
            url, host, port, user, password, db_name = configure_env_interactively()

    cleanup_previous_database(host, port, user, password, db_name)
    init_tables(url, host)
    apply_mysql_schema(host, port, user, password, db_name)
    run_seed()
    verify_and_report(url, host)
    print("[SUCCESS] Database initialization completed successfully!")
    print("          Local Web Link: http://127.0.0.1:8000")


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check_ready() else 1)
    try:
        main()
    except SystemExit as e:
        if e.code not in (0, None):
            print("\n[!] Setup stopped before completion. Review the messages above.")
            try:
                input("Press Enter to return to terminal...")
            except Exception:
                pass
        raise
    except Exception as exc:
        print("\n" + "=" * 60)
        print("[ERROR] An unexpected issue occurred during database setup:")
        print(f"        {exc}")
        print("-" * 60)
        traceback.print_exc()
        print("=" * 60)
        try:
            input("\nPress Enter after reviewing the error above...")
        except Exception:
            pass
        sys.exit(1)
