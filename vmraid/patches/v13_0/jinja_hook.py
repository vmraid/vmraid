# Copyright (c) 2021, VMRaid and Contributors
# License: MIT. See LICENSE

from click import secho

import vmraid


def execute():
	if vmraid.get_hooks("jenv"):
		print()
		secho(
			'WARNING: The hook "jenv" is deprecated. Follow the migration guide to use the new "jinja" hook.',
			fg="yellow",
		)
		secho("https://github.com/vmraid/vmraid/wiki/Migrating-to-Version-13", fg="yellow")
		print()
