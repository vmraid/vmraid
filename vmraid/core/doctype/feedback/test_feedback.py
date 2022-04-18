# Copyright (c) 2021, VMRaid Technologies and Contributors
# License: MIT. See LICENSE

import unittest

import vmraid


class TestFeedback(unittest.TestCase):
	def tearDown(self):
		vmraid.form_dict.reference_doctype = None
		vmraid.form_dict.reference_name = None
		vmraid.form_dict.like = None
		vmraid.local.request_ip = None

	def test_feedback_creation_updation(self):
		from vmraid.website.doctype.blog_post.test_blog_post import make_test_blog

		test_blog = make_test_blog()

		vmraid.db.delete("Feedback", {"reference_doctype": "Blog Post"})

		from vmraid.templates.includes.feedback.feedback import give_feedback

		vmraid.form_dict.reference_doctype = "Blog Post"
		vmraid.form_dict.reference_name = test_blog.name
		vmraid.form_dict.like = True
		vmraid.local.request_ip = "127.0.0.1"

		feedback = give_feedback()

		self.assertEqual(feedback.like, True)

		vmraid.form_dict.like = False

		updated_feedback = give_feedback()

		self.assertEqual(updated_feedback.like, False)

		vmraid.db.delete("Feedback", {"reference_doctype": "Blog Post"})

		test_blog.delete()
