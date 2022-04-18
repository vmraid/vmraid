# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import unittest

import vmraid
from vmraid.cache_manager import clear_controller_cache
from vmraid.desk.doctype.todo.todo import ToDo


class TestHooks(unittest.TestCase):
	def test_hooks(self):
		hooks = vmraid.get_hooks()
		self.assertTrue(isinstance(hooks.get("app_name"), list))
		self.assertTrue(isinstance(hooks.get("doc_events"), dict))
		self.assertTrue(isinstance(hooks.get("doc_events").get("*"), dict))
		self.assertTrue(isinstance(hooks.get("doc_events").get("*"), dict))
		self.assertTrue(
			"vmraid.desk.notifications.clear_doctype_notifications"
			in hooks.get("doc_events").get("*").get("on_update")
		)

	def test_override_doctype_class(self):
		from vmraid import hooks

		# Set hook
		hooks.override_doctype_class = {"ToDo": ["vmraid.tests.test_hooks.CustomToDo"]}

		# Clear cache
		vmraid.cache().delete_value("app_hooks")
		clear_controller_cache("ToDo")

		todo = vmraid.get_doc(doctype="ToDo", description="asdf")
		self.assertTrue(isinstance(todo, CustomToDo))

	def test_has_permission(self):
		from vmraid import hooks

		# Set hook
		address_has_permission_hook = hooks.has_permission.get("Address", [])
		if isinstance(address_has_permission_hook, str):
			address_has_permission_hook = [address_has_permission_hook]

		address_has_permission_hook.append("vmraid.tests.test_hooks.custom_has_permission")

		hooks.has_permission["Address"] = address_has_permission_hook

		# Clear cache
		vmraid.cache().delete_value("app_hooks")

		# Init User and Address
		username = "test@example.com"
		user = vmraid.get_doc("User", username)
		user.add_roles("System Manager")
		address = vmraid.new_doc("Address")

		# Test!
		self.assertTrue(vmraid.has_permission("Address", doc=address, user=username))

		address.flags.dont_touch_me = True
		self.assertFalse(vmraid.has_permission("Address", doc=address, user=username))


def custom_has_permission(doc, ptype, user):
	if doc.flags.dont_touch_me:
		return False


class CustomToDo(ToDo):
	pass
