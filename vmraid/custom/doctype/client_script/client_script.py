# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
import vmraid
from vmraid import _
from vmraid.model.document import Document


class ClientScript(Document):
	def on_update(self):
		vmraid.clear_cache(doctype=self.dt)

	def on_trash(self):
		vmraid.clear_cache(doctype=self.dt)
