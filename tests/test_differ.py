from types import SimpleNamespace

from cqltrack.differ import SchemaDiffer


def _col(name, cql_type="text"):
    return SimpleNamespace(name=name, cql_type=cql_type)


def _table(columns, partition_key=None, clustering_key=None, indexes=None,
           clustering_order=None):
    cols = {c.name: c for c in columns}
    return SimpleNamespace(
        columns=cols,
        partition_key=partition_key or [columns[0]],
        clustering_key=clustering_key or [],
        clustering_order=clustering_order or {},
        indexes=indexes or {},
    )


def _keyspace(tables=None, user_types=None):
    return SimpleNamespace(
        tables=tables or {},
        user_types=user_types or {},
    )


def _udt(field_names, field_types):
    return SimpleNamespace(field_names=field_names, field_types=field_types)


class TestTableDiff:

    def test_identical_schemas(self):
        t = _table([_col("id", "uuid"), _col("name")])
        src = _keyspace({"users": t})
        tgt = _keyspace({"users": t})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        assert diffs == []

    def test_table_only_in_source(self):
        src = _keyspace({"users": _table([_col("id")])})
        tgt = _keyspace({})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        assert len(diffs) == 1
        assert diffs[0].kind == "table"
        assert diffs[0].change == "only_in_source"
        assert diffs[0].path == "users"

    def test_table_only_in_target(self):
        src = _keyspace({})
        tgt = _keyspace({"orders": _table([_col("id")])})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        assert len(diffs) == 1
        assert diffs[0].change == "only_in_target"

    def test_skips_internal_tables(self):
        src = _keyspace({
            "users": _table([_col("id")]),
            "cqltrack_history": _table([_col("version", "int")]),
        })
        tgt = _keyspace({"users": _table([_col("id")])})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        assert diffs == []


class TestColumnDiff:

    def test_column_only_in_source(self):
        src = _keyspace({"t": _table([_col("id"), _col("email")])})
        tgt = _keyspace({"t": _table([_col("id")])})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        col_diffs = [d for d in diffs if d.kind == "column"]
        assert len(col_diffs) == 1
        assert col_diffs[0].path == "t.email"
        assert col_diffs[0].change == "only_in_source"

    def test_column_only_in_target(self):
        src = _keyspace({"t": _table([_col("id")])})
        tgt = _keyspace({"t": _table([_col("id"), _col("phone")])})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        col_diffs = [d for d in diffs if d.kind == "column"]
        assert len(col_diffs) == 1
        assert col_diffs[0].path == "t.phone"
        assert col_diffs[0].change == "only_in_target"

    def test_column_type_mismatch(self):
        src = _keyspace({"t": _table([_col("id"), _col("age", "int")])})
        tgt = _keyspace({"t": _table([_col("id"), _col("age", "bigint")])})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        col_diffs = [d for d in diffs if d.kind == "column"]
        assert len(col_diffs) == 1
        assert col_diffs[0].change == "type_mismatch"
        assert col_diffs[0].left == "int"
        assert col_diffs[0].right == "bigint"


class TestPartitionKeyDiff:

    def test_same_pk(self):
        pk_col = _col("id", "uuid")
        src = _keyspace({"t": _table([pk_col, _col("name")], partition_key=[pk_col])})
        tgt = _keyspace({"t": _table([pk_col, _col("name")], partition_key=[pk_col])})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        pk_diffs = [d for d in diffs if d.kind == "pk"]
        assert pk_diffs == []

    def test_different_pk(self):
        id_col = _col("id", "uuid")
        ts_col = _col("ts", "timestamp")
        src = _keyspace({"t": _table([id_col, ts_col], partition_key=[id_col])})
        tgt = _keyspace({"t": _table([id_col, ts_col], partition_key=[id_col, ts_col])})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        pk_diffs = [d for d in diffs if d.kind == "pk"]
        assert len(pk_diffs) == 1
        assert "(id)" in pk_diffs[0].left
        assert "(id, ts)" in pk_diffs[0].right


class TestIndexDiff:

    def test_index_only_in_source(self):
        src = _keyspace({"t": _table(
            [_col("id")],
            indexes={"idx_email": True},
        )})
        tgt = _keyspace({"t": _table([_col("id")])})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        idx_diffs = [d for d in diffs if d.kind == "index"]
        assert len(idx_diffs) == 1
        assert idx_diffs[0].path == "t.idx_email"

    def test_index_only_in_target(self):
        src = _keyspace({"t": _table([_col("id")])})
        tgt = _keyspace({"t": _table(
            [_col("id")],
            indexes={"idx_name": True},
        )})
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        idx_diffs = [d for d in diffs if d.kind == "index"]
        assert len(idx_diffs) == 1
        assert idx_diffs[0].change == "only_in_target"


class TestUDTDiff:

    def test_udt_only_in_source(self):
        src = _keyspace(user_types={"address": _udt(["street"], ["text"])})
        tgt = _keyspace()
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        assert len(diffs) == 1
        assert diffs[0].kind == "udt"
        assert diffs[0].change == "only_in_source"

    def test_udt_field_type_mismatch(self):
        src = _keyspace(user_types={
            "address": _udt(["zip"], ["int"]),
        })
        tgt = _keyspace(user_types={
            "address": _udt(["zip"], ["text"]),
        })
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        assert len(diffs) == 1
        assert diffs[0].kind == "udt_field"
        assert diffs[0].change == "type_mismatch"

    def test_udt_extra_field(self):
        src = _keyspace(user_types={
            "address": _udt(["street", "city"], ["text", "text"]),
        })
        tgt = _keyspace(user_types={
            "address": _udt(["street"], ["text"]),
        })
        diffs = SchemaDiffer(src, tgt, "a", "b").diff()
        assert len(diffs) == 1
        assert diffs[0].path == "address.city"


class TestMixedDiff:

    def test_multiple_differences(self):
        src = _keyspace({
            "users": _table([_col("id"), _col("email"), _col("age", "int")]),
            "sessions": _table([_col("id")]),
        })
        tgt = _keyspace({
            "users": _table([_col("id"), _col("email"), _col("age", "bigint"), _col("phone")]),
            "orders": _table([_col("id")]),
        })
        diffs = SchemaDiffer(src, tgt, "dev", "staging").diff()

        kinds = [d.kind for d in diffs]
        assert "table" in kinds    # sessions / orders
        assert "column" in kinds   # age mismatch, phone
        assert len(diffs) >= 4
