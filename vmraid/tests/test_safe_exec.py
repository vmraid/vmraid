import unittest

import vmraid
from vmraid.utils.safe_exec import get_safe_globals, safe_exec


class TestSafeExec(unittest.TestCase):
	def test_import_fails(self):
		self.assertRaises(ImportError, safe_exec, "import os")

	def test_internal_attributes(self):
		self.assertRaises(SyntaxError, safe_exec, "().__class__.__call__")

	def test_utils(self):
		_locals = dict(out=None)
		safe_exec("""out = vmraid.utils.cint("1")""", None, _locals)
		self.assertEqual(_locals["out"], 1)

	def test_safe_eval(self):
		self.assertEqual(vmraid.safe_eval("1+1"), 2)
		self.assertRaises(AttributeError, vmraid.safe_eval, "vmraid.utils.os.path", get_safe_globals())

	def test_sql(self):
		_locals = dict(out=None)
		safe_exec(
			"""out = vmraid.db.sql("select name from tabDocType where name='DocType'")""", None, _locals
		)
		self.assertEqual(_locals["out"][0][0], "DocType")

		self.assertRaises(
			vmraid.PermissionError, safe_exec, 'vmraid.db.sql("update tabToDo set description=NULL")'
		)

	def test_query_builder(self):
		_locals = dict(out=None)
		safe_exec(
			script="""out = vmraid.qb.from_("User").select(vmraid.qb.terms.PseudoColumn("Max(name)")).run()""",
			_globals=None,
			_locals=_locals,
		)
		self.assertEqual(vmraid.db.sql("SELECT Max(name) FROM tabUser"), _locals["out"])

	def test_safe_query_builder(self):
		self.assertRaises(
			vmraid.PermissionError, safe_exec, """vmraid.qb.from_("User").delete().run()"""
		)

	def test_call(self):
		# call non whitelisted method
		self.assertRaises(vmraid.PermissionError, safe_exec, """vmraid.call("vmraid.get_user")""")

		# call whitelisted method
		safe_exec("""vmraid.call("ping")""")

	def test_enqueue(self):
		# enqueue non whitelisted method
		self.assertRaises(
			vmraid.PermissionError, safe_exec, """vmraid.enqueue("vmraid.get_user", now=True)"""
		)

		# enqueue whitelisted method
		safe_exec("""vmraid.enqueue("ping", now=True)""")
