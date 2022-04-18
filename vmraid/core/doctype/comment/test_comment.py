# -*- coding: utf-8 -*-
# Copyright (c) 2019, VMRaid Technologies and Contributors
# License: MIT. See LICENSE
import json
import unittest

import vmraid


class TestComment(unittest.TestCase):
	def tearDown(self):
		vmraid.form_dict.comment = None
		vmraid.form_dict.comment_email = None
		vmraid.form_dict.comment_by = None
		vmraid.form_dict.reference_doctype = None
		vmraid.form_dict.reference_name = None
		vmraid.form_dict.route = None
		vmraid.local.request_ip = None

	def test_comment_creation(self):
		test_doc = vmraid.get_doc(dict(doctype="ToDo", description="test"))
		test_doc.insert()
		comment = test_doc.add_comment("Comment", "test comment")

		test_doc.reload()

		# check if updated in _comments cache
		comments = json.loads(test_doc.get("_comments"))
		self.assertEqual(comments[0].get("name"), comment.name)
		self.assertEqual(comments[0].get("comment"), comment.content)

		# check document creation
		comment_1 = vmraid.get_all(
			"Comment",
			fields=["*"],
			filters=dict(reference_doctype=test_doc.doctype, reference_name=test_doc.name),
		)[0]

		self.assertEqual(comment_1.content, "test comment")

	# test via blog
	def test_public_comment(self):
		from vmraid.website.doctype.blog_post.test_blog_post import make_test_blog

		test_blog = make_test_blog()

		vmraid.db.delete("Comment", {"reference_doctype": "Blog Post"})

		from vmraid.templates.includes.comments.comments import add_comment

		vmraid.form_dict.comment = "Good comment with 10 chars"
		vmraid.form_dict.comment_email = "test@test.com"
		vmraid.form_dict.comment_by = "Good Tester"
		vmraid.form_dict.reference_doctype = "Blog Post"
		vmraid.form_dict.reference_name = test_blog.name
		vmraid.form_dict.route = test_blog.route
		vmraid.local.request_ip = "127.0.0.1"

		add_comment()

		self.assertEqual(
			vmraid.get_all(
				"Comment",
				fields=["*"],
				filters=dict(reference_doctype=test_blog.doctype, reference_name=test_blog.name),
			)[0].published,
			1,
		)

		vmraid.db.delete("Comment", {"reference_doctype": "Blog Post"})

		vmraid.form_dict.comment = "pleez vizits my site http://mysite.com"
		vmraid.form_dict.comment_by = "bad commentor"

		add_comment()

		self.assertEqual(
			len(
				vmraid.get_all(
					"Comment",
					fields=["*"],
					filters=dict(reference_doctype=test_blog.doctype, reference_name=test_blog.name),
				)
			),
			0,
		)

		# test for filtering html and css injection elements
		vmraid.db.delete("Comment", {"reference_doctype": "Blog Post"})

		vmraid.form_dict.comment = "<script>alert(1)</script>Comment"
		vmraid.form_dict.comment_by = "hacker"

		add_comment()

		self.assertEqual(
			vmraid.get_all(
				"Comment",
				fields=["content"],
				filters=dict(reference_doctype=test_blog.doctype, reference_name=test_blog.name),
			)[0]["content"],
			"Comment",
		)

		test_blog.delete()
