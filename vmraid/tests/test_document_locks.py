# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
import unittest

import vmraid


class TestDocumentLocks(unittest.TestCase):
	def test_locking(self):
		todo = vmraid.get_doc(dict(doctype="ToDo", description="test")).insert()
		todo_1 = vmraid.get_doc("ToDo", todo.name)

		todo.lock()
		self.assertRaises(vmraid.DocumentLockedError, todo_1.lock)
		todo.unlock()

		todo_1.lock()
		self.assertRaises(vmraid.DocumentLockedError, todo.lock)
		todo_1.unlock()
