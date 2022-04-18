# Copyright (c) 2021, VMRaid and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals

import functools

import vmraid


@vmraid.whitelist()
def get_google_fonts():
	return _get_google_fonts()


@functools.lru_cache()
def _get_google_fonts():
	file_path = vmraid.get_app_path("vmraid", "data", "google_fonts.json")
	return vmraid.parse_json(vmraid.read_file(file_path))
