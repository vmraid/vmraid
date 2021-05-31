# -*- coding: utf-8 -*-
# Copyright (c) 2017, VMRaid Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from vmraid import _
from vmraid.utils import get_fullname, now
from vmraid.model.document import Document
from vmraid.core.utils import set_timeline_doc
import vmraid

class ActivityLog(Document):
	def before_insert(self):
		self.full_name = get_fullname(self.user)
		self.date = now()

	def validate(self):
		self.set_status()
		set_timeline_doc(self)

	def set_status(self):
		if not self.is_new():
			return

		if self.reference_doctype and self.reference_name:
			self.status = "Linked"

def on_doctype_update():
	"""Add indexes in `tabActivity Log`"""
	vmraid.db.add_index("Activity Log", ["reference_doctype", "reference_name"])
	vmraid.db.add_index("Activity Log", ["timeline_doctype", "timeline_name"])
	vmraid.db.add_index("Activity Log", ["link_doctype", "link_name"])

def add_authentication_log(subject, user, operation="Login", status="Success"):
	vmraid.get_doc({
		"doctype": "Activity Log",
		"user": user,
		"status": status,
		"subject": subject,
		"operation": operation,
	}).insert(ignore_permissions=True, ignore_links=True)

def clear_activity_logs(days=None):
	"""clear 90 day old authentication logs or configured in log settings"""

	if not days:
		days = 90

	vmraid.db.sql("""delete from `tabActivity Log` where \
		creation< (NOW() - INTERVAL '{0}' DAY)""".format(days))