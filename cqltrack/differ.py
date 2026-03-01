from dataclasses import dataclass


# don't diff our own tracking tables
_INTERNAL = {"cqltrack_history", "cqltrack_lock"}


@dataclass
class Difference:
    kind: str       # table, column, index, udt, udt_field, pk, ck
    path: str       # "users", "users.email", etc.
    change: str     # only_in_source, only_in_target, type_mismatch, differs
    left: str
    right: str


class SchemaDiffer:
    """Compare two KeyspaceMetadata objects from the DataStax driver."""

    def __init__(self, source_meta, target_meta, source_label, target_label):
        self.source = source_meta
        self.target = target_meta
        self.source_label = source_label
        self.target_label = target_label

    def diff(self):
        results = []
        results.extend(self._diff_tables())
        results.extend(self._diff_user_types())
        return results

    # -- tables --------------------------------------------------------------

    def _diff_tables(self):
        results = []
        src = {n for n in self.source.tables if n not in _INTERNAL}
        tgt = {n for n in self.target.tables if n not in _INTERNAL}

        for name in sorted(src - tgt):
            results.append(Difference(
                "table", name, "only_in_source", "exists", "missing",
            ))

        for name in sorted(tgt - src):
            results.append(Difference(
                "table", name, "only_in_target", "missing", "exists",
            ))

        for name in sorted(src & tgt):
            results.extend(self._diff_one_table(name))

        return results

    def _diff_one_table(self, name):
        results = []
        src_t = self.source.tables[name]
        tgt_t = self.target.tables[name]

        # partition key
        src_pk = [c.name for c in src_t.partition_key]
        tgt_pk = [c.name for c in tgt_t.partition_key]
        if src_pk != tgt_pk:
            results.append(Difference(
                "pk", name, "differs",
                f"({', '.join(src_pk)})",
                f"({', '.join(tgt_pk)})",
            ))

        # clustering key + order
        src_ck = self._clustering_desc(src_t)
        tgt_ck = self._clustering_desc(tgt_t)
        if src_ck != tgt_ck:
            results.append(Difference(
                "ck", name, "differs",
                src_ck or "(none)",
                tgt_ck or "(none)",
            ))

        # columns
        src_cols = src_t.columns
        tgt_cols = tgt_t.columns

        for col in sorted(set(src_cols) - set(tgt_cols)):
            results.append(Difference(
                "column", f"{name}.{col}", "only_in_source",
                _col_type(src_cols[col]), "missing",
            ))

        for col in sorted(set(tgt_cols) - set(src_cols)):
            results.append(Difference(
                "column", f"{name}.{col}", "only_in_target",
                "missing", _col_type(tgt_cols[col]),
            ))

        for col in sorted(set(src_cols) & set(tgt_cols)):
            st = _col_type(src_cols[col])
            tt = _col_type(tgt_cols[col])
            if st != tt:
                results.append(Difference(
                    "column", f"{name}.{col}", "type_mismatch", st, tt,
                ))

        # indexes
        src_idx = set(src_t.indexes or {})
        tgt_idx = set(tgt_t.indexes or {})

        for idx in sorted(src_idx - tgt_idx):
            results.append(Difference(
                "index", f"{name}.{idx}", "only_in_source",
                "exists", "missing",
            ))

        for idx in sorted(tgt_idx - src_idx):
            results.append(Difference(
                "index", f"{name}.{idx}", "only_in_target",
                "missing", "exists",
            ))

        return results

    # -- user-defined types --------------------------------------------------

    def _diff_user_types(self):
        results = []
        src_types = set(self.source.user_types or {})
        tgt_types = set(self.target.user_types or {})

        for name in sorted(src_types - tgt_types):
            results.append(Difference(
                "udt", name, "only_in_source", "exists", "missing",
            ))

        for name in sorted(tgt_types - src_types):
            results.append(Difference(
                "udt", name, "only_in_target", "missing", "exists",
            ))

        for name in sorted(src_types & tgt_types):
            results.extend(self._diff_udt_fields(name))

        return results

    def _diff_udt_fields(self, type_name):
        results = []
        src_ut = self.source.user_types[type_name]
        tgt_ut = self.target.user_types[type_name]

        src_fields = dict(zip(src_ut.field_names, [str(t) for t in src_ut.field_types]))
        tgt_fields = dict(zip(tgt_ut.field_names, [str(t) for t in tgt_ut.field_types]))

        for f in sorted(set(src_fields) - set(tgt_fields)):
            results.append(Difference(
                "udt_field", f"{type_name}.{f}", "only_in_source",
                src_fields[f], "missing",
            ))

        for f in sorted(set(tgt_fields) - set(src_fields)):
            results.append(Difference(
                "udt_field", f"{type_name}.{f}", "only_in_target",
                "missing", tgt_fields[f],
            ))

        for f in sorted(set(src_fields) & set(tgt_fields)):
            if src_fields[f] != tgt_fields[f]:
                results.append(Difference(
                    "udt_field", f"{type_name}.{f}", "type_mismatch",
                    src_fields[f], tgt_fields[f],
                ))

        return results

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _clustering_desc(table_meta):
        """Describe clustering columns and their sort order."""
        if not table_meta.clustering_key:
            return ""
        parts = []
        for col in table_meta.clustering_key:
            order = table_meta.clustering_order.get(col.name, "ASC") \
                if hasattr(table_meta, "clustering_order") else "ASC"
            parts.append(f"{col.name} {order}")
        return ", ".join(parts)


def _col_type(column_meta):
    """Get a string representation of a column's CQL type."""
    return str(column_meta.cql_type)
