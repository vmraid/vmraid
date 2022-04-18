# Copyright (c) 2021, VMRaid and Contributors
# License: MIT. See LICENSE
import os
import unittest
from random import choices
from unittest.mock import patch

import vmraid
import vmraid.translate
from vmraid import _
from vmraid.translate import get_language, get_parent_language
from vmraid.utils import set_request

dirname = os.path.dirname(__file__)
translation_string_file = os.path.join(dirname, "translation_test_file.txt")
first_lang, second_lang, third_lang, fourth_lang, fifth_lang = choices(
	# skip "en*" since it is a default language
	vmraid.get_all("Language", pluck="name", filters=[["name", "not like", "en%"]]),
	k=5,
)


class TestTranslate(unittest.TestCase):
	guest_sessions_required = [
		"test_guest_request_language_resolution_with_cookie",
		"test_guest_request_language_resolution_with_request_header",
	]

	def setUp(self):
		if self._testMethodName in self.guest_sessions_required:
			vmraid.set_user("Guest")

	def tearDown(self):
		vmraid.form_dict.pop("_lang", None)
		if self._testMethodName in self.guest_sessions_required:
			vmraid.set_user("Administrator")

	def test_extract_message_from_file(self):
		data = vmraid.translate.get_messages_from_file(translation_string_file)
		exp_filename = "apps/vmraid/vmraid/tests/translation_test_file.txt"

		self.assertEqual(
			len(data),
			len(expected_output),
			msg=f"Mismatched output:\nExpected: {expected_output}\nFound: {data}",
		)

		for extracted, expected in zip(data, expected_output):
			ext_filename, ext_message, ext_context, ext_line = extracted
			exp_message, exp_context, exp_line = expected
			self.assertEqual(ext_filename, exp_filename)
			self.assertEqual(ext_message, exp_message)
			self.assertEqual(ext_context, exp_context)
			self.assertEqual(ext_line, exp_line)

	def test_translation_with_context(self):
		try:
			vmraid.local.lang = "fr"
			self.assertEqual(_("Change"), "Changement")
			self.assertEqual(_("Change", context="Coins"), "la monnaie")
		finally:
			vmraid.local.lang = "en"

	def test_request_language_resolution_with_form_dict(self):
		"""Test for vmraid.translate.get_language

		Case 1: vmraid.form_dict._lang is set
		"""

		vmraid.form_dict._lang = first_lang

		with patch.object(vmraid.translate, "get_preferred_language_cookie", return_value=second_lang):
			return_val = get_language()

		self.assertIn(return_val, [first_lang, get_parent_language(first_lang)])

	def test_request_language_resolution_with_cookie(self):
		"""Test for vmraid.translate.get_language

		Case 2: vmraid.form_dict._lang is not set, but preferred_language cookie is
		"""

		with patch.object(vmraid.translate, "get_preferred_language_cookie", return_value="fr"):
			set_request(method="POST", path="/", headers=[("Accept-Language", "hr")])
			return_val = get_language()
			# system default language
			self.assertEqual(return_val, "en")
			self.assertNotIn(return_val, [second_lang, get_parent_language(second_lang)])

	def test_guest_request_language_resolution_with_cookie(self):
		"""Test for vmraid.translate.get_language

		Case 3: vmraid.form_dict._lang is not set, but preferred_language cookie is [Guest User]
		"""

		with patch.object(vmraid.translate, "get_preferred_language_cookie", return_value=second_lang):
			set_request(method="POST", path="/", headers=[("Accept-Language", third_lang)])
			return_val = get_language()

		self.assertIn(return_val, [second_lang, get_parent_language(second_lang)])

	def test_guest_request_language_resolution_with_request_header(self):
		"""Test for vmraid.translate.get_language

		Case 4: vmraid.form_dict._lang & preferred_language cookie is not set, but Accept-Language header is [Guest User]
		"""

		set_request(method="POST", path="/", headers=[("Accept-Language", third_lang)])
		return_val = get_language()
		self.assertIn(return_val, [third_lang, get_parent_language(third_lang)])

	def test_request_language_resolution_with_request_header(self):
		"""Test for vmraid.translate.get_language

		Case 5: vmraid.form_dict._lang & preferred_language cookie is not set, but Accept-Language header is
		"""

		set_request(method="POST", path="/", headers=[("Accept-Language", third_lang)])
		return_val = get_language()
		self.assertNotIn(return_val, [third_lang, get_parent_language(third_lang)])


expected_output = [
	("Warning: Unable to find {0} in any table related to {1}", "This is some context", 2),
	("Warning: Unable to find {0} in any table related to {1}", None, 4),
	("You don't have any messages yet.", None, 6),
	("Submit", "Some DocType", 8),
	("Warning: Unable to find {0} in any table related to {1}", "This is some context", 15),
	("Submit", "Some DocType", 17),
	("You don't have any messages yet.", None, 19),
	("You don't have any messages yet.", None, 21),
	("Long string that needs its own line because of black formatting.", None, 24),
	("Long string with", "context", 28),
	("Long string with", "context on newline", 32),
]
