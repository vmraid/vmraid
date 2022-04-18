# Copyright (c) 2021, VMRaid Technologies and contributors
# For license information, please see license.txt

import vmraid
from vmraid.model.document import Document


class DiscussionReply(Document):
	def on_update(self):
		vmraid.publish_realtime(
			event="update_message",
			message={"reply": vmraid.utils.md_to_html(self.reply), "reply_name": self.name},
			after_commit=True,
		)

	def after_insert(self):
		replies = vmraid.db.count("Discussion Reply", {"topic": self.topic})
		topic_info = vmraid.get_all(
			"Discussion Topic",
			{"name": self.topic},
			["reference_doctype", "reference_docname", "name", "title", "owner", "creation"],
		)

		template = vmraid.render_template(
			"vmraid/templates/discussions/reply_card.html",
			{
				"reply": self,
				"topic": {"name": self.topic},
				"loop": {"index": replies},
				"single_thread": True if not topic_info[0].title else False,
			},
		)

		sidebar = vmraid.render_template(
			"vmraid/templates/discussions/sidebar.html", {"topic": topic_info[0]}
		)

		new_topic_template = vmraid.render_template(
			"vmraid/templates/discussions/reply_section.html", {"topic": topic_info[0]}
		)

		vmraid.publish_realtime(
			event="publish_message",
			message={
				"template": template,
				"topic_info": topic_info[0],
				"sidebar": sidebar,
				"new_topic_template": new_topic_template,
				"reply_owner": self.owner,
			},
			after_commit=True,
		)

	def after_delete(self):
		vmraid.publish_realtime(
			event="delete_message", message={"reply_name": self.name}, after_commit=True
		)


@vmraid.whitelist()
def delete_message(reply_name):
	vmraid.delete_doc("Discussion Reply", reply_name, ignore_permissions=True)
