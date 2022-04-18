# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	if vmraid.db.exists("DocType", "Event Producer"):
		vmraid.db.sql("""UPDATE `tabEvent Producer` SET api_key='', api_secret=''""")
	if vmraid.db.exists("DocType", "Event Consumer"):
		vmraid.db.sql("""UPDATE `tabEvent Consumer` SET api_key='', api_secret=''""")
