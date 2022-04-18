# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	vmraid.reload_doc("core", "doctype", "system_settings", force=1)
	vmraid.db.set_value("System Settings", None, "password_reset_limit", 3)
