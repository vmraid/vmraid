# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
import vmraid


def add_custom_field(doctype, fieldname, fieldtype="Data", options=None):
	vmraid.get_doc(
		{
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": fieldname,
			"fieldtype": fieldtype,
			"options": options,
		}
	).insert()


def clear_custom_fields(doctype):
	vmraid.db.delete("Custom Field", {"dt": doctype})
	vmraid.clear_cache(doctype=doctype)
