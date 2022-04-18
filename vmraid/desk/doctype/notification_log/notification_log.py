# -*- coding: utf-8 -*-
# Copyright (c) 2019, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid import _
from vmraid.desk.doctype.notification_settings.notification_settings import (
	is_email_notifications_enabled_for_type,
	is_notifications_enabled,
	set_seen_value,
)
from vmraid.model.document import Document


class NotificationLog(Document):
	def after_insert(self):
		vmraid.publish_realtime("notification", after_commit=True, user=self.for_user)
		set_notifications_as_unseen(self.for_user)
		if is_email_notifications_enabled_for_type(self.for_user, self.type):
			try:
				send_notification_email(self)
			except vmraid.OutgoingEmailError:
				vmraid.log_error(message=vmraid.get_traceback(), title=_("Failed to send notification email"))


def get_permission_query_conditions(for_user):
	if not for_user:
		for_user = vmraid.session.user

	if for_user == "Administrator":
		return

	return """(`tabNotification Log`.for_user = '{user}')""".format(user=for_user)


def get_title(doctype, docname, title_field=None):
	if not title_field:
		title_field = vmraid.get_meta(doctype).get_title_field()
	title = docname if title_field == "name" else vmraid.db.get_value(doctype, docname, title_field)
	return title


def get_title_html(title):
	return '<b class="subject-title">{0}</b>'.format(title)


def enqueue_create_notification(users, doc):
	"""
	During installation of new site, enqueue_create_notification tries to connect to Redis.
	This breaks new site creation if Redis server is not running.
	We do not need any notifications in fresh installation
	"""
	if vmraid.flags.in_install:
		return

	doc = vmraid._dict(doc)

	if isinstance(users, str):
		users = [user.strip() for user in users.split(",") if user.strip()]
	users = list(set(users))

	vmraid.enqueue(
		"vmraid.desk.doctype.notification_log.notification_log.make_notification_logs",
		doc=doc,
		users=users,
		now=vmraid.flags.in_test,
	)


def make_notification_logs(doc, users):
	from vmraid.social.doctype.energy_point_settings.energy_point_settings import (
		is_energy_point_enabled,
	)

	for user in users:
		if vmraid.db.exists("User", {"email": user, "enabled": 1}):
			if is_notifications_enabled(user):
				if doc.type == "Energy Point" and not is_energy_point_enabled():
					return

				_doc = vmraid.new_doc("Notification Log")
				_doc.update(doc)
				_doc.for_user = user
				if _doc.for_user != _doc.from_user or doc.type == "Energy Point" or doc.type == "Alert":
					_doc.insert(ignore_permissions=True)


def send_notification_email(doc):

	if doc.type == "Energy Point" and doc.email_content is None:
		return

	from vmraid.utils import get_url_to_form, strip_html

	doc_link = get_url_to_form(doc.document_type, doc.document_name)
	header = get_email_header(doc)
	email_subject = strip_html(doc.subject)

	vmraid.sendmail(
		recipients=doc.for_user,
		subject=email_subject,
		template="new_notification",
		args={
			"body_content": doc.subject,
			"description": doc.email_content,
			"document_type": doc.document_type,
			"document_name": doc.document_name,
			"doc_link": doc_link,
		},
		header=[header, "orange"],
		now=vmraid.flags.in_test,
	)


def get_email_header(doc):
	docname = doc.document_name
	header_map = {
		"Default": _("New Notification"),
		"Mention": _("New Mention on {0}").format(docname),
		"Assignment": _("Assignment Update on {0}").format(docname),
		"Share": _("New Document Shared {0}").format(docname),
		"Energy Point": _("Energy Point Update on {0}").format(docname),
	}

	return header_map[doc.type or "Default"]


@vmraid.whitelist()
def mark_all_as_read():
	unread_docs_list = vmraid.db.get_all(
		"Notification Log", filters={"read": 0, "for_user": vmraid.session.user}
	)
	unread_docnames = [doc.name for doc in unread_docs_list]
	if unread_docnames:
		filters = {"name": ["in", unread_docnames]}
		vmraid.db.set_value("Notification Log", filters, "read", 1, update_modified=False)


@vmraid.whitelist()
def mark_as_read(docname):
	if docname:
		vmraid.db.set_value("Notification Log", docname, "read", 1, update_modified=False)


@vmraid.whitelist()
def trigger_indicator_hide():
	vmraid.publish_realtime("indicator_hide", user=vmraid.session.user)


def set_notifications_as_unseen(user):
	try:
		vmraid.db.set_value("Notification Settings", user, "seen", 0)
	except vmraid.DoesNotExistError:
		return
