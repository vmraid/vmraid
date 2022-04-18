# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE
"""Use blog post test to test user permissions logic"""

import vmraid
import vmraid.defaults
import vmraid.model.meta
from vmraid.core.doctype.user_permission.user_permission import clear_user_permissions
from vmraid.core.page.permission_manager.permission_manager import reset, update
from vmraid.desk.form.load import getdoc
from vmraid.permissions import (
	add_permission,
	add_user_permission,
	clear_user_permissions_for_doctype,
	get_doc_permissions,
	remove_user_permission,
	update_permission_property,
)
from vmraid.test_runner import make_test_records_for_doctype
from vmraid.tests.utils import VMRaidTestCase
from vmraid.utils.data import now_datetime

test_dependencies = ["Blogger", "Blog Post", "User", "Contact", "Salutation"]


class TestPermissions(VMRaidTestCase):
	def setUp(self):
		vmraid.clear_cache(doctype="Blog Post")

		if not vmraid.flags.permission_user_setup_done:
			user = vmraid.get_doc("User", "test1@example.com")
			user.add_roles("Website Manager")
			user.add_roles("System Manager")

			user = vmraid.get_doc("User", "test2@example.com")
			user.add_roles("Blogger")

			user = vmraid.get_doc("User", "test3@example.com")
			user.add_roles("Sales User")

			user = vmraid.get_doc("User", "testperm@example.com")
			user.add_roles("Website Manager")

			vmraid.flags.permission_user_setup_done = True

		reset("Blogger")
		reset("Blog Post")

		vmraid.db.delete("User Permission")

		vmraid.set_user("test1@example.com")

	def tearDown(self):
		vmraid.set_user("Administrator")
		vmraid.db.set_value("Blogger", "_Test Blogger 1", "user", None)

		clear_user_permissions_for_doctype("Blog Category")
		clear_user_permissions_for_doctype("Blog Post")
		clear_user_permissions_for_doctype("Blogger")

	@staticmethod
	def set_strict_user_permissions(ignore):
		ss = vmraid.get_doc("System Settings")
		ss.apply_strict_user_permissions = ignore
		ss.flags.ignore_mandatory = 1
		ss.save()

	def test_basic_permission(self):
		post = vmraid.get_doc("Blog Post", "-test-blog-post")
		self.assertTrue(post.has_permission("read"))

	def test_select_permission(self):
		# grant only select perm to blog post
		add_permission("Blog Post", "Sales User", 0)
		update_permission_property("Blog Post", "Sales User", 0, "select", 1)
		update_permission_property("Blog Post", "Sales User", 0, "read", 0)
		update_permission_property("Blog Post", "Sales User", 0, "write", 0)

		vmraid.clear_cache(doctype="Blog Post")
		vmraid.set_user("test3@example.com")

		# validate select perm
		post = vmraid.get_doc("Blog Post", "-test-blog-post")
		self.assertTrue(post.has_permission("select"))

		# validate does not have read and write perm
		self.assertFalse(post.has_permission("read"))
		self.assertRaises(vmraid.PermissionError, post.save)

	def test_user_permissions_in_doc(self):
		add_user_permission("Blog Category", "-test-blog-category-1", "test2@example.com")

		vmraid.set_user("test2@example.com")

		post = vmraid.get_doc("Blog Post", "-test-blog-post")
		self.assertFalse(post.has_permission("read"))
		self.assertFalse(get_doc_permissions(post).get("read"))

		post1 = vmraid.get_doc("Blog Post", "-test-blog-post-1")
		self.assertTrue(post1.has_permission("read"))
		self.assertTrue(get_doc_permissions(post1).get("read"))

	def test_user_permissions_in_report(self):
		add_user_permission("Blog Category", "-test-blog-category-1", "test2@example.com")

		vmraid.set_user("test2@example.com")
		names = [d.name for d in vmraid.get_list("Blog Post", fields=["name", "blog_category"])]

		self.assertTrue("-test-blog-post-1" in names)
		self.assertFalse("-test-blog-post" in names)

	def test_default_values(self):
		doc = vmraid.new_doc("Blog Post")
		self.assertFalse(doc.get("blog_category"))

		# Fetch default based on single user permission
		add_user_permission("Blog Category", "-test-blog-category-1", "test2@example.com")

		vmraid.set_user("test2@example.com")
		doc = vmraid.new_doc("Blog Post")
		self.assertEqual(doc.get("blog_category"), "-test-blog-category-1")

		# Don't fetch default if user permissions is more than 1
		add_user_permission(
			"Blog Category", "-test-blog-category", "test2@example.com", ignore_permissions=True
		)
		vmraid.clear_cache()
		doc = vmraid.new_doc("Blog Post")
		self.assertFalse(doc.get("blog_category"))

		# Fetch user permission set as default from multiple user permission
		add_user_permission(
			"Blog Category",
			"-test-blog-category-2",
			"test2@example.com",
			ignore_permissions=True,
			is_default=1,
		)
		vmraid.clear_cache()
		doc = vmraid.new_doc("Blog Post")
		self.assertEqual(doc.get("blog_category"), "-test-blog-category-2")

	def test_user_link_match_doc(self):
		blogger = vmraid.get_doc("Blogger", "_Test Blogger 1")
		blogger.user = "test2@example.com"
		blogger.save()

		vmraid.set_user("test2@example.com")

		post = vmraid.get_doc("Blog Post", "-test-blog-post-2")
		self.assertTrue(post.has_permission("read"))

		post1 = vmraid.get_doc("Blog Post", "-test-blog-post-1")
		self.assertFalse(post1.has_permission("read"))

	def test_user_link_match_report(self):
		blogger = vmraid.get_doc("Blogger", "_Test Blogger 1")
		blogger.user = "test2@example.com"
		blogger.save()

		vmraid.set_user("test2@example.com")

		names = [d.name for d in vmraid.get_list("Blog Post", fields=["name", "owner"])]
		self.assertTrue("-test-blog-post-2" in names)
		self.assertFalse("-test-blog-post-1" in names)

	def test_set_user_permissions(self):
		vmraid.set_user("test1@example.com")
		add_user_permission("Blog Post", "-test-blog-post", "test2@example.com")

	def test_not_allowed_to_set_user_permissions(self):
		vmraid.set_user("test2@example.com")

		# this user can't add user permissions
		self.assertRaises(
			vmraid.PermissionError, add_user_permission, "Blog Post", "-test-blog-post", "test2@example.com"
		)

	def test_read_if_explicit_user_permissions_are_set(self):
		self.test_set_user_permissions()

		vmraid.set_user("test2@example.com")

		# user can only access permitted blog post
		doc = vmraid.get_doc("Blog Post", "-test-blog-post")
		self.assertTrue(doc.has_permission("read"))

		# and not this one
		doc = vmraid.get_doc("Blog Post", "-test-blog-post-1")
		self.assertFalse(doc.has_permission("read"))

	def test_not_allowed_to_remove_user_permissions(self):
		self.test_set_user_permissions()

		vmraid.set_user("test2@example.com")

		# user cannot remove their own user permissions
		self.assertRaises(
			vmraid.PermissionError,
			remove_user_permission,
			"Blog Post",
			"-test-blog-post",
			"test2@example.com",
		)

	def test_user_permissions_if_applied_on_doc_being_evaluated(self):
		vmraid.set_user("test2@example.com")
		doc = vmraid.get_doc("Blog Post", "-test-blog-post-1")
		self.assertTrue(doc.has_permission("read"))

		vmraid.set_user("test1@example.com")
		add_user_permission("Blog Post", "-test-blog-post", "test2@example.com")

		vmraid.set_user("test2@example.com")
		doc = vmraid.get_doc("Blog Post", "-test-blog-post-1")
		self.assertFalse(doc.has_permission("read"))

		doc = vmraid.get_doc("Blog Post", "-test-blog-post")
		self.assertTrue(doc.has_permission("read"))

	def test_set_standard_fields_manually(self):
		# check that creation and owner cannot be set manually
		from datetime import timedelta

		fake_creation = now_datetime() + timedelta(days=-7)
		fake_owner = vmraid.db.get_value("User", {"name": ("!=", vmraid.session.user)})

		d = vmraid.new_doc("ToDo")
		d.description = "ToDo created via test_set_standard_fields_manually"
		d.creation = fake_creation
		d.owner = fake_owner
		d.save()
		self.assertNotEqual(d.creation, fake_creation)
		self.assertNotEqual(d.owner, fake_owner)

	def test_dont_change_standard_constants(self):
		# check that Document.creation cannot be changed
		user = vmraid.get_doc("User", vmraid.session.user)
		user.creation = now_datetime()
		self.assertRaises(vmraid.CannotChangeConstantError, user.save)

		# check that Document.owner cannot be changed
		user.reload()
		user.owner = "Guest"
		self.assertRaises(vmraid.CannotChangeConstantError, user.save)

	def test_set_only_once(self):
		blog_post = vmraid.get_meta("Blog Post")
		doc = vmraid.get_doc("Blog Post", "-test-blog-post-1")
		doc.db_set("title", "Old")
		blog_post.get_field("title").set_only_once = 1
		doc.title = "New"
		self.assertRaises(vmraid.CannotChangeConstantError, doc.save)
		blog_post.get_field("title").set_only_once = 0

	def test_set_only_once_child_table_rows(self):
		doctype_meta = vmraid.get_meta("DocType")
		doctype_meta.get_field("fields").set_only_once = 1
		doc = vmraid.get_doc("DocType", "Blog Post")

		# remove last one
		doc.fields = doc.fields[:-1]
		self.assertRaises(vmraid.CannotChangeConstantError, doc.save)
		vmraid.clear_cache(doctype="DocType")

	def test_set_only_once_child_table_row_value(self):
		doctype_meta = vmraid.get_meta("DocType")
		doctype_meta.get_field("fields").set_only_once = 1
		doc = vmraid.get_doc("DocType", "Blog Post")

		# change one property from the child table
		doc.fields[-1].fieldtype = "Check"
		self.assertRaises(vmraid.CannotChangeConstantError, doc.save)
		vmraid.clear_cache(doctype="DocType")

	def test_set_only_once_child_table_okay(self):
		doctype_meta = vmraid.get_meta("DocType")
		doctype_meta.get_field("fields").set_only_once = 1
		doc = vmraid.get_doc("DocType", "Blog Post")

		doc.load_doc_before_save()
		self.assertFalse(doc.validate_set_only_once())
		vmraid.clear_cache(doctype="DocType")

	def test_user_permission_doctypes(self):
		add_user_permission("Blog Category", "-test-blog-category-1", "test2@example.com")
		add_user_permission("Blogger", "_Test Blogger 1", "test2@example.com")

		vmraid.set_user("test2@example.com")

		vmraid.clear_cache(doctype="Blog Post")

		doc = vmraid.get_doc("Blog Post", "-test-blog-post")
		self.assertFalse(doc.has_permission("read"))

		doc = vmraid.get_doc("Blog Post", "-test-blog-post-2")
		self.assertTrue(doc.has_permission("read"))

		vmraid.clear_cache(doctype="Blog Post")

	def if_owner_setup(self):
		update("Blog Post", "Blogger", 0, "if_owner", 1)

		add_user_permission("Blog Category", "-test-blog-category-1", "test2@example.com")
		add_user_permission("Blogger", "_Test Blogger 1", "test2@example.com")

		vmraid.clear_cache(doctype="Blog Post")

	def test_insert_if_owner_with_user_permissions(self):
		"""If `If Owner` is checked for a Role, check if that document
		is allowed to be read, updated, submitted, etc. except be created,
		even if the document is restricted based on User Permissions."""
		vmraid.delete_doc("Blog Post", "-test-blog-post-title")

		self.if_owner_setup()

		vmraid.set_user("test2@example.com")

		doc = vmraid.get_doc(
			{
				"doctype": "Blog Post",
				"blog_category": "-test-blog-category",
				"blogger": "_Test Blogger 1",
				"title": "_Test Blog Post Title",
				"content": "_Test Blog Post Content",
			}
		)

		self.assertRaises(vmraid.PermissionError, doc.insert)

		vmraid.set_user("test1@example.com")
		add_user_permission("Blog Category", "-test-blog-category", "test2@example.com")

		vmraid.set_user("test2@example.com")
		doc.insert()

		vmraid.set_user("Administrator")
		remove_user_permission("Blog Category", "-test-blog-category", "test2@example.com")

		vmraid.set_user("test2@example.com")
		doc = vmraid.get_doc(doc.doctype, doc.name)
		self.assertTrue(doc.has_permission("read"))
		self.assertTrue(doc.has_permission("write"))
		self.assertFalse(doc.has_permission("create"))

		# delete created record
		vmraid.set_user("Administrator")
		vmraid.delete_doc("Blog Post", "-test-blog-post-title")

	def test_ignore_user_permissions_if_missing(self):
		"""If there are no user permissions, then allow as per role"""

		add_user_permission("Blog Category", "-test-blog-category", "test2@example.com")
		vmraid.set_user("test2@example.com")

		doc = vmraid.get_doc(
			{
				"doctype": "Blog Post",
				"blog_category": "-test-blog-category-2",
				"blogger": "_Test Blogger 1",
				"title": "_Test Blog Post Title",
				"content": "_Test Blog Post Content",
			}
		)

		self.assertFalse(doc.has_permission("write"))

		vmraid.set_user("Administrator")
		remove_user_permission("Blog Category", "-test-blog-category", "test2@example.com")

		vmraid.set_user("test2@example.com")
		self.assertTrue(doc.has_permission("write"))

	def test_strict_user_permissions(self):
		"""If `Strict User Permissions` is checked in System Settings,
		show records even if User Permissions are missing for a linked
		doctype"""

		vmraid.set_user("Administrator")
		vmraid.db.delete("Contact")
		vmraid.db.delete("Contact Email")
		vmraid.db.delete("Contact Phone")

		reset("Salutation")
		reset("Contact")

		make_test_records_for_doctype("Contact", force=True)

		add_user_permission("Salutation", "Mr", "test3@example.com")
		self.set_strict_user_permissions(0)

		allowed_contact = vmraid.get_doc("Contact", "_Test Contact For _Test Customer")
		other_contact = vmraid.get_doc("Contact", "_Test Contact For _Test Supplier")

		vmraid.set_user("test3@example.com")
		self.assertTrue(allowed_contact.has_permission("read"))
		self.assertTrue(other_contact.has_permission("read"))
		self.assertEqual(len(vmraid.get_list("Contact")), 2)

		vmraid.set_user("Administrator")
		self.set_strict_user_permissions(1)

		vmraid.set_user("test3@example.com")
		self.assertTrue(allowed_contact.has_permission("read"))
		self.assertFalse(other_contact.has_permission("read"))
		self.assertTrue(len(vmraid.get_list("Contact")), 1)

		vmraid.set_user("Administrator")
		self.set_strict_user_permissions(0)

		clear_user_permissions_for_doctype("Salutation")
		clear_user_permissions_for_doctype("Contact")

	def test_user_permissions_not_applied_if_user_can_edit_user_permissions(self):
		add_user_permission("Blogger", "_Test Blogger 1", "test1@example.com")

		# test1@example.com has rights to create user permissions
		# so it should not matter if explicit user permissions are not set
		self.assertTrue(vmraid.get_doc("Blogger", "_Test Blogger").has_permission("read"))

	def test_user_permission_is_not_applied_if_user_roles_does_not_have_permission(self):
		add_user_permission("Blog Post", "-test-blog-post-1", "test3@example.com")
		vmraid.set_user("test3@example.com")
		doc = vmraid.get_doc("Blog Post", "-test-blog-post-1")
		self.assertFalse(doc.has_permission("read"))

		vmraid.set_user("Administrator")
		user = vmraid.get_doc("User", "test3@example.com")
		user.add_roles("Blogger")
		vmraid.set_user("test3@example.com")
		self.assertTrue(doc.has_permission("read"))

		vmraid.set_user("Administrator")
		user.remove_roles("Blogger")

	def test_contextual_user_permission(self):
		# should be applicable for across all doctypes
		add_user_permission("Blogger", "_Test Blogger", "test2@example.com")
		# should be applicable only while accessing Blog Post
		add_user_permission(
			"Blogger", "_Test Blogger 1", "test2@example.com", applicable_for="Blog Post"
		)
		# should be applicable only while accessing User
		add_user_permission("Blogger", "_Test Blogger 2", "test2@example.com", applicable_for="User")

		posts = vmraid.get_all("Blog Post", fields=["name", "blogger"])

		# Get all posts for admin
		self.assertEqual(len(posts), 4)

		vmraid.set_user("test2@example.com")

		posts = vmraid.get_list("Blog Post", fields=["name", "blogger"])

		# Should get only posts with allowed blogger via user permission
		# only '_Test Blogger', '_Test Blogger 1' are allowed in Blog Post
		self.assertEqual(len(posts), 3)

		for post in posts:
			self.assertIn(
				post.blogger,
				["_Test Blogger", "_Test Blogger 1"],
				"A post from {} is not expected.".format(post.blogger),
			)

	def test_if_owner_permission_overrides_properly(self):
		# check if user is not granted access if the user is not the owner of the doc
		# Blogger has only read access on the blog post unless he is the owner of the blog
		update("Blog Post", "Blogger", 0, "if_owner", 1)
		update("Blog Post", "Blogger", 0, "read", 1)
		update("Blog Post", "Blogger", 0, "write", 1)
		update("Blog Post", "Blogger", 0, "delete", 1)

		# currently test2 user has not created any document
		# still he should be able to do get_list query which should
		# not raise permission error but simply return empty list
		vmraid.set_user("test2@example.com")
		self.assertEqual(vmraid.get_list("Blog Post"), [])

		vmraid.set_user("Administrator")

		# creates a custom docperm with just read access
		# now any user can read any blog post (but other rights are limited to the blog post owner)
		add_permission("Blog Post", "Blogger")
		vmraid.clear_cache(doctype="Blog Post")

		vmraid.delete_doc("Blog Post", "-test-blog-post-title")

		vmraid.set_user("test1@example.com")

		doc = vmraid.get_doc(
			{
				"doctype": "Blog Post",
				"blog_category": "-test-blog-category",
				"blogger": "_Test Blogger 1",
				"title": "_Test Blog Post Title",
				"content": "_Test Blog Post Content",
			}
		)

		doc.insert()

		vmraid.set_user("test2@example.com")
		doc = vmraid.get_doc(doc.doctype, doc.name)

		self.assertTrue(doc.has_permission("read"))
		self.assertFalse(doc.has_permission("write"))
		self.assertFalse(doc.has_permission("delete"))

		# check if owner of the doc has the access that is available only for the owner of the doc
		vmraid.set_user("test1@example.com")
		doc = vmraid.get_doc(doc.doctype, doc.name)

		self.assertTrue(doc.has_permission("read"))
		self.assertTrue(doc.has_permission("write"))
		self.assertTrue(doc.has_permission("delete"))

		# delete the created doc
		vmraid.delete_doc("Blog Post", "-test-blog-post-title")

	def test_if_owner_permission_on_getdoc(self):
		update("Blog Post", "Blogger", 0, "if_owner", 1)
		update("Blog Post", "Blogger", 0, "read", 1)
		update("Blog Post", "Blogger", 0, "write", 1)
		update("Blog Post", "Blogger", 0, "delete", 1)
		vmraid.clear_cache(doctype="Blog Post")

		vmraid.set_user("test1@example.com")

		doc = vmraid.get_doc(
			{
				"doctype": "Blog Post",
				"blog_category": "-test-blog-category",
				"blogger": "_Test Blogger 1",
				"title": "_Test Blog Post Title New",
				"content": "_Test Blog Post Content",
			}
		)

		doc.insert()

		getdoc("Blog Post", doc.name)
		doclist = [d.name for d in vmraid.response.docs]
		self.assertTrue(doc.name in doclist)

		vmraid.set_user("test2@example.com")
		self.assertRaises(vmraid.PermissionError, getdoc, "Blog Post", doc.name)

	def test_if_owner_permission_on_get_list(self):
		doc = vmraid.get_doc(
			{
				"doctype": "Blog Post",
				"blog_category": "-test-blog-category",
				"blogger": "_Test Blogger 1",
				"title": "_Test If Owner Permissions on Get List",
				"content": "_Test Blog Post Content",
			}
		)

		doc.insert(ignore_if_duplicate=True)

		update("Blog Post", "Blogger", 0, "if_owner", 1)
		update("Blog Post", "Blogger", 0, "read", 1)
		user = vmraid.get_doc("User", "test2@example.com")
		user.add_roles("Website Manager")
		vmraid.clear_cache(doctype="Blog Post")

		vmraid.set_user("test2@example.com")
		self.assertIn(doc.name, vmraid.get_list("Blog Post", pluck="name"))

		# Become system manager to remove role
		vmraid.set_user("test1@example.com")
		user.remove_roles("Website Manager")
		vmraid.clear_cache(doctype="Blog Post")

		vmraid.set_user("test2@example.com")
		self.assertNotIn(doc.name, vmraid.get_list("Blog Post", pluck="name"))

	def test_if_owner_permission_on_delete(self):
		update("Blog Post", "Blogger", 0, "if_owner", 1)
		update("Blog Post", "Blogger", 0, "read", 1)
		update("Blog Post", "Blogger", 0, "write", 1)
		update("Blog Post", "Blogger", 0, "delete", 1)

		# Remove delete perm
		update("Blog Post", "Website Manager", 0, "delete", 0)

		vmraid.clear_cache(doctype="Blog Post")

		vmraid.set_user("test2@example.com")

		doc = vmraid.get_doc(
			{
				"doctype": "Blog Post",
				"blog_category": "-test-blog-category",
				"blogger": "_Test Blogger 1",
				"title": "_Test Blog Post Title New 1",
				"content": "_Test Blog Post Content",
			}
		)

		doc.insert()

		getdoc("Blog Post", doc.name)
		doclist = [d.name for d in vmraid.response.docs]
		self.assertTrue(doc.name in doclist)

		vmraid.set_user("testperm@example.com")

		# Website Manager able to read
		getdoc("Blog Post", doc.name)
		doclist = [d.name for d in vmraid.response.docs]
		self.assertTrue(doc.name in doclist)

		# Website Manager should not be able to delete
		self.assertRaises(vmraid.PermissionError, vmraid.delete_doc, "Blog Post", doc.name)

		vmraid.set_user("test2@example.com")
		vmraid.delete_doc("Blog Post", "-test-blog-post-title-new-1")
		update("Blog Post", "Website Manager", 0, "delete", 1)

	def test_clear_user_permissions(self):
		current_user = vmraid.session.user
		vmraid.set_user("Administrator")
		clear_user_permissions_for_doctype("Blog Category", "test2@example.com")
		clear_user_permissions_for_doctype("Blog Post", "test2@example.com")

		add_user_permission("Blog Post", "-test-blog-post-1", "test2@example.com")
		add_user_permission("Blog Post", "-test-blog-post-2", "test2@example.com")
		add_user_permission("Blog Category", "-test-blog-category-1", "test2@example.com")

		deleted_user_permission_count = clear_user_permissions("test2@example.com", "Blog Post")

		self.assertEqual(deleted_user_permission_count, 2)

		blog_post_user_permission_count = vmraid.db.count(
			"User Permission", filters={"user": "test2@example.com", "allow": "Blog Post"}
		)

		self.assertEqual(blog_post_user_permission_count, 0)

		blog_category_user_permission_count = vmraid.db.count(
			"User Permission", filters={"user": "test2@example.com", "allow": "Blog Category"}
		)

		self.assertEqual(blog_category_user_permission_count, 1)

		# reset the user
		vmraid.set_user(current_user)

	def test_child_table_permissions(self):
		vmraid.set_user("test@example.com")
		self.assertIsInstance(vmraid.get_list("Has Role", parent_doctype="User", limit=1), list)
		self.assertRaisesRegex(
			vmraid.exceptions.ValidationError,
			".* is not a valid parent DocType for .*",
			vmraid.get_list,
			doctype="Has Role",
			parent_doctype="ToDo",
		)
		self.assertRaisesRegex(
			vmraid.exceptions.ValidationError,
			"Please specify a valid parent DocType for .*",
			vmraid.get_list,
			"Has Role",
		)
		self.assertRaisesRegex(
			vmraid.exceptions.ValidationError,
			".* is not a valid parent DocType for .*",
			vmraid.get_list,
			doctype="Has Role",
			parent_doctype="Has Role",
		)
