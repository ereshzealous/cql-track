import ssl

from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy

from cqltrack.exceptions import ConfigError


# map config strings to driver constants
_CONSISTENCY_MAP = {
    "ANY": ConsistencyLevel.ANY,
    "ONE": ConsistencyLevel.ONE,
    "TWO": ConsistencyLevel.TWO,
    "THREE": ConsistencyLevel.THREE,
    "QUORUM": ConsistencyLevel.QUORUM,
    "ALL": ConsistencyLevel.ALL,
    "LOCAL_ONE": ConsistencyLevel.LOCAL_ONE,
    "LOCAL_QUORUM": ConsistencyLevel.LOCAL_QUORUM,
    "EACH_QUORUM": ConsistencyLevel.EACH_QUORUM,
    "LOCAL_SERIAL": ConsistencyLevel.LOCAL_SERIAL,
    "SERIAL": ConsistencyLevel.SERIAL,
}


def _resolve_consistency(name):
    name = name.upper()
    if name not in _CONSISTENCY_MAP:
        valid = ", ".join(sorted(_CONSISTENCY_MAP))
        raise ConfigError(
            f"Unknown consistency level '{name}'. "
            f"Valid options: {valid}"
        )
    return _CONSISTENCY_MAP[name]


def _build_ssl_context(config):
    """Build an ssl.SSLContext from config, or return None."""
    if not config.ssl_enabled:
        return None

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    if not config.ssl_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True

    if config.ssl_ca_certs:
        ctx.load_verify_locations(config.ssl_ca_certs)
    if config.ssl_certfile:
        ctx.load_cert_chain(
            certfile=config.ssl_certfile,
            keyfile=config.ssl_keyfile,
        )

    return ctx


def connect(config, use_keyspace=True):
    """Create a Cassandra session from a Config object.

    Supports three modes:
      1. Plain connection (default)
      2. SSL/TLS with certificates
      3. Astra DB via secure connect bundle
    """
    auth = None
    if config.username and config.password:
        auth = PlainTextAuthProvider(
            username=config.username,
            password=config.password,
        )

    # Astra DB — secure connect bundle takes over everything
    if config.secure_connect_bundle:
        cluster = Cluster(
            cloud={"secure_connect_bundle": config.secure_connect_bundle},
            auth_provider=auth,
        )
        session = cluster.connect()
        session.default_consistency_level = _resolve_consistency(config.consistency)
        if use_keyspace:
            session.set_keyspace(config.keyspace)
        return session

    # Standard or SSL connection
    ssl_context = _build_ssl_context(config)

    cluster = Cluster(
        contact_points=config.contact_points,
        port=config.port,
        auth_provider=auth,
        load_balancing_policy=DCAwareRoundRobinPolicy(),
        protocol_version=4,
        connect_timeout=config.connect_timeout,
        ssl_context=ssl_context,
        max_schema_agreement_wait=config.schema_agreement_wait,
    )

    session = cluster.connect()
    session.default_timeout = config.request_timeout
    session.default_consistency_level = _resolve_consistency(config.consistency)

    if use_keyspace:
        session.set_keyspace(config.keyspace)

    return session
