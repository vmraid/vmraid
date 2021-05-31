# -*- coding: utf-8 -*-
# Copyright (c) 2015, VMRaid Technologies Pvt. Ltd. and Contributors
# See license.txt
from __future__ import unicode_literals

import base64
import vmraid
import os
import unittest
from vmraid import _
from vmraid.core.doctype.file.file import move_file, get_files_in_folder
from vmraid.utils import get_files_path
# test_records = vmraid.get_test_records('File')

test_content1 = 'Hello'
test_content2 = 'Hello World'


def make_test_doc():
	d = vmraid.new_doc('ToDo')
	d.description = 'Test'
	d.save()
	return d.doctype, d.name


class TestSimpleFile(unittest.TestCase):


	def setUp(self):
		self.attached_to_doctype, self.attached_to_docname = make_test_doc()
		self.test_content = test_content1
		_file = vmraid.get_doc({
			"doctype": "File",
			"file_name": "test1.txt",
			"attached_to_doctype": self.attached_to_doctype,
			"attached_to_name": self.attached_to_docname,
			"content": self.test_content})
		_file.save()
		self.saved_file_url = _file.file_url


	def test_save(self):
		_file = vmraid.get_doc("File", {"file_url": self.saved_file_url})
		content = _file.get_content()
		self.assertEqual(content, self.test_content)


	def tearDown(self):
		# File gets deleted on rollback, so blank
		pass


class TestBase64File(unittest.TestCase):


	def setUp(self):
		self.attached_to_doctype, self.attached_to_docname = make_test_doc()
		self.test_content = base64.b64encode(test_content1.encode('utf-8'))
		_file = vmraid.get_doc({
			"doctype": "File",
			"file_name": "test_base64.txt",
			"attached_to_doctype": self.attached_to_doctype,
			"attached_to_docname": self.attached_to_docname,
			"content": self.test_content,
			"decode": True})
		_file.save()
		self.saved_file_url = _file.file_url


	def test_saved_content(self):
		_file = vmraid.get_doc("File", {"file_url": self.saved_file_url})
		content = _file.get_content()
		self.assertEqual(content, test_content1)


	def tearDown(self):
		# File gets deleted on rollback, so blank
		pass


class TestSameFileName(unittest.TestCase):
	def test_saved_content(self):
		self.attached_to_doctype, self.attached_to_docname = make_test_doc()
		self.test_content1 = test_content1
		self.test_content2 = test_content2
		_file1 = vmraid.get_doc({
			"doctype": "File",
			"file_name": "testing.txt",
			"attached_to_doctype": self.attached_to_doctype,
			"attached_to_name": self.attached_to_docname,
			"content": self.test_content1})
		_file1.save()
		_file2 = vmraid.get_doc({
			"doctype": "File",
			"file_name": "testing.txt",
			"attached_to_doctype": self.attached_to_doctype,
			"attached_to_name": self.attached_to_docname,
			"content": self.test_content2})
		_file2.save()
		self.saved_file_url1 = _file1.file_url
		self.saved_file_url2 = _file2.file_url


		_file = vmraid.get_doc("File", {"file_url": self.saved_file_url1})
		content1 = _file.get_content()
		self.assertEqual(content1, self.test_content1)
		_file = vmraid.get_doc("File", {"file_url": self.saved_file_url2})
		content2 = _file.get_content()
		self.assertEqual(content2, self.test_content2)

	def test_saved_content_private(self):
		_file1 = vmraid.get_doc({
			"doctype": "File",
			"file_name": "testing-private.txt",
			"content": test_content1,
			"is_private": 1
		}).insert()
		_file2 = vmraid.get_doc({
			"doctype": "File",
			"file_name": "testing-private.txt",
			"content": test_content2,
			"is_private": 1
		}).insert()

		_file = vmraid.get_doc("File", {"file_url": _file1.file_url})
		self.assertEqual(_file.get_content(), test_content1)

		_file = vmraid.get_doc("File", {"file_url": _file2.file_url})
		self.assertEqual(_file.get_content(), test_content2)


class TestSameContent(unittest.TestCase):


	def setUp(self):
		self.attached_to_doctype1, self.attached_to_docname1 = make_test_doc()
		self.attached_to_doctype2, self.attached_to_docname2 = make_test_doc()
		self.test_content1 = test_content1
		self.test_content2 = test_content1
		self.orig_filename = 'hello.txt'
		self.dup_filename = 'hello2.txt'
		_file1 = vmraid.get_doc({
			"doctype": "File",
			"file_name": self.orig_filename,
			"attached_to_doctype": self.attached_to_doctype1,
			"attached_to_name": self.attached_to_docname1,
			"content": self.test_content1})
		_file1.save()

		_file2 = vmraid.get_doc({
			"doctype": "File",
			"file_name": self.dup_filename,
			"attached_to_doctype": self.attached_to_doctype2,
			"attached_to_name": self.attached_to_docname2,
			"content": self.test_content2})

		_file2.save()


	def test_saved_content(self):
		self.assertFalse(os.path.exists(get_files_path(self.dup_filename)))

	def test_attachment_limit(self):
		doctype, docname = make_test_doc()
		from vmraid.custom.doctype.property_setter.property_setter import make_property_setter
		limit_property = make_property_setter('ToDo', None, 'max_attachments', 1, 'int', for_doctype=True)
		file1 = vmraid.get_doc({
			"doctype": "File",
			"file_name": 'test-attachment',
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
			"content": 'test'
		})

		file1.insert()

		file2 = vmraid.get_doc({
			"doctype": "File",
			"file_name": 'test-attachment',
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
			"content": 'test2'
		})

		self.assertRaises(vmraid.exceptions.AttachmentLimitReached, file2.insert)
		limit_property.delete()
		vmraid.clear_cache(doctype='ToDo')

	def tearDown(self):
		# File gets deleted on rollback, so blank
		pass


class TestFile(unittest.TestCase):
	def setUp(self):
		vmraid.set_user('Administrator')
		self.delete_test_data()
		self.upload_file()

	def tearDown(self):
		try:
			vmraid.get_doc("File", {"file_name": "file_copy.txt"}).delete()
		except vmraid.DoesNotExistError:
			pass


	def delete_test_data(self):
		for f in vmraid.db.sql('''select name, file_name from tabFile where
			is_home_folder = 0 and is_attachments_folder = 0 order by creation desc'''):
			vmraid.delete_doc("File", f[0])


	def upload_file(self):
		_file = vmraid.get_doc({
			"doctype": "File",
			"file_name": "file_copy.txt",
			"attached_to_name": "",
			"attached_to_doctype": "",
			"folder": self.get_folder("Test Folder 1", "Home").name,
			"content": "Testing file copy example."})
		_file.save()
		self.saved_folder = _file.folder
		self.saved_name = _file.name
		self.saved_filename = get_files_path(_file.file_name)


	def get_folder(self, folder_name, parent_folder="Home"):
		return vmraid.get_doc({
			"doctype": "File",
			"file_name": _(folder_name),
			"is_folder": 1,
			"folder": _(parent_folder)
		}).insert()


	def tests_after_upload(self):
		self.assertEqual(self.saved_folder, _("Home/Test Folder 1"))
		file_folder = vmraid.db.get_value("File", self.saved_name, "folder")
		self.assertEqual(file_folder, _("Home/Test Folder 1"))


	def test_file_copy(self):
		folder = self.get_folder("Test Folder 2", "Home")

		file = vmraid.get_doc("File", {"file_name": "file_copy.txt"})
		move_file([{"name": file.name}], folder.name, file.folder)
		file = vmraid.get_doc("File", {"file_name": "file_copy.txt"})

		self.assertEqual(_("Home/Test Folder 2"), file.folder)

	def test_folder_depth(self):
		result1 = self.get_folder("d1", "Home")
		self.assertEqual(result1.name, "Home/d1")
		result2 = self.get_folder("d2", "Home/d1")
		self.assertEqual(result2.name, "Home/d1/d2")
		result3 = self.get_folder("d3", "Home/d1/d2")
		self.assertEqual(result3.name, "Home/d1/d2/d3")
		result4 = self.get_folder("d4", "Home/d1/d2/d3")
		_file = vmraid.get_doc({
			"doctype": "File",
			"file_name": "folder_copy.txt",
			"attached_to_name": "",
			"attached_to_doctype": "",
			"folder": result4.name,
			"content": "Testing folder copy example"})
		_file.save()


	def test_folder_copy(self):
		folder = self.get_folder("Test Folder 2", "Home")
		folder = self.get_folder("Test Folder 3", "Home/Test Folder 2")
		_file = vmraid.get_doc({
			"doctype": "File",
			"file_name": "folder_copy.txt",
			"attached_to_name": "",
			"attached_to_doctype": "",
			"folder": folder.name,
			"content": "Testing folder copy example"})
		_file.save()

		move_file([{"name": folder.name}], 'Home/Test Folder 1', folder.folder)

		file = vmraid.get_doc("File", {"file_name":"folder_copy.txt"})
		file_copy_txt = vmraid.get_value("File", {"file_name":"file_copy.txt"})
		if file_copy_txt:
			vmraid.get_doc("File", file_copy_txt).delete()

		self.assertEqual(_("Home/Test Folder 1/Test Folder 3"), file.folder)


	def test_default_folder(self):
		d = vmraid.get_doc({
			"doctype": "File",
			"file_name": _("Test_Folder"),
			"is_folder": 1
		})
		d.save()
		self.assertEqual(d.folder, "Home")


	def test_on_delete(self):
		file = vmraid.get_doc("File", {"file_name": "file_copy.txt"})
		file.delete()

		self.assertEqual(vmraid.db.get_value("File", _("Home/Test Folder 1"), "file_size"), 0)

		folder = self.get_folder("Test Folder 3", "Home/Test Folder 1")
		_file = vmraid.get_doc({
			"doctype": "File",
			"file_name": "folder_copy.txt",
			"attached_to_name": "",
			"attached_to_doctype": "",
			"folder": folder.name,
			"content": "Testing folder copy example"})
		_file.save()

		folder = vmraid.get_doc("File", "Home/Test Folder 1/Test Folder 3")
		self.assertRaises(vmraid.ValidationError, folder.delete)

	def test_same_file_url_update(self):
		attached_to_doctype1, attached_to_docname1 = make_test_doc()
		attached_to_doctype2, attached_to_docname2 = make_test_doc()

		file1 = vmraid.get_doc({
			"doctype": "File",
			"file_name": 'file1.txt',
			"attached_to_doctype": attached_to_doctype1,
			"attached_to_name": attached_to_docname1,
			"is_private": 1,
			"content": test_content1}).insert()

		file2 = vmraid.get_doc({
			"doctype": "File",
			"file_name": 'file2.txt',
			"attached_to_doctype": attached_to_doctype2,
			"attached_to_name": attached_to_docname2,
			"is_private": 1,
			"content": test_content1}).insert()

		self.assertEqual(file1.is_private, file2.is_private, 1)
		self.assertEqual(file1.file_url, file2.file_url)
		self.assertTrue(os.path.exists(file1.get_full_path()))

		file1.is_private = 0
		file1.save()

		file2 = vmraid.get_doc('File', file2.name)

		self.assertEqual(file1.is_private, file2.is_private, 0)
		self.assertEqual(file1.file_url, file2.file_url)
		self.assertTrue(os.path.exists(file2.get_full_path()))

	def test_parent_directory_validation_in_file_url(self):
		file1 = vmraid.get_doc({
			"doctype": "File",
			"file_name": 'parent_dir.txt',
			"attached_to_doctype": "",
			"attached_to_name": "",
			"is_private": 1,
			"content": test_content1}).insert()

		file1.file_url = '/private/files/../test.txt'
		self.assertRaises(vmraid.exceptions.ValidationError, file1.save)

		# No validation to see if file exists
		file1.reload()
		file1.file_url = '/private/files/parent_dir2.txt'
		file1.save()

class TestAttachment(unittest.TestCase):
	test_doctype = 'Test For Attachment'

	def setUp(self):
		if vmraid.db.exists('DocType', self.test_doctype):
			return

		vmraid.get_doc(
			doctype='DocType',
			name=self.test_doctype,
			module='Custom',
			custom=1,
			fields=[
				{'label': 'Title', 'fieldname': 'title', 'fieldtype': 'Data'},
				{'label': 'Attachment', 'fieldname': 'attachment', 'fieldtype': 'Attach'},
			]
		).insert()

	def tearDown(self):
		vmraid.delete_doc('DocType', self.test_doctype)

	def test_file_attachment_on_update(self):
		doc = vmraid.get_doc(
			doctype=self.test_doctype,
			title='test for attachment on update'
		).insert()

		file = vmraid.get_doc({
			'doctype': 'File',
			'file_name': 'test_attach.txt',
			'content': 'Test Content'
		})
		file.save()

		doc.attachment = file.file_url
		doc.save()

		exists = vmraid.db.exists('File', {
			'file_name': 'test_attach.txt',
			'file_url': file.file_url,
			'attached_to_doctype': self.test_doctype,
			'attached_to_name': doc.name,
			'attached_to_field': 'attachment'
		})

		self.assertTrue(exists)


class TestAttachmentsAccess(unittest.TestCase):

	def test_attachments_access(self):

		vmraid.set_user('test4@example.com')
		self.attached_to_doctype, self.attached_to_docname = make_test_doc()

		vmraid.get_doc({
			"doctype": "File",
			"file_name": 'test_user.txt',
			"attached_to_doctype": self.attached_to_doctype,
			"attached_to_name": self.attached_to_docname,
			"content": 'Testing User'
		}).insert()

		vmraid.get_doc({
			"doctype": "File",
			"file_name": "test_user_home.txt",
			"content": 'User Home',
		}).insert()

		vmraid.set_user('test@example.com')

		vmraid.get_doc({
			"doctype": "File",
			"file_name": 'test_system_manager.txt',
			"attached_to_doctype": self.attached_to_doctype,
			"attached_to_name": self.attached_to_docname,
			"content": 'Testing System Manager'
		}).insert()

		vmraid.get_doc({
			"doctype": "File",
			"file_name": "test_sm_home.txt",
			"content": 'System Manager Home',
		}).insert()

		system_manager_files = [file.file_name for file in get_files_in_folder('Home')['files']]
		system_manager_attachments_files = [file.file_name for file in get_files_in_folder('Home/Attachments')['files']]

		vmraid.set_user('test4@example.com')
		user_files = [file.file_name for file in get_files_in_folder('Home')['files']]
		user_attachments_files = [file.file_name for file in get_files_in_folder('Home/Attachments')['files']]

		self.assertIn('test_sm_home.txt', system_manager_files)
		self.assertNotIn('test_sm_home.txt', user_files)
		self.assertIn('test_user_home.txt', system_manager_files)
		self.assertIn('test_user_home.txt', user_files)

		self.assertIn('test_system_manager.txt', system_manager_attachments_files)
		self.assertNotIn('test_system_manager.txt', user_attachments_files)
		self.assertIn('test_user.txt', system_manager_attachments_files)
		self.assertIn('test_user.txt', user_attachments_files)

		vmraid.set_user('Administrator')
		vmraid.db.rollback()
