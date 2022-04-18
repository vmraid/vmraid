import unittest
from unittest.mock import mock_open, patch

import vmraid
from vmraid.modules import patch_handler

EMTPY_FILE = ""
EMTPY_SECTION = """
[pre_model_sync]

[post_model_sync]
"""
FILLED_SECTIONS = """
[pre_model_sync]
app.module.patch1
app.module.patch2

[post_model_sync]
app.module.patch3

"""
OLD_STYLE_PATCH_TXT = """
app.module.patch1
app.module.patch2
app.module.patch3
"""

EDGE_CASES = """
[pre_model_sync]
App.module.patch1
app.module.patch2 # rerun
execute:vmraid.db.updatedb("Item")
execute:vmraid.function(arg="1")

[post_model_sync]
app.module.patch3
"""

COMMENTED_OUT = """
[pre_model_sync]
app.module.patch1
# app.module.patch2 # rerun
app.module.patch3

[post_model_sync]
app.module.patch4
"""


class TestPatches(unittest.TestCase):
	def test_patch_module_names(self):
		vmraid.flags.final_patches = []
		vmraid.flags.in_install = True
		for patchmodule in patch_handler.get_all_patches():
			if patchmodule.startswith("execute:"):
				pass
			else:
				if patchmodule.startswith("finally:"):
					patchmodule = patchmodule.split("finally:")[-1]
				self.assertTrue(vmraid.get_attr(patchmodule.split()[0] + ".execute"))

		vmraid.flags.in_install = False

	def test_get_patch_list(self):
		pre = patch_handler.get_patches_from_app("vmraid", patch_handler.PatchType.pre_model_sync)
		post = patch_handler.get_patches_from_app("vmraid", patch_handler.PatchType.post_model_sync)
		all_patches = patch_handler.get_patches_from_app("vmraid")
		self.assertGreater(len(pre), 0)
		self.assertGreater(len(post), 0)

		self.assertEqual(len(all_patches), len(pre) + len(post))

	def test_all_patches_are_marked_completed(self):
		all_patches = patch_handler.get_patches_from_app("vmraid")
		finished_patches = vmraid.db.count("Patch Log")

		self.assertGreaterEqual(finished_patches, len(all_patches))


class TestPatchReader(unittest.TestCase):
	def get_patches(self):
		return (
			patch_handler.get_patches_from_app("vmraid"),
			patch_handler.get_patches_from_app("vmraid", patch_handler.PatchType.pre_model_sync),
			patch_handler.get_patches_from_app("vmraid", patch_handler.PatchType.post_model_sync),
		)

	@patch("builtins.open", new_callable=mock_open, read_data=EMTPY_FILE)
	def test_empty_file(self, _file):
		all, pre, post = self.get_patches()
		self.assertEqual(all, [])
		self.assertEqual(pre, [])
		self.assertEqual(post, [])

	@patch("builtins.open", new_callable=mock_open, read_data=EMTPY_SECTION)
	def test_empty_sections(self, _file):
		all, pre, post = self.get_patches()
		self.assertEqual(all, [])
		self.assertEqual(pre, [])
		self.assertEqual(post, [])

	@patch("builtins.open", new_callable=mock_open, read_data=FILLED_SECTIONS)
	def test_new_style(self, _file):
		all, pre, post = self.get_patches()
		self.assertEqual(all, ["app.module.patch1", "app.module.patch2", "app.module.patch3"])
		self.assertEqual(pre, ["app.module.patch1", "app.module.patch2"])
		self.assertEqual(
			post,
			[
				"app.module.patch3",
			],
		)

	@patch("builtins.open", new_callable=mock_open, read_data=OLD_STYLE_PATCH_TXT)
	def test_old_style(self, _file):
		all, pre, post = self.get_patches()
		self.assertEqual(all, ["app.module.patch1", "app.module.patch2", "app.module.patch3"])
		self.assertEqual(pre, ["app.module.patch1", "app.module.patch2", "app.module.patch3"])
		self.assertEqual(post, [])

	@patch("builtins.open", new_callable=mock_open, read_data=EDGE_CASES)
	def test_new_style_edge_cases(self, _file):
		all, pre, post = self.get_patches()
		self.assertEqual(
			pre,
			[
				"App.module.patch1",
				"app.module.patch2 # rerun",
				'execute:vmraid.db.updatedb("Item")',
				'execute:vmraid.function(arg="1")',
			],
		)

	@patch("builtins.open", new_callable=mock_open, read_data=COMMENTED_OUT)
	def test_ignore_comments(self, _file):
		all, pre, post = self.get_patches()
		self.assertEqual(pre, ["app.module.patch1", "app.module.patch3"])
