# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE

import os
import unittest
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from random import choice, sample
from typing import List
from unittest.mock import patch

import vmraid
from vmraid.exceptions import DoesNotExistError, ValidationError
from vmraid.model.base_document import get_controller
from vmraid.model.rename_doc import (
	bulk_rename,
	get_fetch_fields,
	update_document_title,
	update_linked_doctypes,
)
from vmraid.modules.utils import get_doc_path
from vmraid.utils import add_to_date, now


@contextmanager
def patch_db(endpoints: List[str] = None):
	patched_endpoints = []

	for point in endpoints:
		x = patch(f"vmraid.db.{point}", new=lambda: True)
		patched_endpoints.append(x)

	savepoint = "SAVEPOINT_for_test_bulk_rename"
	vmraid.db.savepoint(save_point=savepoint)
	try:
		for x in patched_endpoints:
			x.start()
		yield
	finally:
		for x in patched_endpoints:
			x.stop()
		vmraid.db.rollback(save_point=savepoint)


class TestRenameDoc(unittest.TestCase):
	@classmethod
	def setUpClass(self):
		"""Setting Up data for the tests defined under TestRenameDoc"""
		# set developer_mode to rename doc controllers
		self._original_developer_flag = vmraid.conf.developer_mode
		vmraid.conf.developer_mode = 1

		# data generation: for base and merge tests
		self.available_documents = []
		self.test_doctype = "ToDo"

		for num in range(1, 5):
			doc = vmraid.get_doc(
				{
					"doctype": self.test_doctype,
					"date": add_to_date(now(), days=num),
					"description": "this is todo #{}".format(num),
				}
			).insert()
			self.available_documents.append(doc.name)

		#  data generation: for controllers tests
		self.doctype = vmraid._dict(
			{
				"old": "Test Rename Document Old",
				"new": "Test Rename Document New",
			}
		)

		vmraid.get_doc(
			{
				"doctype": "DocType",
				"module": "Custom",
				"name": self.doctype.old,
				"custom": 0,
				"fields": [{"label": "Some Field", "fieldname": "some_fieldname", "fieldtype": "Data"}],
				"permissions": [{"role": "System Manager", "read": 1}],
			}
		).insert()

	@classmethod
	def tearDownClass(self):
		"""Deleting data generated for the tests defined under TestRenameDoc"""
		# delete_doc doesnt drop tables
		# this is done to bypass inconsistencies in the db
		vmraid.delete_doc_if_exists("DocType", "Renamed Doc")
		vmraid.db.sql_ddl("drop table if exists `tabRenamed Doc`")

		# delete the documents created
		for docname in self.available_documents:
			vmraid.delete_doc(self.test_doctype, docname)

		for dt in self.doctype.values():
			if vmraid.db.exists("DocType", dt):
				vmraid.delete_doc("DocType", dt)
				vmraid.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{dt}`")

		vmraid.delete_doc_if_exists("Renamed Doc", "ToDo")

		# reset original value of developer_mode conf
		vmraid.conf.developer_mode = self._original_developer_flag

	def setUp(self):
		vmraid.flags.link_fields = {}
		super().setUp()

	def test_rename_doc(self):
		"""Rename an existing document via vmraid.rename_doc"""
		old_name = choice(self.available_documents)
		new_name = old_name + ".new"
		self.assertEqual(new_name, vmraid.rename_doc(self.test_doctype, old_name, new_name, force=True))
		self.available_documents.remove(old_name)
		self.available_documents.append(new_name)

	def test_merging_docs(self):
		"""Merge two documents via vmraid.rename_doc"""
		first_todo, second_todo = sample(self.available_documents, 2)

		second_todo_doc = vmraid.get_doc(self.test_doctype, second_todo)
		second_todo_doc.priority = "High"
		second_todo_doc.save()

		merged_todo = vmraid.rename_doc(
			self.test_doctype, first_todo, second_todo, merge=True, force=True
		)
		merged_todo_doc = vmraid.get_doc(self.test_doctype, merged_todo)
		self.available_documents.remove(first_todo)

		with self.assertRaises(DoesNotExistError):
			vmraid.get_doc(self.test_doctype, first_todo)

		self.assertEqual(merged_todo_doc.priority, second_todo_doc.priority)

	def test_rename_controllers(self):
		"""Rename doctypes with controller code paths"""
		# check if module exists exists;
		# if custom, get_controller will return Document class
		# if not custom, a different class will be returned
		self.assertNotEqual(get_controller(self.doctype.old), vmraid.model.document.Document)

		old_doctype_path = get_doc_path("Custom", "DocType", self.doctype.old)

		# rename doc via wrapper API accessible via /desk
		vmraid.rename_doc("DocType", self.doctype.old, self.doctype.new)

		# check if database and controllers are updated
		self.assertTrue(vmraid.db.exists("DocType", self.doctype.new))
		self.assertFalse(vmraid.db.exists("DocType", self.doctype.old))
		self.assertFalse(os.path.exists(old_doctype_path))

	def test_rename_doctype(self):
		"""Rename DocType via vmraid.rename_doc"""
		from vmraid.core.doctype.doctype.test_doctype import new_doctype

		if not vmraid.db.exists("DocType", "Rename This"):
			new_doctype(
				"Rename This",
				fields=[
					{
						"label": "Linked To",
						"fieldname": "linked_to_doctype",
						"fieldtype": "Link",
						"options": "DocType",
						"unique": 0,
					}
				],
			).insert()

		to_rename_record = vmraid.get_doc(
			{"doctype": "Rename This", "linked_to_doctype": "Rename This"}
		).insert()

		# Rename doctype
		self.assertEqual(
			"Renamed Doc", vmraid.rename_doc("DocType", "Rename This", "Renamed Doc", force=True)
		)

		# Test if Doctype value has changed in Link field
		linked_to_doctype = vmraid.db.get_value(
			"Renamed Doc", to_rename_record.name, "linked_to_doctype"
		)
		self.assertEqual(linked_to_doctype, "Renamed Doc")

		# Test if there are conflicts between a record and a DocType
		# having the same name
		old_name = to_rename_record.name
		new_name = "ToDo"
		self.assertEqual(new_name, vmraid.rename_doc("Renamed Doc", old_name, new_name, force=True))

	def test_update_document_title_api(self):
		test_doctype = "Module Def"
		test_doc = vmraid.get_doc(
			{
				"doctype": test_doctype,
				"module_name": f"Test-test_update_document_title_api-{vmraid.generate_hash()}",
				"custom": True,
			}
		)
		test_doc.insert(ignore_mandatory=True)

		dt = test_doc.doctype
		dn = test_doc.name
		new_name = f"{dn}-new"

		# pass invalid types to API
		with self.assertRaises(ValidationError):
			update_document_title(doctype=dt, docname=dn, title={}, name={"hack": "this"})

		doc_before = vmraid.get_doc(test_doctype, dn)
		return_value = update_document_title(doctype=dt, docname=dn, new_name=new_name)
		doc_after = vmraid.get_doc(test_doctype, return_value)

		doc_before_dict = doc_before.as_dict(no_nulls=True, no_default_fields=True)
		doc_after_dict = doc_after.as_dict(no_nulls=True, no_default_fields=True)
		doc_before_dict.pop("module_name")
		doc_after_dict.pop("module_name")

		self.assertEqual(new_name, return_value)
		self.assertDictEqual(doc_before_dict, doc_after_dict)
		self.assertEqual(doc_after.module_name, return_value)

		test_doc.delete()

	def test_bulk_rename(self):
		input_data = [[x, f"{x}-new"] for x in self.available_documents]

		with patch_db(["commit", "rollback"]), patch("vmraid.enqueue") as enqueue:
			message_log = bulk_rename(self.test_doctype, input_data, via_console=False)
			self.assertEqual(len(message_log), len(self.available_documents))
			self.assertIsInstance(message_log, list)
			enqueue.assert_called_with(
				"vmraid.utils.global_search.rebuild_for_doctype",
				doctype=self.test_doctype,
			)

	def test_deprecated_utils(self):
		stdout = StringIO()

		with redirect_stdout(stdout), patch_db(["set_value"]):
			get_fetch_fields("User", "ToDo", ["Activity Log"])
			self.assertTrue("Function vmraid.model.rename_doc.get_fetch_fields" in stdout.getvalue())

			update_linked_doctypes("User", "ToDo", "str", "str")
			self.assertTrue("Function vmraid.model.rename_doc.update_linked_doctypes" in stdout.getvalue())
