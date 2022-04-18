# -*- coding: utf-8 -*-
# Copyright (c) 2020, VMRaid Technologies and Contributors
# License: MIT. See LICENSE
import unittest

import vmraid


class TestSystemConsole(unittest.TestCase):
	def test_system_console(self):
		system_console = vmraid.get_doc("System Console")
		system_console.console = 'log("hello")'
		system_console.run()

		self.assertEqual(system_console.output, "hello")

		system_console.console = 'log(vmraid.db.get_value("DocType", "DocType", "module"))'
		system_console.run()

		self.assertEqual(system_console.output, "Core")
