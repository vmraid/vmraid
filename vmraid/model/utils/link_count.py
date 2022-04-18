# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid

ignore_doctypes = ("DocType", "Print Format", "Role", "Module Def", "Communication", "ToDo")


def notify_link_count(doctype, name):
	"""updates link count for given document"""
	if hasattr(vmraid.local, "link_count"):
		if (doctype, name) in vmraid.local.link_count:
			vmraid.local.link_count[(doctype, name)] += 1
		else:
			vmraid.local.link_count[(doctype, name)] = 1


def flush_local_link_count():
	"""flush from local before ending request"""
	if not getattr(vmraid.local, "link_count", None):
		return

	link_count = vmraid.cache().get_value("_link_count")
	if not link_count:
		link_count = {}

		for key, value in vmraid.local.link_count.items():
			if key in link_count:
				link_count[key] += vmraid.local.link_count[key]
			else:
				link_count[key] = vmraid.local.link_count[key]

	vmraid.cache().set_value("_link_count", link_count)


def update_link_count():
	"""increment link count in the `idx` column for the given document"""
	link_count = vmraid.cache().get_value("_link_count")

	if link_count:
		for key, count in link_count.items():
			if key[0] not in ignore_doctypes:
				try:
					vmraid.db.sql(
						"update `tab{0}` set idx = idx + {1} where name=%s".format(key[0], count),
						key[1],
						auto_commit=1,
					)
				except Exception as e:
					if not vmraid.db.is_table_missing(e):  # table not found, single
						raise e
	# reset the count
	vmraid.cache().delete_value("_link_count")
