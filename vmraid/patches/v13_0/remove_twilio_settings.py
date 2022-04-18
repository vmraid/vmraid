# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	"""Add missing Twilio patch.

	While making Twilio as a standaone app, we missed to delete Twilio records from DB through migration. Adding the missing patch.
	"""
	vmraid.delete_doc_if_exists("DocType", "Twilio Number Group")
	if twilio_settings_doctype_in_integrations():
		vmraid.delete_doc_if_exists("DocType", "Twilio Settings")
		vmraid.db.delete("Singles", {"doctype": "Twilio Settings"})


def twilio_settings_doctype_in_integrations() -> bool:
	"""Check Twilio Settings doctype exists in integrations module or not."""
	return vmraid.db.exists("DocType", {"name": "Twilio Settings", "module": "Integrations"})
