# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document


class WebsiteScript(Document):
	def on_update(self):
		"""clear cache"""
		vmraid.clear_cache(user="Guest")

		from vmraid.website.utils import clear_cache

		clear_cache()
