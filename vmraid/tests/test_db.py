# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE

import datetime
import inspect
import unittest
from random import choice
from unittest.mock import patch

import vmraid
from vmraid.custom.doctype.custom_field.custom_field import create_custom_field
from vmraid.database import savepoint
from vmraid.database.database import Database
from vmraid.query_builder import Field
from vmraid.query_builder.functions import Concat_ws
from vmraid.tests.test_query_builder import db_type_is, run_only_if
from vmraid.utils import add_days, cint, now, random_string
from vmraid.utils.testutils import clear_custom_fields


class TestDB(unittest.TestCase):
	def test_get_value(self):
		self.assertEqual(vmraid.db.get_value("User", {"name": ["=", "Administrator"]}), "Administrator")
		self.assertEqual(vmraid.db.get_value("User", {"name": ["like", "Admin%"]}), "Administrator")
		self.assertNotEqual(vmraid.db.get_value("User", {"name": ["!=", "Guest"]}), "Guest")
		self.assertEqual(vmraid.db.get_value("User", {"name": ["<", "Adn"]}), "Administrator")
		self.assertEqual(vmraid.db.get_value("User", {"name": ["<=", "Administrator"]}), "Administrator")
		self.assertEqual(
			vmraid.db.get_value("User", {}, ["Max(name)"], order_by=None),
			vmraid.db.sql("SELECT Max(name) FROM tabUser")[0][0],
		)
		self.assertEqual(
			vmraid.db.get_value("User", {}, "Min(name)", order_by=None),
			vmraid.db.sql("SELECT Min(name) FROM tabUser")[0][0],
		)
		self.assertIn(
			"for update",
			vmraid.db.get_value(
				"User", Field("name") == "Administrator", for_update=True, run=False
			).lower(),
		)
		user_doctype = vmraid.qb.DocType("User")
		self.assertEqual(
			vmraid.qb.from_(user_doctype).select(user_doctype.name, user_doctype.email).run(),
			vmraid.db.get_values(
				user_doctype,
				filters={},
				fieldname=[user_doctype.name, user_doctype.email],
				order_by=None,
			),
		)
		self.assertEqual(
			vmraid.db.sql("""SELECT name FROM `tabUser` WHERE name > 's' ORDER BY MODIFIED DESC""")[0][0],
			vmraid.db.get_value("User", {"name": [">", "s"]}),
		)

		self.assertEqual(
			vmraid.db.sql("""SELECT name FROM `tabUser` WHERE name >= 't' ORDER BY MODIFIED DESC""")[0][0],
			vmraid.db.get_value("User", {"name": [">=", "t"]}),
		)
		self.assertEqual(
			vmraid.db.get_values(
				"User",
				filters={"name": "Administrator"},
				distinct=True,
				fieldname="email",
			),
			vmraid.qb.from_(user_doctype)
			.where(user_doctype.name == "Administrator")
			.select("email")
			.distinct()
			.run(),
		)

		self.assertIn(
			"concat_ws",
			vmraid.db.get_value(
				"User",
				filters={"name": "Administrator"},
				fieldname=Concat_ws(" ", "LastName"),
				run=False,
			).lower(),
		)
		self.assertEqual(
			vmraid.db.sql("select email from tabUser where name='Administrator' order by modified DESC"),
			vmraid.db.get_values("User", filters=[["name", "=", "Administrator"]], fieldname="email"),
		)

	def test_get_value_limits(self):

		# check both dict and list style filters
		filters = [{"enabled": 1}, [["enabled", "=", 1]]]
		for filter in filters:
			self.assertEqual(1, len(vmraid.db.get_values("User", filters=filter, limit=1)))
			# count of last touched rows as per DB-API 2.0 https://peps.python.org/pep-0249/#rowcount
			self.assertGreaterEqual(1, cint(vmraid.db._cursor.rowcount))
			self.assertEqual(2, len(vmraid.db.get_values("User", filters=filter, limit=2)))
			self.assertGreaterEqual(2, cint(vmraid.db._cursor.rowcount))

			# without limits length == count
			self.assertEqual(
				len(vmraid.db.get_values("User", filters=filter)), vmraid.db.count("User", filter)
			)

			vmraid.db.get_value("User", filters=filter)
			self.assertGreaterEqual(1, cint(vmraid.db._cursor.rowcount))

			vmraid.db.exists("User", filter)
			self.assertGreaterEqual(1, cint(vmraid.db._cursor.rowcount))

	def test_escape(self):
		vmraid.db.escape("香港濟生堂製藥有限公司 - IT".encode("utf-8"))

	def test_get_single_value(self):
		# setup
		values_dict = {
			"Float": 1.5,
			"Int": 1,
			"Percent": 55.5,
			"Currency": 12.5,
			"Data": "Test",
			"Date": datetime.datetime.now().date(),
			"Datetime": datetime.datetime.now(),
			"Time": datetime.timedelta(hours=9, minutes=45, seconds=10),
		}
		test_inputs = [
			{"fieldtype": fieldtype, "value": value} for fieldtype, value in values_dict.items()
		]
		for fieldtype in values_dict.keys():
			create_custom_field(
				"Print Settings",
				{
					"fieldname": f"test_{fieldtype.lower()}",
					"label": f"Test {fieldtype}",
					"fieldtype": fieldtype,
				},
			)

		# test
		for inp in test_inputs:
			fieldname = f"test_{inp['fieldtype'].lower()}"
			vmraid.db.set_value("Print Settings", "Print Settings", fieldname, inp["value"])
			self.assertEqual(vmraid.db.get_single_value("Print Settings", fieldname), inp["value"])

		# teardown
		clear_custom_fields("Print Settings")

	def test_log_touched_tables(self):
		vmraid.flags.in_migrate = True
		vmraid.flags.touched_tables = set()
		vmraid.db.set_value("System Settings", "System Settings", "backup_limit", 5)
		self.assertIn("tabSingles", vmraid.flags.touched_tables)

		vmraid.flags.touched_tables = set()
		todo = vmraid.get_doc({"doctype": "ToDo", "description": "Random Description"})
		todo.save()
		self.assertIn("tabToDo", vmraid.flags.touched_tables)

		vmraid.flags.touched_tables = set()
		todo.description = "Another Description"
		todo.save()
		self.assertIn("tabToDo", vmraid.flags.touched_tables)

		if vmraid.db.db_type != "postgres":
			vmraid.flags.touched_tables = set()
			vmraid.db.sql("UPDATE tabToDo SET description = 'Updated Description'")
			self.assertNotIn("tabToDo SET", vmraid.flags.touched_tables)
			self.assertIn("tabToDo", vmraid.flags.touched_tables)

		vmraid.flags.touched_tables = set()
		todo.delete()
		self.assertIn("tabToDo", vmraid.flags.touched_tables)

		vmraid.flags.touched_tables = set()
		create_custom_field("ToDo", {"label": "ToDo Custom Field"})

		self.assertIn("tabToDo", vmraid.flags.touched_tables)
		self.assertIn("tabCustom Field", vmraid.flags.touched_tables)
		vmraid.flags.in_migrate = False
		vmraid.flags.touched_tables.clear()

	def test_db_keywords_as_fields(self):
		"""Tests if DB keywords work as docfield names. If they're wrapped with grave accents."""
		# Using random.choices, picked out a list of 40 keywords for testing
		all_keywords = {
			"mariadb": [
				"CHARACTER",
				"DELAYED",
				"LINES",
				"EXISTS",
				"YEAR_MONTH",
				"LOCALTIME",
				"BOTH",
				"MEDIUMINT",
				"LEFT",
				"BINARY",
				"DEFAULT",
				"KILL",
				"WRITE",
				"SQL_SMALL_RESULT",
				"CURRENT_TIME",
				"CROSS",
				"INHERITS",
				"SELECT",
				"TABLE",
				"ALTER",
				"CURRENT_TIMESTAMP",
				"XOR",
				"CASE",
				"ALL",
				"WHERE",
				"INT",
				"TO",
				"SOME",
				"DAY_MINUTE",
				"ERRORS",
				"OPTIMIZE",
				"REPLACE",
				"HIGH_PRIORITY",
				"VARBINARY",
				"HELP",
				"IS",
				"CHAR",
				"DESCRIBE",
				"KEY",
			],
			"postgres": [
				"WORK",
				"LANCOMPILER",
				"REAL",
				"HAVING",
				"REPEATABLE",
				"DATA",
				"USING",
				"BIT",
				"DEALLOCATE",
				"SERIALIZABLE",
				"CURSOR",
				"INHERITS",
				"ARRAY",
				"TRUE",
				"IGNORE",
				"PARAMETER_MODE",
				"ROW",
				"CHECKPOINT",
				"SHOW",
				"BY",
				"SIZE",
				"SCALE",
				"UNENCRYPTED",
				"WITH",
				"AND",
				"CONVERT",
				"FIRST",
				"SCOPE",
				"WRITE",
				"INTERVAL",
				"CHARACTER_SET_SCHEMA",
				"ADD",
				"SCROLL",
				"NULL",
				"WHEN",
				"TRANSACTION_ACTIVE",
				"INT",
				"FORTRAN",
				"STABLE",
			],
		}
		created_docs = []

		# edit by rushabh: added [:1]
		# don't run every keyword! - if one works, they all do
		fields = all_keywords[vmraid.conf.db_type][:1]
		test_doctype = "ToDo"

		def add_custom_field(field):
			create_custom_field(
				test_doctype,
				{
					"fieldname": field.lower(),
					"label": field.title(),
					"fieldtype": "Data",
				},
			)

		# Create custom fields for test_doctype
		for field in fields:
			add_custom_field(field)

		# Create documents under that doctype and query them via ORM
		for _ in range(10):
			docfields = {key.lower(): random_string(10) for key in fields}
			doc = vmraid.get_doc({"doctype": test_doctype, "description": random_string(20), **docfields})
			doc.insert()
			created_docs.append(doc.name)

		random_field = choice(fields).lower()
		random_doc = choice(created_docs)
		random_value = random_string(20)

		# Testing read
		self.assertEqual(
			list(vmraid.get_all("ToDo", fields=[random_field], limit=1)[0])[0], random_field
		)
		self.assertEqual(
			list(vmraid.get_all("ToDo", fields=[f"`{random_field}` as total"], limit=1)[0])[0], "total"
		)

		# Testing read for distinct and sql functions
		self.assertEqual(
			list(
				vmraid.get_all(
					"ToDo",
					fields=[f"`{random_field}` as total"],
					distinct=True,
					limit=1,
				)[0]
			)[0],
			"total",
		)
		self.assertEqual(
			list(
				vmraid.get_all(
					"ToDo",
					fields=[f"`{random_field}`"],
					distinct=True,
					limit=1,
				)[0]
			)[0],
			random_field,
		)
		self.assertEqual(
			list(vmraid.get_all("ToDo", fields=[f"count(`{random_field}`)"], limit=1)[0])[0],
			"count" if vmraid.conf.db_type == "postgres" else f"count(`{random_field}`)",
		)

		# Testing update
		vmraid.db.set_value(test_doctype, random_doc, random_field, random_value)
		self.assertEqual(vmraid.db.get_value(test_doctype, random_doc, random_field), random_value)

		# Cleanup - delete records and remove custom fields
		for doc in created_docs:
			vmraid.delete_doc(test_doctype, doc)
		clear_custom_fields(test_doctype)

	def test_savepoints(self):
		vmraid.db.rollback()
		save_point = "todonope"

		created_docs = []
		failed_docs = []

		for _ in range(5):
			vmraid.db.savepoint(save_point)
			doc_gone = vmraid.get_doc(doctype="ToDo", description="nope").save()
			failed_docs.append(doc_gone.name)
			vmraid.db.rollback(save_point=save_point)
			doc_kept = vmraid.get_doc(doctype="ToDo", description="nope").save()
			created_docs.append(doc_kept.name)
		vmraid.db.commit()

		for d in failed_docs:
			self.assertFalse(vmraid.db.exists("ToDo", d))
		for d in created_docs:
			self.assertTrue(vmraid.db.exists("ToDo", d))

	def test_savepoints_wrapper(self):
		vmraid.db.rollback()

		class SpecificExc(Exception):
			pass

		created_docs = []
		failed_docs = []

		for _ in range(5):
			with savepoint(catch=SpecificExc):
				doc_kept = vmraid.get_doc(doctype="ToDo", description="nope").save()
				created_docs.append(doc_kept.name)

			with savepoint(catch=SpecificExc):
				doc_gone = vmraid.get_doc(doctype="ToDo", description="nope").save()
				failed_docs.append(doc_gone.name)
				raise SpecificExc

		vmraid.db.commit()

		for d in failed_docs:
			self.assertFalse(vmraid.db.exists("ToDo", d))
		for d in created_docs:
			self.assertTrue(vmraid.db.exists("ToDo", d))

	def test_transaction_writes_error(self):
		from vmraid.database.database import Database

		vmraid.db.rollback()

		vmraid.db.MAX_WRITES_PER_TRANSACTION = 1
		note = vmraid.get_last_doc("ToDo")
		note.description = "changed"
		with self.assertRaises(vmraid.TooManyWritesError) as tmw:
			note.save()

		vmraid.db.MAX_WRITES_PER_TRANSACTION = Database.MAX_WRITES_PER_TRANSACTION

	def test_transaction_write_counting(self):
		note = vmraid.get_doc(doctype="Note", title="transaction counting").insert()

		writes = vmraid.db.transaction_writes
		vmraid.db.set_value("Note", note.name, "content", "abc")
		self.assertEqual(1, vmraid.db.transaction_writes - writes)
		writes = vmraid.db.transaction_writes

		vmraid.db.sql(
			"""
			update `tabNote`
			set content = 'abc'
			where name = %s
			""",
			note.name,
		)
		self.assertEqual(1, vmraid.db.transaction_writes - writes)

	def test_pk_collision_ignoring(self):
		# note has `name` generated from title
		for _ in range(3):
			vmraid.get_doc(doctype="Note", title="duplicate name").insert(ignore_if_duplicate=True)

		with savepoint():
			self.assertRaises(
				vmraid.DuplicateEntryError, vmraid.get_doc(doctype="Note", title="duplicate name").insert
			)
			# recover transaction to continue other tests
			raise Exception

	def test_exists(self):
		dt, dn = "User", "Administrator"
		self.assertEqual(vmraid.db.exists(dt, dn, cache=True), dn)
		self.assertEqual(vmraid.db.exists(dt, dn), dn)
		self.assertEqual(vmraid.db.exists(dt, {"name": ("=", dn)}), dn)

		filters = {"doctype": dt, "name": ("like", "Admin%")}
		self.assertEqual(vmraid.db.exists(filters), dn)
		self.assertEqual(filters["doctype"], dt)  # make sure that doctype was not removed from filters

		self.assertEqual(vmraid.db.exists(dt, [["name", "=", dn]]), dn)


@run_only_if(db_type_is.MARIADB)
class TestDDLCommandsMaria(unittest.TestCase):
	test_table_name = "TestNotes"

	def setUp(self) -> None:
		vmraid.db.commit()
		vmraid.db.sql(
			f"""
			CREATE TABLE `tab{self.test_table_name}` (`id` INT NULL, content TEXT, PRIMARY KEY (`id`));
			"""
		)

	def tearDown(self) -> None:
		vmraid.db.sql(f"DROP TABLE tab{self.test_table_name};")
		self.test_table_name = "TestNotes"

	def test_rename(self) -> None:
		new_table_name = f"{self.test_table_name}_new"
		vmraid.db.rename_table(self.test_table_name, new_table_name)
		check_exists = vmraid.db.sql(
			f"""
			SELECT * FROM INFORMATION_SCHEMA.TABLES
			WHERE TABLE_NAME = N'tab{new_table_name}';
			"""
		)
		self.assertGreater(len(check_exists), 0)
		self.assertIn(f"tab{new_table_name}", check_exists[0])

		# * so this table is deleted after the rename
		self.test_table_name = new_table_name

	def test_describe(self) -> None:
		self.assertEqual(
			(
				("id", "int(11)", "NO", "PRI", None, ""),
				("content", "text", "YES", "", None, ""),
			),
			vmraid.db.describe(self.test_table_name),
		)

	def test_change_type(self) -> None:
		vmraid.db.change_column_type("TestNotes", "id", "varchar(255)")
		test_table_description = vmraid.db.sql(f"DESC tab{self.test_table_name};")
		self.assertGreater(len(test_table_description), 0)
		self.assertIn("varchar(255)", test_table_description[0])

	def test_add_index(self) -> None:
		index_name = "test_index"
		vmraid.db.add_index(self.test_table_name, ["id", "content(50)"], index_name)
		indexs_in_table = vmraid.db.sql(
			f"""
			SHOW INDEX FROM tab{self.test_table_name}
			WHERE Key_name = '{index_name}';
			"""
		)
		self.assertEqual(len(indexs_in_table), 2)


class TestDBSetValue(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.todo1 = vmraid.get_doc(doctype="ToDo", description="test_set_value 1").insert()
		cls.todo2 = vmraid.get_doc(doctype="ToDo", description="test_set_value 2").insert()

	def test_update_single_doctype_field(self):
		value = vmraid.db.get_single_value("System Settings", "deny_multiple_sessions")
		changed_value = not value

		vmraid.db.set_value(
			"System Settings", "System Settings", "deny_multiple_sessions", changed_value
		)
		current_value = vmraid.db.get_single_value("System Settings", "deny_multiple_sessions")
		self.assertEqual(current_value, changed_value)

		changed_value = not current_value
		vmraid.db.set_value("System Settings", None, "deny_multiple_sessions", changed_value)
		current_value = vmraid.db.get_single_value("System Settings", "deny_multiple_sessions")
		self.assertEqual(current_value, changed_value)

		changed_value = not current_value
		vmraid.db.set_single_value("System Settings", "deny_multiple_sessions", changed_value)
		current_value = vmraid.db.get_single_value("System Settings", "deny_multiple_sessions")
		self.assertEqual(current_value, changed_value)

	def test_update_single_row_single_column(self):
		vmraid.db.set_value("ToDo", self.todo1.name, "description", "test_set_value change 1")
		updated_value = vmraid.db.get_value("ToDo", self.todo1.name, "description")
		self.assertEqual(updated_value, "test_set_value change 1")

	def test_update_single_row_multiple_columns(self):
		description, status = "Upated by test_update_single_row_multiple_columns", "Closed"

		vmraid.db.set_value(
			"ToDo",
			self.todo1.name,
			{
				"description": description,
				"status": status,
			},
			update_modified=False,
		)

		updated_desciption, updated_status = vmraid.db.get_value(
			"ToDo", filters={"name": self.todo1.name}, fieldname=["description", "status"]
		)

		self.assertEqual(description, updated_desciption)
		self.assertEqual(status, updated_status)

	def test_update_multiple_rows_single_column(self):
		vmraid.db.set_value(
			"ToDo", {"description": ("like", "%test_set_value%")}, "description", "change 2"
		)

		self.assertEqual(vmraid.db.get_value("ToDo", self.todo1.name, "description"), "change 2")
		self.assertEqual(vmraid.db.get_value("ToDo", self.todo2.name, "description"), "change 2")

	def test_update_multiple_rows_multiple_columns(self):
		todos_to_update = vmraid.get_all(
			"ToDo",
			filters={"description": ("like", "%test_set_value%"), "status": ("!=", "Closed")},
			pluck="name",
		)

		vmraid.db.set_value(
			"ToDo",
			{"description": ("like", "%test_set_value%"), "status": ("!=", "Closed")},
			{"status": "Closed", "priority": "High"},
		)

		test_result = vmraid.get_all(
			"ToDo", filters={"name": ("in", todos_to_update)}, fields=["status", "priority"]
		)

		self.assertTrue(all(x for x in test_result if x["status"] == "Closed"))
		self.assertTrue(all(x for x in test_result if x["priority"] == "High"))

	def test_update_modified_options(self):
		self.todo2.reload()

		todo = self.todo2
		updated_description = f"{todo.description} - by `test_update_modified_options`"
		custom_modified = datetime.datetime.fromisoformat(add_days(now(), 10))
		custom_modified_by = "user_that_doesnt_exist@example.com"

		vmraid.db.set_value("ToDo", todo.name, "description", updated_description, update_modified=False)
		self.assertEqual(updated_description, vmraid.db.get_value("ToDo", todo.name, "description"))
		self.assertEqual(todo.modified, vmraid.db.get_value("ToDo", todo.name, "modified"))

		vmraid.db.set_value(
			"ToDo",
			todo.name,
			"description",
			"test_set_value change 1",
			modified=custom_modified,
			modified_by=custom_modified_by,
		)
		self.assertTupleEqual(
			(custom_modified, custom_modified_by),
			vmraid.db.get_value("ToDo", todo.name, ["modified", "modified_by"]),
		)

	def test_for_update(self):
		self.todo1.reload()

		with patch.object(Database, "sql") as sql_called:
			vmraid.db.set_value(
				self.todo1.doctype,
				self.todo1.name,
				"description",
				f"{self.todo1.description}-edit by `test_for_update`",
			)
			first_query = sql_called.call_args_list[0].args[0]
			second_query = sql_called.call_args_list[1].args[0]

			self.assertTrue(sql_called.call_count == 2)
			self.assertTrue("FOR UPDATE" in first_query)
			if vmraid.conf.db_type == "postgres":
				from vmraid.database.postgres.database import modify_query

				self.assertTrue(modify_query("UPDATE `tabToDo` SET") in second_query)
			if vmraid.conf.db_type == "mariadb":
				self.assertTrue("UPDATE `tabToDo` SET" in second_query)

	def test_cleared_cache(self):
		self.todo2.reload()

		with patch.object(vmraid, "clear_document_cache") as clear_cache:
			vmraid.db.set_value(
				self.todo2.doctype,
				self.todo2.name,
				"description",
				f"{self.todo2.description}-edit by `test_cleared_cache`",
			)
			clear_cache.assert_called()

	def test_update_alias(self):
		args = (self.todo1.doctype, self.todo1.name, "description", "Updated by `test_update_alias`")
		kwargs = {
			"for_update": False,
			"modified": None,
			"modified_by": None,
			"update_modified": True,
			"debug": False,
		}

		self.assertTrue("return self.set_value(" in inspect.getsource(vmraid.db.update))

		with patch.object(Database, "set_value") as set_value:
			vmraid.db.update(*args, **kwargs)
			set_value.assert_called_once()
			set_value.assert_called_with(*args, **kwargs)

	@classmethod
	def tearDownClass(cls):
		vmraid.db.rollback()


@run_only_if(db_type_is.POSTGRES)
class TestDDLCommandsPost(unittest.TestCase):
	test_table_name = "TestNotes"

	def setUp(self) -> None:
		vmraid.db.sql(
			f"""
			CREATE TABLE "tab{self.test_table_name}" ("id" INT NULL, content text, PRIMARY KEY ("id"))
			"""
		)

	def tearDown(self) -> None:
		vmraid.db.sql(f'DROP TABLE "tab{self.test_table_name}"')
		self.test_table_name = "TestNotes"

	def test_rename(self) -> None:
		new_table_name = f"{self.test_table_name}_new"
		vmraid.db.rename_table(self.test_table_name, new_table_name)
		check_exists = vmraid.db.sql(
			f"""
			SELECT EXISTS (
			SELECT FROM information_schema.tables
			WHERE  table_name = 'tab{new_table_name}'
			);
			"""
		)
		self.assertTrue(check_exists[0][0])

		# * so this table is deleted after the rename
		self.test_table_name = new_table_name

	def test_describe(self) -> None:
		self.assertEqual([("id",), ("content",)], vmraid.db.describe(self.test_table_name))

	def test_change_type(self) -> None:
		vmraid.db.change_column_type(self.test_table_name, "id", "varchar(255)")
		check_change = vmraid.db.sql(
			f"""
			SELECT
				table_name,
				column_name,
				data_type
			FROM
				information_schema.columns
			WHERE
				table_name = 'tab{self.test_table_name}'
			"""
		)
		self.assertGreater(len(check_change), 0)
		self.assertIn("character varying", check_change[0])

	def test_add_index(self) -> None:
		index_name = "test_index"
		vmraid.db.add_index(self.test_table_name, ["id", "content(50)"], index_name)
		indexs_in_table = vmraid.db.sql(
			f"""
			SELECT indexname
			FROM pg_indexes
			WHERE tablename = 'tab{self.test_table_name}'
			AND indexname = '{index_name}' ;
			""",
		)
		self.assertEqual(len(indexs_in_table), 1)

	@run_only_if(db_type_is.POSTGRES)
	def test_modify_query(self):
		from vmraid.database.postgres.database import modify_query

		query = "select * from `tabtree b` where lft > 13 and rgt <= 16 and name =1.0 and parent = 4134qrsdc and isgroup = 1.00045"
		self.assertEqual(
			"select * from \"tabtree b\" where lft > '13' and rgt <= '16' and name = '1' and parent = 4134qrsdc and isgroup = 1.00045",
			modify_query(query),
		)

		query = (
			'select locate(".io", "vmraid.io"), locate("3", cast(3 as varchar)), locate("3", 3::varchar)'
		)
		self.assertEqual(
			'select strpos( "vmraid.io", ".io"), strpos( cast(3 as varchar), "3"), strpos( 3::varchar, "3")',
			modify_query(query),
		)

	@run_only_if(db_type_is.POSTGRES)
	def test_modify_values(self):
		from vmraid.database.postgres.database import modify_values

		self.assertEqual(
			{"abcd": "23", "efgh": "23", "ijkl": 23.0345, "mnop": "wow"},
			modify_values({"abcd": 23, "efgh": 23.0, "ijkl": 23.0345, "mnop": "wow"}),
		)
		self.assertEqual(["23", "23", 23.00004345, "wow"], modify_values((23, 23.0, 23.00004345, "wow")))

	def test_sequence_table_creation(self):
		from vmraid.core.doctype.doctype.test_doctype import new_doctype

		dt = new_doctype("autoinc_dt_seq_test", autoname="autoincrement").insert(ignore_permissions=True)

		if vmraid.db.db_type == "postgres":
			self.assertTrue(
				vmraid.db.sql(
					"""select sequence_name FROM information_schema.sequences
				where sequence_name ilike 'autoinc_dt_seq_test%'"""
				)[0][0]
			)
		else:
			self.assertTrue(
				vmraid.db.sql(
					"""select data_type FROM information_schema.tables
				where table_type = 'SEQUENCE' and table_name like 'autoinc_dt_seq_test%'"""
				)[0][0]
			)

		dt.delete(ignore_permissions=True)
