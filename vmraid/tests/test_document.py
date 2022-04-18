# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE
import unittest
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import vmraid
from vmraid.desk.doctype.note.note import Note
from vmraid.model.naming import make_autoname, parse_naming_series, revert_series_if_last
from vmraid.utils import cint, now_datetime


class CustomTestNote(Note):
	@property
	def age(self):
		return now_datetime() - self.creation


class TestDocument(unittest.TestCase):
	def test_get_return_empty_list_for_table_field_if_none(self):
		d = vmraid.get_doc({"doctype": "User"})
		self.assertEqual(d.get("roles"), [])

	def test_load(self):
		d = vmraid.get_doc("DocType", "User")
		self.assertEqual(d.doctype, "DocType")
		self.assertEqual(d.name, "User")
		self.assertEqual(d.allow_rename, 1)
		self.assertTrue(isinstance(d.fields, list))
		self.assertTrue(isinstance(d.permissions, list))
		self.assertTrue(filter(lambda d: d.fieldname == "email", d.fields))

	def test_load_single(self):
		d = vmraid.get_doc("Website Settings", "Website Settings")
		self.assertEqual(d.name, "Website Settings")
		self.assertEqual(d.doctype, "Website Settings")
		self.assertTrue(d.disable_signup in (0, 1))

	def test_insert(self):
		d = vmraid.get_doc(
			{
				"doctype": "Event",
				"subject": "test-doc-test-event 1",
				"starts_on": "2014-01-01",
				"event_type": "Public",
			}
		)
		d.insert()
		self.assertTrue(d.name.startswith("EV"))
		self.assertEqual(vmraid.db.get_value("Event", d.name, "subject"), "test-doc-test-event 1")

		# test if default values are added
		self.assertEqual(d.send_reminder, 1)
		return d

	def test_insert_with_child(self):
		d = vmraid.get_doc(
			{
				"doctype": "Event",
				"subject": "test-doc-test-event 2",
				"starts_on": "2014-01-01",
				"event_type": "Public",
			}
		)
		d.insert()
		self.assertTrue(d.name.startswith("EV"))
		self.assertEqual(vmraid.db.get_value("Event", d.name, "subject"), "test-doc-test-event 2")

	def test_update(self):
		d = self.test_insert()
		d.subject = "subject changed"
		d.save()

		self.assertEqual(vmraid.db.get_value(d.doctype, d.name, "subject"), "subject changed")

	def test_value_changed(self):
		d = self.test_insert()
		d.subject = "subject changed again"
		d.save()
		self.assertTrue(d.has_value_changed("subject"))
		self.assertFalse(d.has_value_changed("event_type"))

	def test_mandatory(self):
		# TODO: recheck if it is OK to force delete
		vmraid.delete_doc_if_exists("User", "test_mandatory@example.com", 1)

		d = vmraid.get_doc(
			{
				"doctype": "User",
				"email": "test_mandatory@example.com",
			}
		)
		self.assertRaises(vmraid.MandatoryError, d.insert)

		d.set("first_name", "Test Mandatory")
		d.insert()
		self.assertEqual(vmraid.db.get_value("User", d.name), d.name)

	def test_conflict_validation(self):
		d1 = self.test_insert()
		d2 = vmraid.get_doc(d1.doctype, d1.name)
		d1.save()
		self.assertRaises(vmraid.TimestampMismatchError, d2.save)

	def test_conflict_validation_single(self):
		d1 = vmraid.get_doc("Website Settings", "Website Settings")
		d1.home_page = "test-web-page-1"

		d2 = vmraid.get_doc("Website Settings", "Website Settings")
		d2.home_page = "test-web-page-1"

		d1.save()
		self.assertRaises(vmraid.TimestampMismatchError, d2.save)

	def test_permission(self):
		vmraid.set_user("Guest")
		self.assertRaises(vmraid.PermissionError, self.test_insert)
		vmraid.set_user("Administrator")

	def test_permission_single(self):
		vmraid.set_user("Guest")
		d = vmraid.get_doc("Website Settings", "Website Settings")
		self.assertRaises(vmraid.PermissionError, d.save)
		vmraid.set_user("Administrator")

	def test_link_validation(self):
		vmraid.delete_doc_if_exists("User", "test_link_validation@example.com", 1)

		d = vmraid.get_doc(
			{
				"doctype": "User",
				"email": "test_link_validation@example.com",
				"first_name": "Link Validation",
				"roles": [{"role": "ABC"}],
			}
		)
		self.assertRaises(vmraid.LinkValidationError, d.insert)

		d.roles = []
		d.append("roles", {"role": "System Manager"})
		d.insert()

		self.assertEqual(vmraid.db.get_value("User", d.name), d.name)

	def test_validate(self):
		d = self.test_insert()
		d.starts_on = "2014-01-01"
		d.ends_on = "2013-01-01"
		self.assertRaises(vmraid.ValidationError, d.validate)
		self.assertRaises(vmraid.ValidationError, d.run_method, "validate")
		self.assertRaises(vmraid.ValidationError, d.save)

	def test_update_after_submit(self):
		d = self.test_insert()
		d.starts_on = "2014-09-09"
		self.assertRaises(vmraid.UpdateAfterSubmitError, d.validate_update_after_submit)
		d.meta.get_field("starts_on").allow_on_submit = 1
		d.validate_update_after_submit()
		d.meta.get_field("starts_on").allow_on_submit = 0

		# when comparing date(2014, 1, 1) and "2014-01-01"
		d.reload()
		d.starts_on = "2014-01-01"
		d.validate_update_after_submit()

	def test_varchar_length(self):
		d = self.test_insert()
		d.sender = "abcde" * 100 + "@user.com"
		self.assertRaises(vmraid.CharacterLengthExceededError, d.save)

	def test_xss_filter(self):
		d = self.test_insert()

		# script
		xss = '<script>alert("XSS")</script>'
		escaped_xss = xss.replace("<", "&lt;").replace(">", "&gt;")
		d.subject += xss
		d.save()
		d.reload()

		self.assertTrue(xss not in d.subject)
		self.assertTrue(escaped_xss in d.subject)

		# onload
		xss = '<div onload="alert("XSS")">Test</div>'
		escaped_xss = "<div>Test</div>"
		d.subject += xss
		d.save()
		d.reload()

		self.assertTrue(xss not in d.subject)
		self.assertTrue(escaped_xss in d.subject)

		# css attributes
		xss = '<div style="something: doesn\'t work; color: red;">Test</div>'
		escaped_xss = '<div style="">Test</div>'
		d.subject += xss
		d.save()
		d.reload()

		self.assertTrue(xss not in d.subject)
		self.assertTrue(escaped_xss in d.subject)

	def test_naming_series(self):
		data = ["TEST-", "TEST/17-18/.test_data./.####", "TEST.YYYY.MM.####"]

		for series in data:
			name = make_autoname(series)
			prefix = series

			if ".#" in series:
				prefix = series.rsplit(".", 1)[0]

			prefix = parse_naming_series(prefix)
			old_current = vmraid.db.get_value("Series", prefix, "current", order_by="name")

			revert_series_if_last(series, name)
			new_current = cint(vmraid.db.get_value("Series", prefix, "current", order_by="name"))

			self.assertEqual(cint(old_current) - 1, new_current)

	def test_non_negative_check(self):
		vmraid.delete_doc_if_exists("Currency", "VMRaid Coin", 1)

		d = vmraid.get_doc(
			{"doctype": "Currency", "currency_name": "VMRaid Coin", "smallest_currency_fraction_value": -1}
		)

		self.assertRaises(vmraid.NonNegativeError, d.insert)

		d.set("smallest_currency_fraction_value", 1)
		d.insert()
		self.assertEqual(vmraid.db.get_value("Currency", d.name), d.name)

		vmraid.delete_doc_if_exists("Currency", "VMRaid Coin", 1)

	def test_get_formatted(self):
		vmraid.get_doc(
			{
				"doctype": "DocType",
				"name": "Test Formatted",
				"module": "Custom",
				"custom": 1,
				"fields": [
					{"label": "Currency", "fieldname": "currency", "reqd": 1, "fieldtype": "Currency"},
				],
			}
		).insert(ignore_if_duplicate=True)

		vmraid.delete_doc_if_exists("Currency", "INR", 1)

		d = vmraid.get_doc(
			{
				"doctype": "Currency",
				"currency_name": "INR",
				"symbol": "₹",
			}
		).insert()

		d = vmraid.get_doc({"doctype": "Test Formatted", "currency": 100000})
		self.assertEqual(d.get_formatted("currency", currency="INR", format="#,###.##"), "₹ 100,000.00")

		# should work even if options aren't set in df
		# and currency param is not passed
		self.assertIn("0", d.get_formatted("currency"))

	def test_limit_for_get(self):
		doc = vmraid.get_doc("DocType", "DocType")
		# assuming DocType has more than 3 Data fields
		self.assertEqual(len(doc.get("fields", limit=3)), 3)

		# limit with filters
		self.assertEqual(len(doc.get("fields", filters={"fieldtype": "Data"}, limit=3)), 3)

	def test_virtual_fields(self):
		"""Virtual fields are accessible via API and Form views, whenever .as_dict is invoked"""
		vmraid.db.delete("Custom Field", {"dt": "Note", "fieldname": "age"})
		note = vmraid.new_doc("Note")
		note.content = "some content"
		note.title = vmraid.generate_hash(length=20)
		note.insert()

		def patch_note():
			return patch("vmraid.controllers", new={vmraid.local.site: {"Note": CustomTestNote}})

		@contextmanager
		def customize_note(with_options=False):
			options = "vmraid.utils.now_datetime() - doc.creation" if with_options else ""
			custom_field = vmraid.get_doc(
				{
					"doctype": "Custom Field",
					"dt": "Note",
					"fieldname": "age",
					"fieldtype": "Data",
					"read_only": True,
					"is_virtual": True,
					"options": options,
				}
			)

			try:
				yield custom_field.insert(ignore_if_duplicate=True)
			finally:
				custom_field.delete()

		with patch_note():
			doc = vmraid.get_last_doc("Note")
			self.assertIsInstance(doc, CustomTestNote)
			self.assertIsInstance(doc.age, timedelta)
			self.assertIsNone(doc.as_dict().get("age"))
			self.assertIsNone(doc.get_valid_dict().get("age"))

		with customize_note(), patch_note():
			doc = vmraid.get_last_doc("Note")
			self.assertIsInstance(doc, CustomTestNote)
			self.assertIsInstance(doc.age, timedelta)
			self.assertIsInstance(doc.as_dict().get("age"), timedelta)
			self.assertIsInstance(doc.get_valid_dict().get("age"), timedelta)

		with customize_note(with_options=True):
			doc = vmraid.get_last_doc("Note")
			self.assertIsInstance(doc, Note)
			self.assertIsInstance(doc.as_dict().get("age"), timedelta)
			self.assertIsInstance(doc.get_valid_dict().get("age"), timedelta)

	def test_run_method(self):
		doc = vmraid.get_last_doc("User")

		# Case 1: Override with a string
		doc.as_dict = ""

		# run_method should throw TypeError
		self.assertRaisesRegex(TypeError, "not callable", doc.run_method, "as_dict")

		# Case 2: Override with a function
		def my_as_dict(*args, **kwargs):
			return "success"

		doc.as_dict = my_as_dict

		# run_method should get overridden
		self.assertEqual(doc.run_method("as_dict"), "success")
