# -*- coding: utf-8 -*-
# config.py – PipeAgent v5.2.12

from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE pairs from a local .env without overriding the process env."""
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key:
                os.environ.setdefault(key, value)
    except OSError:
        return


PROJECT_ROOT = Path(__file__).parent.resolve()
_load_dotenv(PROJECT_ROOT / ".env")

ORG_NAME = "PipeAgent"
APP_NAME = "PipeAgent"
APP_VERSION = "5.2.12"
SUPPORT_EMAIL = ""
WHATSAPP_SUPPORT_PHONE = "+989160684552"
WHATSAPP_SUPPORT_URL = "https://wa.me/989160684552"
WEBSITE = ""
LICENSE_PURCHASE_URL = os.getenv("PIPEAGENT_LICENSE_PURCHASE_URL", "")
BRAND_TAGLINE = "Know What’s Next. Control What Matters."
PRODUCT_POSITIONING = "Piping Execution Operating System"
BRAND_SUPPORT_LINE = "Connect the field. Predict the risk. Control the execution."

DATABASE_NAME = "pipeagent.db"
DATABASE_PATH = PROJECT_ROOT / DATABASE_NAME
CONNECTION_PROFILE_PATH = PROJECT_ROOT / "pipeagent.connection.json"


def get_database_url() -> str:
    """Env URL wins; otherwise the saved profile; otherwise local SQLite."""
    from db.connection_profiles import resolve_database_url

    return resolve_database_url(
        env_url=os.getenv("PIPEAGENT_DATABASE_URL"),
        profile_path=CONNECTION_PROFILE_PATH,
        sqlite_path=DATABASE_PATH,
    )


DATABASE_URL = get_database_url()
DATABASE_URL_LOCKED_BY_ENV = bool(os.getenv("PIPEAGENT_DATABASE_URL", "").strip())

def default_db_path() -> str:
    return str(DATABASE_PATH)

LOG_DIR = PROJECT_ROOT / "logs"
BACKUP_DIR = PROJECT_ROOT / "backups"
EXPORT_DIR = PROJECT_ROOT / "exports"
DOCUMENTS_DIR = PROJECT_ROOT / "documents"
for d in (LOG_DIR, BACKUP_DIR, EXPORT_DIR, DOCUMENTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

LOG_FILE = str(LOG_DIR / "pipeagent.log")
LOG_LEVEL = os.getenv("PIPEAGENT_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_MAX_BYTES = int(os.getenv("PIPEAGENT_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("PIPEAGENT_LOG_BACKUP_COUNT", "5"))
LOG_AS_JSON = os.getenv("PIPEAGENT_LOG_AS_JSON", "false").lower() == "true"
LOG_TO_CONSOLE = os.getenv("PIPEAGENT_LOG_TO_CONSOLE", "true").lower() == "true"

SEARCH_DEBOUNCE_MS = 300
DEFAULT_PAGE_SIZE = 100
AUTO_REFRESH_INTERVAL = 30_000
PASSWORD_MIN_LENGTH = 8
MAX_LOGIN_ATTEMPTS = 5
SESSION_TIMEOUT_MINUTES = 30

@dataclass(frozen=True)
class Roles:
    ADMIN: str = "admin"
    ENGINEER: str = "engineer"
    INSPECTOR: str = "inspector"
    WELDER: str = "welder"
    VIEWER: str = "viewer"
    PROJECT_MANAGER: str = "project_manager"
    PLANNER: str = "planner"
    SUPERVISOR: str = "supervisor"
    STOREKEEPER: str = "storekeeper"
    DOCUMENT_CONTROLLER: str = "document_controller"
    CLIENT_REP: str = "client_rep"

TRIAL_PERIOD_DAYS = 30
MAX_TRIAL_RECORDS = 500
HIDDEN_LICENSE_DIR = os.path.join(os.path.expanduser("~"), ".pipeagent")
HIDDEN_LICENSE_FILE = os.path.join(HIDDEN_LICENSE_DIR, ".license.dat")

PIPING_CODES = [
    "ASME B31.3", "ASME B31.1", "ASME B31.4", "ASME B31.8",
    "EN 13480", "ISO 15614", "API 570", "ASME Section IX",
]

FLUID_SERVICES = [
    "Normal Fluid Service", "Category D Fluid Service", "Category M Fluid Service",
    "High Pressure Fluid Service", "High Purity Fluid Service", "Elevated Temperature Fluid Service",
]

NDT_EXTENT_BY_SERVICE = {
    "Normal Fluid Service": {"RT": 5, "UT": 5, "PT": 100, "MT": 100, "VT": 100},
    "Category D Fluid Service": {"RT": 0, "UT": 0, "PT": 0, "MT": 0, "VT": 100},
    "Category M Fluid Service": {"RT": 20, "UT": 20, "PT": 100, "MT": 100, "VT": 100},
    "High Pressure Fluid Service": {"RT": 100, "UT": 100, "PT": 100, "MT": 100, "VT": 100},
    "High Purity Fluid Service": {"RT": 10, "UT": 10, "PT": 100, "MT": 100, "VT": 100},
    "Elevated Temperature Fluid Service": {"RT": 10, "UT": 10, "PT": 100, "MT": 100, "VT": 100},
}

JOINT_TYPES = ["Butt", "Fillet", "Socket", "Flange", "Branch (Olet)", "Lap"]
WELDING_PROCESSES = ["SMAW", "GTAW", "GMAW", "FCAW", "SAW", "PAW"]
NDT_METHODS = ["VT", "PT", "MT", "RT", "UT", "TOFD", "PAUT"]

WELD_STATUSES = [
    "Pending", "Fit-up", "Welded", "Inspected",
    "Accepted", "Rejected", "Repaired", "Cut-out",
]

SPOOL_STATUSES = [
    "Engineering", "Material Issued", "Prefabrication", "Fabricated",
    "NDT Complete", "Released to Site", "Installed", "Tested",
]

SUPPORT_TYPES = [
    "Shoe", "Guide", "Anchor", "Spring Hanger", "Rigid Hanger",
    "Dummy Leg", "Trunnion", "Saddle", "Clamp", "U-Bolt", "Other",
]

SUPPORT_STATUSES = [
    "Pending", "Fabricated", "Installed", "Inspected", "Accepted", "Rejected",
]

TEST_PACKAGE_STATUSES = [
    "Planned", "Ready for Test", "In Progress",
    "Passed", "Failed", "Re-test Required",
]

HANDOVER_STATUSES = ["In Progress", "Ready", "Accepted", "Rejected"]

DOCUMENT_STATUSES = [
    "Draft", "For Review", "Reviewed", "Approved",
    "Issued for Construction", "As-Built", "Superseded",
]

DOCUMENT_TYPES = [
    "P&ID", "Isometric", "Plot Plan", "General Arrangement", "Piping Layout",
    "Weld Map", "Spool Drawing", "Support Drawing", "Line List",
    "Material Requisition", "MTR", "NDT Report", "WPS", "PQR", "WPQ",
    "WJC", "Hydrotest Certificate", "ITR", "Punch List",
    "As-Built Drawing", "Procedure", "Transmittal", "Handover Dossier", "Other",
]

MATERIAL_TYPES = [
    "Pipe", "Elbow", "Tee", "Reducer", "Cap", "Flange",
    "Gasket", "Bolt/Nut", "Valve", "Olet", "Stub-end",
    "Spectacle Blind", "Spade", "Support", "Gasket Ring", "Other",
]

COMMON_GRADES = [
    "ASTM A106 Gr.B", "ASTM A53 Gr.B", "API 5L Gr.B", "ASTM A333 Gr.6",
    "ASTM A312 TP304/304L", "ASTM A312 TP316/316L",
    "ASTM A335 P11", "ASTM A335 P22", "ASTM A335 P91",
    "ASTM A234 WPB", "ASTM A105", "ASTM A182 F304/F316",
]

FLUID_CODES = [
    "HC", "CR", "CW", "SW", "ST", "SC", "N2", "IA", "IA-I",
    "FG", "FO", "LO", "HO", "DM", "PW", "WW", "CA", "VA", "VE",
]

DEFAULT_THEME = "light"
THEMES = {
    "dark": {"background": "#2b2b2b", "foreground": "#ffffff", "accent": "#0078d7"},
    "light": {"background": "#ffffff", "foreground": "#000000", "accent": "#0078d7"},
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("PIPEAGENT_AI_MODEL", "gpt-4o-mini")
AI_ENABLED = os.getenv("PIPEAGENT_AI_ENABLED", "true").lower() == "true"
AI_MODE = os.getenv("PIPEAGENT_AI_MODE", "hybrid")  # hybrid | local | cloud
AI_TIMEOUT_SECONDS = int(os.getenv("PIPEAGENT_AI_TIMEOUT", "30"))

# Enterprise integration configuration
API_HOST = os.getenv("PIPEAGENT_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("PIPEAGENT_API_PORT", "8765"))
API_ENABLED = os.getenv("PIPEAGENT_API_ENABLED", "true").lower() == "true"
OIDC_ISSUER_URL = os.getenv("PIPEAGENT_OIDC_ISSUER_URL", "")
OIDC_AUDIENCE = os.getenv("PIPEAGENT_OIDC_AUDIENCE", APP_NAME)
OIDC_REQUIRED = os.getenv("PIPEAGENT_OIDC_REQUIRED", "false").lower() == "true"
INTEGRATION_TIMEOUT_SECONDS = int(os.getenv("PIPEAGENT_INTEGRATION_TIMEOUT", "20"))
SYNC_BATCH_SIZE = int(os.getenv("PIPEAGENT_SYNC_BATCH_SIZE", "100"))
BIM_IMPORT_ROOT = Path(os.getenv("PIPEAGENT_BIM_ROOT", str(DOCUMENTS_DIR))).expanduser()
API_TOKEN_PEPPER = os.getenv("PIPEAGENT_API_TOKEN_PEPPER", "")
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("PIPEAGENT_BOOTSTRAP_ADMIN_PASSWORD")
ALLOW_INSECURE_DEFAULTS = os.getenv("PIPEAGENT_ALLOW_INSECURE_DEFAULTS", "true").lower() == "true"
