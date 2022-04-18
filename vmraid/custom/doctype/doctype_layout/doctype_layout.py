# -*- coding: utf-8 -*-
# Copyright (c) 2020, VMRaid Technologies and contributors
# License: MIT. See LICENSE

from vmraid.desk.utils import slug
from vmraid.model.document import Document


class DocTypeLayout(Document):
	def validate(self):
		if not self.route:
			self.route = slug(self.name)
