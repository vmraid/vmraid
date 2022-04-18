# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
from __future__ import unicode_literals

import vmraid
from vmraid import _
from vmraid.rate_limiter import rate_limit
from vmraid.website.doctype.blog_settings.blog_settings import get_feedback_limit


@vmraid.whitelist(allow_guest=True)
@rate_limit(key="reference_name", limit=get_feedback_limit, seconds=60 * 60)
def give_feedback(reference_doctype, reference_name, like):
	like = vmraid.parse_json(like)
	ref_doc = vmraid.get_doc(reference_doctype, reference_name)
	if ref_doc.disable_feedback == 1:
		return

	filters = {
		"owner": vmraid.session.user,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
	}
	d = vmraid.get_all("Feedback", filters=filters, limit=1)
	if d:
		doc = vmraid.get_doc("Feedback", d[0].name)
	else:
		doc = doc = vmraid.new_doc("Feedback")
		doc.reference_doctype = reference_doctype
		doc.reference_name = reference_name
		doc.ip_address = vmraid.local.request_ip
	doc.like = like
	doc.save(ignore_permissions=True)

	subject = _("Feedback on {0}: {1}").format(reference_doctype, reference_name)
	ref_doc.enable_email_notification and send_mail(doc, subject)
	return doc


def send_mail(feedback, subject):
	doc = vmraid.get_doc(feedback.reference_doctype, feedback.reference_name)
	if feedback.like:
		message = "<p>Hey, </p><p>You have received a ❤️ heart on your blog post <b>{0}</b></p>".format(
			feedback.reference_name
		)
	else:
		return

	# notify creator
	vmraid.sendmail(
		recipients=vmraid.db.get_value("User", doc.owner, "email") or doc.owner,
		subject=subject,
		message=message,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)
