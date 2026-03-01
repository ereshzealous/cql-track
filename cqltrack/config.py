import os
from pathlib import Path

import yaml

from cqltrack.exceptions import ConfigError


_DEFAULTS = {
    "contact_points": ["127.0.0.1"],
    "port": 9042,
    "keyspace": "my_app",
    "username": None,
    "password": None,
    "consistency": "LOCAL_ONE",
    "replication": {"class": "SimpleStrategy", "replication_factor": 1},
    "migration_dir": "migrations",
    "lock_ttl": 600,
    "schema_agreement_wait": 30,
    "connect_timeout": 10,
    "request_timeout": 30,
    "ssl_enabled": False,
    "ssl_ca_certs": None,
    "ssl_certfile": None,
    "ssl_keyfile": None,
    "ssl_verify": True,
    "secure_connect_bundle": None,
}


class Config:

    def __init__(self, **overrides):
        merged = {**_DEFAULTS, **overrides}
        self.contact_points = merged["contact_points"]
        self.port = int(merged["port"])
        self.keyspace = merged["keyspace"]
        self.username = merged["username"]
        self.password = merged["password"]
        self.consistency = merged["consistency"].upper()
        self.replication = merged["replication"]
        self.migration_dir = Path(merged["migration_dir"])
        self.lock_ttl = int(merged["lock_ttl"])
        self.schema_agreement_wait = int(merged["schema_agreement_wait"])
        self.connect_timeout = int(merged["connect_timeout"])
        self.request_timeout = int(merged["request_timeout"])
        self.ssl_enabled = bool(merged["ssl_enabled"])
        self.ssl_ca_certs = merged["ssl_ca_certs"]
        self.ssl_certfile = merged["ssl_certfile"]
        self.ssl_keyfile = merged["ssl_keyfile"]
        self.ssl_verify = bool(merged["ssl_verify"])
        self.secure_connect_bundle = merged["secure_connect_bundle"]

    @classmethod
    def load(cls, path=None, profile=None):
        """Load from YAML file with optional profile and env-var overrides.

        Resolution order (last wins):
          1. built-in defaults
          2. top-level YAML values
          3. profile-specific overrides
          4. CQLTRACK_* environment variables
        """
        if path is None:
            path = Path("cqltrack.yml")
        else:
            path = Path(path)

        flat = {}

        if path.exists():
            with open(path) as fh:
                raw = yaml.safe_load(fh) or {}

            # base config from top-level keys
            flat = cls._flatten(raw)

            # layer profile overrides on top
            if profile:
                profiles = raw.get("profiles", {})
                if not isinstance(profiles, dict) or profile not in profiles:
                    available = list(profiles.keys()) if isinstance(profiles, dict) else []
                    raise ConfigError(
                        f"Profile '{profile}' not found. "
                        f"Available: {', '.join(available) or 'none'}"
                    )
                profile_flat = cls._flatten(profiles[profile])
                flat.update(profile_flat)

        # env always wins
        cls._apply_env(flat)

        return cls(**flat)

    @classmethod
    def available_profiles(cls, path=None):
        """List profile names defined in the config file."""
        if path is None:
            path = Path("cqltrack.yml")
        else:
            path = Path(path)

        if not path.exists():
            return []

        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}

        profiles = raw.get("profiles", {})
        return list(profiles.keys()) if isinstance(profiles, dict) else []

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _flatten(raw):
        """Turn the nested YAML structure into our flat kwargs dict."""
        out = {}

        cassandra = raw.get("cassandra", {})
        if isinstance(cassandra, dict):
            for key in ("contact_points", "port", "consistency",
                        "connect_timeout", "request_timeout"):
                if key in cassandra:
                    out[key] = cassandra[key]
            auth = cassandra.get("auth", {})
            if isinstance(auth, dict):
                out["username"] = auth.get("username")
                out["password"] = auth.get("password")

            # SSL / TLS
            ssl = cassandra.get("ssl", {})
            if isinstance(ssl, dict):
                if "enabled" in ssl:
                    out["ssl_enabled"] = ssl["enabled"]
                if "ca_certs" in ssl:
                    out["ssl_ca_certs"] = ssl["ca_certs"]
                if "certfile" in ssl:
                    out["ssl_certfile"] = ssl["certfile"]
                if "keyfile" in ssl:
                    out["ssl_keyfile"] = ssl["keyfile"]
                if "verify" in ssl:
                    out["ssl_verify"] = ssl["verify"]

            # Astra secure connect bundle
            if "secure_connect_bundle" in cassandra:
                out["secure_connect_bundle"] = cassandra["secure_connect_bundle"]

        ks = raw.get("keyspace", {})
        if isinstance(ks, dict):
            if "name" in ks:
                out["keyspace"] = ks["name"]
            if "replication" in ks:
                out["replication"] = ks["replication"]
        elif isinstance(ks, str):
            out["keyspace"] = ks

        migrations = raw.get("migrations", {})
        if isinstance(migrations, dict) and "directory" in migrations:
            out["migration_dir"] = migrations["directory"]

        lock = raw.get("lock", {})
        if isinstance(lock, dict) and "ttl" in lock:
            out["lock_ttl"] = lock["ttl"]

        schema = raw.get("schema", {})
        if isinstance(schema, dict) and "agreement_wait" in schema:
            out["schema_agreement_wait"] = schema["agreement_wait"]

        return out

    @staticmethod
    def _apply_env(flat):
        """Override config from CQLTRACK_* environment variables."""
        if os.environ.get("CQLTRACK_CONTACT_POINTS"):
            flat["contact_points"] = os.environ["CQLTRACK_CONTACT_POINTS"].split(",")
        if os.environ.get("CQLTRACK_KEYSPACE"):
            flat["keyspace"] = os.environ["CQLTRACK_KEYSPACE"]
        if os.environ.get("CQLTRACK_PORT"):
            flat["port"] = int(os.environ["CQLTRACK_PORT"])
        if os.environ.get("CQLTRACK_USERNAME"):
            flat["username"] = os.environ["CQLTRACK_USERNAME"]
        if os.environ.get("CQLTRACK_PASSWORD"):
            flat["password"] = os.environ["CQLTRACK_PASSWORD"]
        if os.environ.get("CQLTRACK_CONSISTENCY"):
            flat["consistency"] = os.environ["CQLTRACK_CONSISTENCY"]
        if os.environ.get("CQLTRACK_SECURE_CONNECT_BUNDLE"):
            flat["secure_connect_bundle"] = os.environ["CQLTRACK_SECURE_CONNECT_BUNDLE"]
