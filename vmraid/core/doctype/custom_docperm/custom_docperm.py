# -*- coding: utf-8 -*-
# Copyright (c) 2015, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document


class CustomDocPerm(Document):
	def on_update(self):
		vmraid.clear_cache(doctype=self.parent)
