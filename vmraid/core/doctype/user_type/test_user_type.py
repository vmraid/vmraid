# -*- coding: utf-8 -*-
# Copyright (c) 2021, VMRaid Technologies and Contributors
# License: MIT. See LICENSE
import unittest

import vmraid
from vmraid.installer import update_site_config


class TestUserType(unittest.TestCase):
	def setUp(self):
		create_role()

	def test_add_select_perm_doctypes(self):
		user_type = create_user_type("Test User Type")

		# select perms added for all link fields
		doc = vmraid.get_meta("Contact")
		link_fields = doc.get_link_fields()
		select_doctypes = vmraid.get_all(
			"User Select Document Type", {"parent": user_type.name}, pluck="document_type"
		)

		for entry in link_fields:
			self.assertTrue(entry.options in select_doctypes)

		# select perms added for all child table link fields
		link_fields = []
		for child_table in doc.get_table_fields():
			child_doc = vmraid.get_meta(child_table.options)
			link_fields.extend(child_doc.get_link_fields())

		for entry in link_fields:
			self.assertTrue(entry.options in select_doctypes)

	def tearDown(self):
		vmraid.db.rollback()


def create_user_type(user_type):
	if vmraid.db.exists("User Type", user_type):
		vmraid.delete_doc("User Type", user_type)

	user_type_limit = {vmraid.scrub(user_type): 1}
	update_site_config("user_type_doctype_limit", user_type_limit)

	doc = vmraid.get_doc(
		{
			"doctype": "User Type",
			"name": user_type,
			"role": "_Test User Type",
			"user_id_field": "user",
			"apply_user_permission_on": "User",
		}
	)

	doc.append("user_doctypes", {"document_type": "Contact", "read": 1, "write": 1})

	return doc.insert()


def create_role():
	if not vmraid.db.exists("Role", "_Test User Type"):
		vmraid.get_doc(
			{"doctype": "Role", "role_name": "_Test User Type", "desk_access": 1, "is_custom": 1}
		).insert()
