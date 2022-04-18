# -*- coding: utf-8 -*-
# Copyright (c) 2020, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid import _
from vmraid.model.document import Document
from vmraid.query_builder import DocType, Interval
from vmraid.query_builder.functions import Now


class LogSettings(Document):
	def clear_logs(self):
		self.clear_error_logs()
		self.clear_activity_logs()
		self.clear_email_queue()

	def clear_error_logs(self):
		table = DocType("Error Log")
		vmraid.db.delete(
			table, filters=(table.creation < (Now() - Interval(days=self.clear_error_log_after)))
		)

	def clear_activity_logs(self):
		from vmraid.core.doctype.activity_log.activity_log import clear_activity_logs

		clear_activity_logs(days=self.clear_activity_log_after)

	def clear_email_queue(self):
		from vmraid.email.queue import clear_outbox

		clear_outbox(days=self.clear_email_queue_after)


def run_log_clean_up():
	doc = vmraid.get_doc("Log Settings")
	doc.clear_logs()


@vmraid.whitelist()
def has_unseen_error_log(user):
	def _get_response(show_alert=True):
		return {
			"show_alert": True,
			"message": _("You have unseen {0}").format(
				'<a href="/app/List/Error%20Log/List"> Error Logs </a>'
			),
		}

	if vmraid.get_all("Error Log", filters={"seen": 0}, limit=1):
		log_settings = vmraid.get_cached_doc("Log Settings")

		if log_settings.users_to_notify:
			if user in [u.user for u in log_settings.users_to_notify]:
				return _get_response()
			else:
				return _get_response(show_alert=False)
		else:
			return _get_response()
