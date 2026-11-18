"""Policy for preserving imperfect historical MyISAM data during migration."""

ORPHAN_POLICY = "preserve"
POLICY = {
    "orphan_relationships": ORPHAN_POLICY,
    "preserve_source_rows": True,
    "create_tombstone_parents": False,
    "delete_orphan_rows": False,
    "enforce_strict_foreign_keys_on_historical_rows": False,
    "raw_archive_table": "legacy_import_rows",
}