# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	if vmraid.db.exists("DocType", "Onboarding"):
		vmraid.rename_doc("DocType", "Onboarding", "Module Onboarding", ignore_if_exists=True)
