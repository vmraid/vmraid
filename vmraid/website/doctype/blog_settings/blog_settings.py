# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document


class BlogSettings(Document):
	def on_update(self):
		from vmraid.website.utils import clear_cache

		clear_cache("blog")
		clear_cache("writers")


def get_feedback_limit():
	return vmraid.db.get_single_value("Blog Settings", "feedback_limit") or 5


def get_comment_limit():
	return vmraid.db.get_single_value("Blog Settings", "comment_limit") or 5
