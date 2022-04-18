# Copyright (c) 2018, VMRaid and Contributors
# License: MIT. See LICENSE

import unittest

import vmraid
from vmraid.core.doctype.doctype.test_doctype import new_doctype
from vmraid.model.naming import (
	append_number_if_name_exists,
	determine_consecutive_week_number,
	getseries,
	revert_series_if_last,
)
from vmraid.utils import now_datetime


class TestNaming(unittest.TestCase):
	def setUp(self):
		vmraid.db.delete("Note")

	def tearDown(self):
		vmraid.db.rollback()

	def test_append_number_if_name_exists(self):
		"""
		Append number to name based on existing values
		if Bottle exists
		        Bottle -> Bottle-1
		if Bottle-1 exists
		        Bottle -> Bottle-2
		"""

		note = vmraid.new_doc("Note")
		note.title = "Test"
		note.insert()

		title2 = append_number_if_name_exists("Note", "Test")
		self.assertEqual(title2, "Test-1")

		title2 = append_number_if_name_exists("Note", "Test", "title", "_")
		self.assertEqual(title2, "Test_1")

	def test_field_autoname_name_sync(self):

		country = vmraid.get_last_doc("Country")
		original_name = country.name
		country.country_name = "Not a country"
		country.save()
		country.reload()

		self.assertEqual(country.name, original_name)
		self.assertEqual(country.name, country.country_name)

	def test_child_table_naming(self):
		child_dt_with_naming = new_doctype(
			"childtable_with_autonaming", istable=1, autoname="field:some_fieldname"
		).insert()
		dt_with_child_autoname = new_doctype(
			"dt_with_childtable_naming",
			fields=[
				{
					"label": "table with naming",
					"fieldname": "table_with_naming",
					"options": "childtable_with_autonaming",
					"fieldtype": "Table",
				}
			],
		).insert()

		name = vmraid.generate_hash(length=10)

		doc = vmraid.new_doc("dt_with_childtable_naming")
		doc.append("table_with_naming", {"some_fieldname": name})
		doc.save()
		self.assertEqual(doc.table_with_naming[0].name, name)

		# change autoname field
		doc.table_with_naming[0].some_fieldname = "Something else"
		doc.save()

		self.assertEqual(doc.table_with_naming[0].name, name)
		self.assertEqual(doc.table_with_naming[0].some_fieldname, name)

		doc.delete()
		dt_with_child_autoname.delete()
		child_dt_with_naming.delete()

	def test_format_autoname(self):
		"""
		Test if braced params are replaced in format autoname
		"""
		doctype = "ToDo"

		todo_doctype = vmraid.get_doc("DocType", doctype)
		todo_doctype.autoname = "format:TODO-{MM}-{status}-{##}"
		todo_doctype.save()

		description = "Format"

		todo = vmraid.new_doc(doctype)
		todo.description = description
		todo.insert()

		series = getseries("", 2)

		series = str(int(series) - 1)

		if len(series) < 2:
			series = "0" + series

		self.assertEqual(
			todo.name,
			"TODO-{month}-{status}-{series}".format(
				month=now_datetime().strftime("%m"), status=todo.status, series=series
			),
		)

	def test_format_autoname_for_consecutive_week_number(self):
		"""
		Test if braced params are replaced for consecutive week number in format autoname
		"""
		doctype = "ToDo"

		todo_doctype = vmraid.get_doc("DocType", doctype)
		todo_doctype.autoname = "format:TODO-{WW}-{##}"
		todo_doctype.save()

		description = "Format"

		todo = vmraid.new_doc(doctype)
		todo.description = description
		todo.insert()

		series = getseries("", 2)

		series = str(int(series) - 1)

		if len(series) < 2:
			series = "0" + series

		week = determine_consecutive_week_number(now_datetime())

		self.assertEqual(todo.name, "TODO-{week}-{series}".format(week=week, series=series))

	def test_revert_series(self):
		from datetime import datetime

		year = datetime.now().year

		series = "TEST-{}-".format(year)
		key = "TEST-.YYYY.-"
		name = "TEST-{}-00001".format(year)
		vmraid.db.sql("""INSERT INTO `tabSeries` (name, current) values (%s, 1)""", (series,))
		revert_series_if_last(key, name)
		current_index = vmraid.db.sql(
			"""SELECT current from `tabSeries` where name = %s""", series, as_dict=True
		)[0]

		self.assertEqual(current_index.get("current"), 0)
		vmraid.db.delete("Series", {"name": series})

		series = "TEST-{}-".format(year)
		key = "TEST-.YYYY.-.#####"
		name = "TEST-{}-00002".format(year)
		vmraid.db.sql("""INSERT INTO `tabSeries` (name, current) values (%s, 2)""", (series,))
		revert_series_if_last(key, name)
		current_index = vmraid.db.sql(
			"""SELECT current from `tabSeries` where name = %s""", series, as_dict=True
		)[0]

		self.assertEqual(current_index.get("current"), 1)
		vmraid.db.delete("Series", {"name": series})

		series = "TEST-"
		key = "TEST-"
		name = "TEST-00003"
		vmraid.db.delete("Series", {"name": series})
		vmraid.db.sql("""INSERT INTO `tabSeries` (name, current) values (%s, 3)""", (series,))
		revert_series_if_last(key, name)
		current_index = vmraid.db.sql(
			"""SELECT current from `tabSeries` where name = %s""", series, as_dict=True
		)[0]

		self.assertEqual(current_index.get("current"), 2)
		vmraid.db.delete("Series", {"name": series})

		series = "TEST1-"
		key = "TEST1-.#####.-2021-22"
		name = "TEST1-00003-2021-22"
		vmraid.db.delete("Series", {"name": series})
		vmraid.db.sql("""INSERT INTO `tabSeries` (name, current) values (%s, 3)""", (series,))
		revert_series_if_last(key, name)
		current_index = vmraid.db.sql(
			"""SELECT current from `tabSeries` where name = %s""", series, as_dict=True
		)[0]

		self.assertEqual(current_index.get("current"), 2)
		vmraid.db.delete("Series", {"name": series})

		series = ""
		key = ".#####.-2021-22"
		name = "00003-2021-22"
		vmraid.db.delete("Series", {"name": series})
		vmraid.db.sql("""INSERT INTO `tabSeries` (name, current) values (%s, 3)""", (series,))
		revert_series_if_last(key, name)
		current_index = vmraid.db.sql(
			"""SELECT current from `tabSeries` where name = %s""", series, as_dict=True
		)[0]

		self.assertEqual(current_index.get("current"), 2)

		vmraid.db.delete("Series", {"name": series})

	def test_naming_for_cancelled_and_amended_doc(self):
		submittable_doctype = vmraid.get_doc(
			{
				"doctype": "DocType",
				"module": "Core",
				"custom": 1,
				"is_submittable": 1,
				"permissions": [{"role": "System Manager", "read": 1}],
				"name": "Submittable Doctype",
			}
		).insert(ignore_if_duplicate=True)

		doc = vmraid.new_doc("Submittable Doctype")
		doc.save()
		original_name = doc.name

		doc.submit()
		doc.cancel()
		cancelled_name = doc.name
		self.assertEqual(cancelled_name, original_name)

		amended_doc = vmraid.copy_doc(doc)
		amended_doc.docstatus = 0
		amended_doc.amended_from = doc.name
		amended_doc.save()
		self.assertEqual(amended_doc.name, "{}-1".format(original_name))

		amended_doc.submit()
		amended_doc.cancel()
		self.assertEqual(amended_doc.name, "{}-1".format(original_name))

		submittable_doctype.delete()

	def test_determine_consecutive_week_number(self):
		from datetime import datetime

		dt = datetime.fromisoformat("2019-12-31")
		w = determine_consecutive_week_number(dt)
		self.assertEqual(w, "53")

		dt = datetime.fromisoformat("2020-01-01")
		w = determine_consecutive_week_number(dt)
		self.assertEqual(w, "01")

		dt = datetime.fromisoformat("2020-01-15")
		w = determine_consecutive_week_number(dt)
		self.assertEqual(w, "03")

		dt = datetime.fromisoformat("2021-01-01")
		w = determine_consecutive_week_number(dt)
		self.assertEqual(w, "00")

		dt = datetime.fromisoformat("2021-12-31")
		w = determine_consecutive_week_number(dt)
		self.assertEqual(w, "52")

	def test_naming_validations(self):
		# case 1: check same name as doctype
		# set name via prompt
		tag = vmraid.get_doc({"doctype": "Tag", "__newname": "Tag"})
		self.assertRaises(vmraid.NameError, tag.insert)

		# set by passing set_name as ToDo
		self.assertRaises(vmraid.NameError, make_invalid_todo)

		# set new name - Note
		note = vmraid.get_doc({"doctype": "Note", "title": "Note"})
		self.assertRaises(vmraid.NameError, note.insert)

		# case 2: set name with "New ---"
		tag = vmraid.get_doc({"doctype": "Tag", "__newname": "New Tag"})
		self.assertRaises(vmraid.NameError, tag.insert)

		# case 3: set name with special characters
		tag = vmraid.get_doc({"doctype": "Tag", "__newname": "Tag<>"})
		self.assertRaises(vmraid.NameError, tag.insert)

		# case 4: no name specified
		tag = vmraid.get_doc({"doctype": "Tag", "__newname": ""})
		self.assertRaises(vmraid.ValidationError, tag.insert)

	def test_autoincremented_naming(self):
		from vmraid.core.doctype.doctype.test_doctype import new_doctype

		doctype = "autoinc_doctype" + vmraid.generate_hash(length=5)
		dt = new_doctype(doctype, autoname="autoincrement").insert(ignore_permissions=True)

		for i in range(1, 20):
			self.assertEqual(vmraid.new_doc(doctype).save(ignore_permissions=True).name, i)

		dt.delete(ignore_permissions=True)


def make_invalid_todo():
	vmraid.get_doc({"doctype": "ToDo", "description": "Test"}).insert(set_name="ToDo")
