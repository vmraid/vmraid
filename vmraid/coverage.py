# Copyright (c) 2021, VMRaid and Contributors
# MIT License. See LICENSE
"""
	vmraid.coverage
	~~~~~~~~~~~~~~~~

	Coverage settings for vmraid
"""

STANDARD_INCLUSIONS = ["*.py"]

STANDARD_EXCLUSIONS = [
	"*.js",
	"*.xml",
	"*.pyc",
	"*.css",
	"*.less",
	"*.scss",
	"*.vue",
	"*.html",
	"*/test_*",
	"*/node_modules/*",
	"*/doctype/*/*_dashboard.py",
	"*/patches/*",
]

VMRAID_EXCLUSIONS = [
	"*/tests/*",
	"*/commands/*",
	"*/vmraid/change_log/*",
	"*/vmraid/exceptions*",
	"*/vmraid/coverage.py",
	"*vmraid/setup.py",
	"*/doctype/*/*_dashboard.py",
	"*/patches/*",
]


class CodeCoverage:
	def __init__(self, with_coverage, app):
		self.with_coverage = with_coverage
		self.app = app or "vmraid"

	def __enter__(self):
		if self.with_coverage:
			import os

			from coverage import Coverage

			from vmraid.utils import get_chair_path

			# Generate coverage report only for app that is being tested
			source_path = os.path.join(get_chair_path(), "apps", self.app)
			omit = STANDARD_EXCLUSIONS[:]

			if self.app == "vmraid":
				omit.extend(VMRAID_EXCLUSIONS)

			self.coverage = Coverage(source=[source_path], omit=omit, include=STANDARD_INCLUSIONS)
			self.coverage.start()

	def __exit__(self, exc_type, exc_value, traceback):
		if self.with_coverage:
			self.coverage.stop()
			self.coverage.save()
			self.coverage.xml_report()
