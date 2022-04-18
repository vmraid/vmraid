# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE


import vmraid
from vmraid.model import data_field_options


def execute():
	custom_field = vmraid.qb.DocType("Custom Field")
	(
		vmraid.qb.update(custom_field)
		.set(custom_field.options, None)
		.where((custom_field.fieldtype == "Data") & (custom_field.options.notin(data_field_options)))
	).run()
