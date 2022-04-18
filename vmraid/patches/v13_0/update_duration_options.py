# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	vmraid.reload_doc("core", "doctype", "DocField")

	if vmraid.db.has_column("DocField", "show_days"):
		vmraid.db.sql(
			"""
			UPDATE
				tabDocField
			SET
				hide_days = 1 WHERE show_days = 0
		"""
		)
		vmraid.db.sql_ddl("alter table tabDocField drop column show_days")

	if vmraid.db.has_column("DocField", "show_seconds"):
		vmraid.db.sql(
			"""
			UPDATE
				tabDocField
			SET
				hide_seconds = 1 WHERE show_seconds = 0
		"""
		)
		vmraid.db.sql_ddl("alter table tabDocField drop column show_seconds")

	vmraid.clear_cache(doctype="DocField")
