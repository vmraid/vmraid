# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	"""Enable all the existing Client script"""

	vmraid.db.sql(
		"""
		UPDATE `tabClient Script` SET enabled=1
	"""
	)
