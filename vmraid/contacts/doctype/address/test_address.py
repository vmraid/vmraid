# -*- coding: utf-8 -*-
# Copyright (c) 2015, VMRaid Technologies and Contributors
# License: MIT. See LICENSE
import unittest

import vmraid
from vmraid.contacts.doctype.address.address import get_address_display


class TestAddress(unittest.TestCase):
	def test_template_works(self):
		if not vmraid.db.exists("Address Template", "India"):
			vmraid.get_doc({"doctype": "Address Template", "country": "India", "is_default": 1}).insert()

		if not vmraid.db.exists("Address", "_Test Address-Office"):
			vmraid.get_doc(
				{
					"address_line1": "_Test Address Line 1",
					"address_title": "_Test Address",
					"address_type": "Office",
					"city": "_Test City",
					"state": "Test State",
					"country": "India",
					"doctype": "Address",
					"is_primary_address": 1,
					"phone": "+91 0000000000",
				}
			).insert()

		address = vmraid.get_list("Address")[0].name
		display = get_address_display(vmraid.get_doc("Address", address).as_dict())
		self.assertTrue(display)
