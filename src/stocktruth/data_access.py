"""Data layer. Same tables, two backends: local CSV folder, or Fabric OneLake (Lakehouse Files)."""
import io
import re

import pandas as pd

TABLES = ["products", "suppliers", "locations", "pos_sales", "grn", "returns", "wms_moves",
          "adjustments", "pick_exceptions", "stock_counts", "golden_cases"]
GUID = re.compile(r"^[0-9a-fA-F-]{36}$")


def get_credential():
    """Azure CLI login first (this is what Cloud Shell has), then the default chain (managed identity, env)."""
    from azure.identity import AzureCliCredential, ChainedTokenCredential, DefaultAzureCredential
    return ChainedTokenCredential(AzureCliCredential(), DefaultAzureCredential())


class DataStore:
    def __init__(self, tables):
        self.t = tables
        self._products = tables["products"].set_index("sku")
        self._suppliers = tables["suppliers"].set_index("supplier_id")

    @classmethod
    def load(cls, settings):
        if settings.data_backend == "onelake":
            tables = cls._load_onelake(settings)
        else:
            tables = {n: pd.read_csv(settings.data_dir / f"{n}.csv") for n in TABLES
                      if (settings.data_dir / f"{n}.csv").exists()}
        return cls(tables)

    @staticmethod
    def _load_onelake(s):
        from azure.storage.filedatalake import DataLakeServiceClient
        svc = DataLakeServiceClient("https://onelake.dfs.fabric.microsoft.com", credential=get_credential())
        fs = svc.get_file_system_client(s.fabric_workspace)
        lh = s.fabric_lakehouse
        base = f"{lh}/Files/stocktruth/data" if GUID.match(lh) else f"{lh}.Lakehouse/Files/stocktruth/data"
        out = {}
        for n in TABLES:
            try:
                raw = fs.get_file_client(f"{base}/{n}.csv").download_file().readall()
                out[n] = pd.read_csv(io.BytesIO(raw))
            except Exception as e:
                if n == "golden_cases":
                    continue
                raise RuntimeError(f"OneLake read failed for {n}.csv: {e}") from e
        return out

    # ---- helpers
    def product(self, sku):
        r = self._products.loc[sku]
        return dict(sku=sku, name=r["name"], category=r["category"], unit_cost=float(r["unit_cost"]),
                    unit_price=float(r["unit_price"]), supplier_id=r["supplier_id"])

    def supplier(self, supplier_id):
        r = self._suppliers.loc[supplier_id]
        return dict(supplier_id=supplier_id, name=r["name"], short_tolerance_pct=float(r["short_tolerance_pct"]),
                    claim_window_days=int(r["claim_window_days"]), claim_email=r["claim_email"])

    def rows(self, table, location=None, sku=None):
        df = self.t[table]
        if location is not None:
            df = df[df["location"] == location]
        if sku is not None:
            df = df[df["sku"] == sku]
        return df
