# -*- coding: utf-8 -*-
# Copyright (c) 2021, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid

# import vmraid
from vmraid.model.document import Document


class UserGroup(Document):
	def after_insert(self):
		vmraid.cache().delete_key("user_groups")

	def on_trash(self):
		vmraid.cache().delete_key("user_groups")
