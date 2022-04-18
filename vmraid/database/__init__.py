# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

# Database Module
# --------------------

from vmraid.database.database import savepoint


def setup_database(force, source_sql=None, verbose=None, no_mariadb_socket=False):
	import vmraid

	if vmraid.conf.db_type == "postgres":
		import vmraid.database.postgres.setup_db

		return vmraid.database.postgres.setup_db.setup_database(force, source_sql, verbose)
	else:
		import vmraid.database.mariadb.setup_db

		return vmraid.database.mariadb.setup_db.setup_database(
			force, source_sql, verbose, no_mariadb_socket=no_mariadb_socket
		)


def drop_user_and_database(db_name, root_login=None, root_password=None):
	import vmraid

	if vmraid.conf.db_type == "postgres":
		import vmraid.database.postgres.setup_db

		return vmraid.database.postgres.setup_db.drop_user_and_database(
			db_name, root_login, root_password
		)
	else:
		import vmraid.database.mariadb.setup_db

		return vmraid.database.mariadb.setup_db.drop_user_and_database(
			db_name, root_login, root_password
		)


def get_db(host=None, user=None, password=None, port=None):
	import vmraid

	if vmraid.conf.db_type == "postgres":
		import vmraid.database.postgres.database

		return vmraid.database.postgres.database.PostgresDatabase(host, user, password, port=port)
	else:
		import vmraid.database.mariadb.database

		return vmraid.database.mariadb.database.MariaDBDatabase(host, user, password, port=port)


def setup_help_database(help_db_name):
	import vmraid

	if vmraid.conf.db_type == "postgres":
		import vmraid.database.postgres.setup_db

		return vmraid.database.postgres.setup_db.setup_help_database(help_db_name)
	else:
		import vmraid.database.mariadb.setup_db

		return vmraid.database.mariadb.setup_db.setup_help_database(help_db_name)
