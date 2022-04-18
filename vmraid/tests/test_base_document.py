import unittest

from vmraid.model.base_document import BaseDocument


class TestBaseDocument(unittest.TestCase):
	def test_docstatus(self):
		doc = BaseDocument({"docstatus": 0})
		self.assertTrue(doc.docstatus.is_draft())
		self.assertEqual(doc.docstatus, 0)

		doc.docstatus = 1
		self.assertTrue(doc.docstatus.is_submitted())
		self.assertEqual(doc.docstatus, 1)

		doc.docstatus = 2
		self.assertTrue(doc.docstatus.is_cancelled())
		self.assertEqual(doc.docstatus, 2)
