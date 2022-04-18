# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
import re

import vmraid
from vmraid import _
from vmraid.rate_limiter import rate_limit
from vmraid.utils import add_to_date, now
from vmraid.utils.html_utils import clean_html
from vmraid.website.doctype.blog_settings.blog_settings import get_comment_limit
from vmraid.website.utils import clear_cache


@vmraid.whitelist(allow_guest=True)
@rate_limit(key="reference_name", limit=get_comment_limit, seconds=60 * 60)
def add_comment(comment, comment_email, comment_by, reference_doctype, reference_name, route):
	doc = vmraid.get_doc(reference_doctype, reference_name)

	if vmraid.session.user == "Guest" and doc.doctype not in ["Blog Post", "Web Page"]:
		return

	if not comment.strip():
		vmraid.msgprint(_("The comment cannot be empty"))
		return False

	url_regex = re.compile(
		r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", re.IGNORECASE
	)
	email_regex = re.compile(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)", re.IGNORECASE)

	if url_regex.search(comment) or email_regex.search(comment):
		vmraid.msgprint(_("Comments cannot have links or email addresses"))
		return False

	comment = doc.add_comment(
		text=clean_html(comment), comment_email=comment_email, comment_by=comment_by
	)

	comment.db_set("published", 1)

	# since comments are embedded in the page, clear the web cache
	if route:
		clear_cache(route)

	content = (
		comment.content
		+ "<p><a href='{0}/app/Form/Comment/{1}' style='font-size: 80%'>{2}</a></p>".format(
			vmraid.utils.get_request_site_address(), comment.name, _("View Comment")
		)
	)

	if doc.doctype == "Blog Post" and not doc.enable_email_notification:
		pass
	else:
		# notify creator
		vmraid.sendmail(
			recipients=vmraid.db.get_value("User", doc.owner, "email") or doc.owner,
			subject=_("New Comment on {0}: {1}").format(doc.doctype, doc.name),
			message=content,
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)

	# revert with template if all clear (no backlinks)
	template = vmraid.get_template("templates/includes/comments/comment.html")
	return template.render({"comment": comment.as_dict()})
