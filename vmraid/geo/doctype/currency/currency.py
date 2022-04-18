# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid
from vmraid import _, throw
from vmraid.model.document import Document


class Currency(Document):
	def validate(self):
		if not vmraid.flags.in_install_app:
			vmraid.clear_cache()
