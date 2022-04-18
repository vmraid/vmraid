# -*- coding: utf-8 -*-
# Copyright (c) 2019, VMRaid Technologies and Contributors
# License: MIT. See LICENSE
import unittest

import vmraid
from vmraid.utils import set_request
from vmraid.website.serve import get_response

test_dependencies = ["Blog Post"]


class TestWebsiteRouteMeta(unittest.TestCase):
	def test_meta_tag_generation(self):
		blogs = vmraid.get_all(
			"Blog Post", fields=["name", "route"], filters={"published": 1, "route": ("!=", "")}, limit=1
		)

		blog = blogs[0]

		# create meta tags for this route
		doc = vmraid.new_doc("Website Route Meta")
		doc.append("meta_tags", {"key": "type", "value": "blog_post"})
		doc.append("meta_tags", {"key": "og:title", "value": "My Blog"})
		doc.name = blog.route
		doc.insert()

		# set request on this route
		set_request(path=blog.route)
		response = get_response()

		self.assertTrue(response.status_code, 200)

		html = response.get_data().decode()

		self.assertTrue("""<meta name="type" content="blog_post">""" in html)
		self.assertTrue("""<meta property="og:title" content="My Blog">""" in html)

	def tearDown(self):
		vmraid.db.rollback()
