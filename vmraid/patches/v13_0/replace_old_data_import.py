# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	if not vmraid.db.table_exists("Data Import"):
		return

	meta = vmraid.get_meta("Data Import")
	# if Data Import is the new one, return early
	if meta.fields[1].fieldname == "import_type":
		return

	vmraid.db.sql("DROP TABLE IF EXISTS `tabData Import Legacy`")
	vmraid.rename_doc("DocType", "Data Import", "Data Import Legacy")
	vmraid.db.commit()
	vmraid.db.sql("DROP TABLE IF EXISTS `tabData Import`")
	vmraid.rename_doc("DocType", "Data Import Beta", "Data Import")
