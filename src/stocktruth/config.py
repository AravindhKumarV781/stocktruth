"""Settings, .env loading and policy loading."""
import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def parse_env_file(p):
    """Return {KEY: value} from an env file. Allows trailing ' # comments'."""
    out = {}
    for line in Path(p).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if " #" in v:
            v = v.split(" #", 1)[0]
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def env_file_path(path=None):
    """Order: explicit path, ENV_FILE, ROOT/.env, ~/stocktruth.env (Cloud Shell)."""
    for c in (path, os.environ.get("ENV_FILE"), ROOT / ".env", Path.home() / "stocktruth.env"):
        if c and Path(c).exists():
            return Path(c)
    return None


def load_env(path=None):
    p = env_file_path(path)
    if p is None:
        return
    for k, v in parse_env_file(p).items():
        os.environ.setdefault(k, v)      # real environment variables (App Service settings) win


def env(name, default=""):
    return os.environ.get(name, default).strip()


class Settings:
    def __init__(self):
        load_env()
        self.data_dir = ROOT / env("DATA_DIR", "data")
        self.knowledge_dir = ROOT / "knowledge"
        self.cctv_dir = ROOT / "cctv"
        state = Path(env("STATE_DIR")) if env("STATE_DIR") else ROOT     # web app: /home/stocktruth_state
        self.out_dir = state / "outputs"
        self.control_dir = state / "control"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.control_dir.mkdir(parents=True, exist_ok=True)

        self.data_backend = env("DATA_BACKEND", "bundled")      # bundled (files shipped with the app) | onelake
        self.fabric_workspace = env("FABRIC_WORKSPACE_ID")
        self.fabric_lakehouse = env("FABRIC_LAKEHOUSE_ID")

        self.llm_mode = env("LLM_MODE", "mock")                  # mock | azure
        self.aoai_endpoint = env("AZURE_OPENAI_ENDPOINT")
        self.aoai_key = env("AZURE_OPENAI_API_KEY")
        self.aoai_api_version = env("AZURE_OPENAI_API_VERSION", "2024-10-21")
        self.deployment = env("MODEL_DEPLOYMENT", "gpt-4.1-mini")
        self.price_in = float(env("PRICE_PER_1M_INPUT_USD", "0.40"))
        self.price_out = float(env("PRICE_PER_1M_OUTPUT_USD", "1.60"))

        self.search_endpoint = env("SEARCH_ENDPOINT")
        self.search_key = env("SEARCH_KEY")
        self.search_index = env("SEARCH_INDEX", "stocktruth-kb")

        self.cosmos_endpoint = env("COSMOS_ENDPOINT")
        self.cosmos_key = env("COSMOS_KEY")
        self.cosmos_db = env("COSMOS_DB", "stocktruth")
        self.cosmos_container = env("COSMOS_CONTAINER", "audit")

        self.cs_endpoint = env("CONTENT_SAFETY_ENDPOINT")
        self.cs_key = env("CONTENT_SAFETY_KEY")

        self.teams_webhook = env("TEAMS_WEBHOOK_URL")
        self.app_url = env("APP_URL", "")

        self.cctv_window_min = float(env("CCTV_WINDOW_MIN", "30"))
        self.cctv_min_conf = float(env("CCTV_MIN_CONF", "0.6"))


def load_policy(path=None):
    p = Path(path) if path else ROOT / "config" / "policy.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def to_native(o):
    """json default= helper for numpy / pandas types."""
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def dumps(obj, **kw):
    return json.dumps(obj, default=to_native, ensure_ascii=False, **kw)
