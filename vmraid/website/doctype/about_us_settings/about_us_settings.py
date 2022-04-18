# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document


class AboutUsSettings(Document):
	def on_update(self):
		from vmraid.website.utils import clear_cache

		clear_cache("about")


def get_args():
	obj = vmraid.get_doc("About Us Settings")
	return {"obj": obj}
