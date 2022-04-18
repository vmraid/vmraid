# Copyright (c) 2020, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.model.utils.rename_field import rename_field


def execute():
	"""
	Change notification recipient fields from email to receiver fields
	"""
	vmraid.reload_doc("Email", "doctype", "Notification Recipient")
	vmraid.reload_doc("Email", "doctype", "Notification")

	rename_field("Notification Recipient", "email_by_document_field", "receiver_by_document_field")
	rename_field("Notification Recipient", "email_by_role", "receiver_by_role")
