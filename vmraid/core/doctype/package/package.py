# Copyright (c) 2021, VMRaid Technologies and contributors
# For license information, please see license.txt

import os

import vmraid
from vmraid.model.document import Document


class Package(Document):
	def validate(self):
		if not self.package_name:
			self.package_name = self.name.lower().replace(" ", "-")


@vmraid.whitelist()
def get_license_text(license_type):
	with open(
		os.path.join(os.path.dirname(__file__), "licenses", license_type + ".md"), "r"
	) as textfile:
		return textfile.read()
