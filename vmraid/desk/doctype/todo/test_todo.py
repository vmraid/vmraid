# -*- coding: utf-8 -*-
# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
import unittest

import vmraid
from vmraid.core.doctype.doctype.doctype import clear_permissions_cache
from vmraid.model.db_query import DatabaseQuery
from vmraid.permissions import add_permission, reset_perms

test_dependencies = ["User"]


class TestToDo(unittest.TestCase):
	def test_delete(self):
		todo = vmraid.get_doc(
			dict(doctype="ToDo", description="test todo", assigned_by="Administrator")
		).insert()

		vmraid.db.delete("Deleted Document")
		todo.delete()

		deleted = vmraid.get_doc(
			"Deleted Document", dict(deleted_doctype=todo.doctype, deleted_name=todo.name)
		)
		self.assertEqual(todo.as_json(), deleted.data)

	def test_fetch(self):
		todo = vmraid.get_doc(
			dict(doctype="ToDo", description="test todo", assigned_by="Administrator")
		).insert()
		self.assertEqual(
			todo.assigned_by_full_name, vmraid.db.get_value("User", todo.assigned_by, "full_name")
		)

	def test_fetch_setup(self):
		vmraid.db.delete("ToDo")

		todo_meta = vmraid.get_doc("DocType", "ToDo")
		todo_meta.get("fields", dict(fieldname="assigned_by_full_name"))[0].fetch_from = ""
		todo_meta.save()

		vmraid.clear_cache(doctype="ToDo")

		todo = vmraid.get_doc(
			dict(doctype="ToDo", description="test todo", assigned_by="Administrator")
		).insert()
		self.assertFalse(todo.assigned_by_full_name)

		todo_meta = vmraid.get_doc("DocType", "ToDo")
		todo_meta.get("fields", dict(fieldname="assigned_by_full_name"))[
			0
		].fetch_from = "assigned_by.full_name"
		todo_meta.save()

		todo.reload()

		self.assertEqual(
			todo.assigned_by_full_name, vmraid.db.get_value("User", todo.assigned_by, "full_name")
		)

	def test_todo_list_access(self):
		create_new_todo("Test1", "testperm@example.com")

		vmraid.set_user("test4@example.com")
		create_new_todo("Test2", "test4@example.com")
		test_user_data = DatabaseQuery("ToDo").execute()

		vmraid.set_user("testperm@example.com")
		system_manager_data = DatabaseQuery("ToDo").execute()

		self.assertNotEqual(test_user_data, system_manager_data)

		vmraid.set_user("Administrator")
		vmraid.db.rollback()

	def test_doc_read_access(self):
		# owner and assigned_by is testperm
		todo1 = create_new_todo("Test1", "testperm@example.com")
		test_user = vmraid.get_doc("User", "test4@example.com")

		# owner is testperm, but assigned_by is test4
		todo2 = create_new_todo("Test2", "test4@example.com")

		vmraid.set_user("test4@example.com")
		# owner and assigned_by is test4
		todo3 = create_new_todo("Test3", "test4@example.com")

		# user without any role to read or write todo document
		self.assertFalse(todo1.has_permission("read"))
		self.assertFalse(todo1.has_permission("write"))

		# user without any role but he/she is assigned_by of that todo document
		self.assertTrue(todo2.has_permission("read"))
		self.assertTrue(todo2.has_permission("write"))

		# user is the owner and assigned_by of the todo document
		self.assertTrue(todo3.has_permission("read"))
		self.assertTrue(todo3.has_permission("write"))

		vmraid.set_user("Administrator")

		test_user.add_roles("Blogger")
		add_permission("ToDo", "Blogger")

		vmraid.set_user("test4@example.com")

		# user with only read access to todo document, not an owner or assigned_by
		self.assertTrue(todo1.has_permission("read"))
		self.assertFalse(todo1.has_permission("write"))

		vmraid.set_user("Administrator")
		test_user.remove_roles("Blogger")
		reset_perms("ToDo")
		clear_permissions_cache("ToDo")
		vmraid.db.rollback()

	def test_fetch_if_empty(self):
		vmraid.db.delete("ToDo")

		# Allow user changes
		todo_meta = vmraid.get_doc("DocType", "ToDo")
		field = todo_meta.get("fields", dict(fieldname="assigned_by_full_name"))[0]
		field.fetch_from = "assigned_by.full_name"
		field.fetch_if_empty = 1
		todo_meta.save()

		vmraid.clear_cache(doctype="ToDo")

		todo = vmraid.get_doc(
			dict(
				doctype="ToDo",
				description="test todo",
				assigned_by="Administrator",
				assigned_by_full_name="Admin",
			)
		).insert()

		self.assertEqual(todo.assigned_by_full_name, "Admin")

		# Overwrite user changes
		todo.meta.get("fields", dict(fieldname="assigned_by_full_name"))[0].fetch_if_empty = 0
		todo.meta.save()

		todo.reload()
		todo.save()

		self.assertEqual(
			todo.assigned_by_full_name, vmraid.db.get_value("User", todo.assigned_by, "full_name")
		)


def create_new_todo(description, assigned_by):
	todo = {"doctype": "ToDo", "description": description, "assigned_by": assigned_by}
	return vmraid.get_doc(todo).insert()
