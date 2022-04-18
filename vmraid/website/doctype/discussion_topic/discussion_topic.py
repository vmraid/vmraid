# Copyright (c) 2021, FOSS United and contributors
# For license information, please see license.txt

import vmraid
from vmraid.model.document import Document


class DiscussionTopic(Document):
	pass


@vmraid.whitelist()
def submit_discussion(doctype, docname, reply, title, topic_name=None, reply_name=None):

	if reply_name:
		doc = vmraid.get_doc("Discussion Reply", reply_name)
		doc.reply = reply
		doc.save(ignore_permissions=True)
		return

	if topic_name:
		save_message(reply, topic_name)
		return topic_name

	topic = vmraid.get_doc(
		{
			"doctype": "Discussion Topic",
			"title": title,
			"reference_doctype": doctype,
			"reference_docname": docname,
		}
	)
	topic.save(ignore_permissions=True)
	save_message(reply, topic.name)
	return topic.name


def save_message(reply, topic):
	vmraid.get_doc({"doctype": "Discussion Reply", "reply": reply, "topic": topic}).save(
		ignore_permissions=True
	)


@vmraid.whitelist(allow_guest=True)
def get_docname(route):
	if not route:
		route = vmraid.db.get_single_value("Website Settings", "home_page")
	return vmraid.db.get_value("Web Page", {"route": route}, ["name"])
