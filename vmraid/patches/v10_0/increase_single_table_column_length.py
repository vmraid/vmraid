"""
Run this after updating country_info.json and or
"""
import vmraid


def execute():
	for col in ("field", "doctype"):
		vmraid.db.sql_ddl("alter table `tabSingles` modify column `{0}` varchar(255)".format(col))
