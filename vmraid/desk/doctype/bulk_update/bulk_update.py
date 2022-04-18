# -*- coding: utf-8 -*-
# Copyright (c) 2015, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid import _
from vmraid.model.document import Document
from vmraid.utils import cint


class BulkUpdate(Document):
	pass


@vmraid.whitelist()
def update(doctype, field, value, condition="", limit=500):
	if not limit or cint(limit) > 500:
		limit = 500

	if condition:
		condition = " where " + condition

	if ";" in condition:
		vmraid.throw(_("; not allowed in condition"))

	docnames = vmraid.db.sql_list(
		"""select name from `tab{0}`{1} limit {2} offset 0""".format(doctype, condition, limit)
	)
	data = {}
	data[field] = value
	return submit_cancel_or_update_docs(doctype, docnames, "update", data)


@vmraid.whitelist()
def submit_cancel_or_update_docs(doctype, docnames, action="submit", data=None):
	docnames = vmraid.parse_json(docnames)

	if data:
		data = vmraid.parse_json(data)

	failed = []

	for i, d in enumerate(docnames, 1):
		doc = vmraid.get_doc(doctype, d)
		try:
			message = ""
			if action == "submit" and doc.docstatus.is_draft():
				doc.submit()
				message = _("Submitting {0}").format(doctype)
			elif action == "cancel" and doc.docstatus.is_submitted():
				doc.cancel()
				message = _("Cancelling {0}").format(doctype)
			elif action == "update" and not doc.docstatus.is_cancelled():
				doc.update(data)
				doc.save()
				message = _("Updating {0}").format(doctype)
			else:
				failed.append(d)
			vmraid.db.commit()
			show_progress(docnames, message, i, d)

		except Exception:
			failed.append(d)
			vmraid.db.rollback()

	return failed


def show_progress(docnames, message, i, description):
	n = len(docnames)
	if n >= 10:
		vmraid.publish_progress(float(i) * 100 / n, title=message, description=description)
