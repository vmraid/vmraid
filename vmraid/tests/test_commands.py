# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE

# imports - standard imports
import gzip
import importlib
import json
import os
import shlex
import shutil
import subprocess
import unittest
from contextlib import contextmanager
from functools import wraps
from glob import glob
from typing import List, Optional
from unittest.case import skipIf
from unittest.mock import patch

# imports - third party imports
import click
from click import Command
from click.testing import CliRunner, Result

# imports - module imports
import vmraid
import vmraid.commands.site
import vmraid.commands.utils
import vmraid.recorder
from vmraid.installer import add_to_installed_apps, remove_app
from vmraid.utils import add_to_date, get_chair_path, get_chair_relative_path, now
from vmraid.utils.backups import fetch_latest_backups

_result: Optional[Result] = None
TEST_SITE = "commands-site-O4PN2QKA.test"  # added random string tag to avoid collisions
CLI_CONTEXT = vmraid._dict(sites=[TEST_SITE])


def clean(value) -> str:
	"""Strips and converts bytes to str

	Args:
	        value ([type]): [description]

	Returns:
	        [type]: [description]
	"""
	if isinstance(value, bytes):
		value = value.decode()
	if isinstance(value, str):
		value = value.strip()
	return value


def missing_in_backup(doctypes: List, file: os.PathLike) -> List:
	"""Returns list of missing doctypes in the backup.

	Args:
	        doctypes (list): List of DocTypes to be checked
	        file (str): Path of the database file

	Returns:
	        doctypes(list): doctypes that are missing in backup
	"""
	predicate = 'COPY public."tab{}"' if vmraid.conf.db_type == "postgres" else "CREATE TABLE `tab{}`"
	with gzip.open(file, "rb") as f:
		content = f.read().decode("utf8").lower()

	return [doctype for doctype in doctypes if predicate.format(doctype).lower() not in content]


def exists_in_backup(doctypes: List, file: os.PathLike) -> bool:
	"""Checks if the list of doctypes exist in the database.sql.gz file supplied

	Args:
	        doctypes (list): List of DocTypes to be checked
	        file (str): Path of the database file

	Returns:
	        bool: True if all tables exist
	"""
	missing_doctypes = missing_in_backup(doctypes, file)
	return len(missing_doctypes) == 0


@contextmanager
def maintain_locals():
	pre_site = vmraid.local.site
	pre_flags = vmraid.local.flags.copy()
	pre_db = vmraid.local.db

	try:
		yield
	finally:
		post_site = getattr(vmraid.local, "site", None)
		if not post_site or post_site != pre_site:
			vmraid.init(site=pre_site)
			vmraid.local.db = pre_db
			vmraid.local.flags.update(pre_flags)


def pass_test_context(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		return f(CLI_CONTEXT, *args, **kwargs)

	return decorated_function


@contextmanager
def cli(cmd: Command, args: Optional[List] = None):
	with maintain_locals():
		global _result

		patch_ctx = patch("vmraid.commands.pass_context", pass_test_context)
		_module = cmd.callback.__module__
		_cmd = cmd.callback.__qualname__

		__module = importlib.import_module(_module)
		patch_ctx.start()
		importlib.reload(__module)
		click_cmd = getattr(__module, _cmd)

		try:
			_result = CliRunner().invoke(click_cmd, args=args)
			_result.command = str(cmd)
			yield _result
		finally:
			patch_ctx.stop()
			__module = importlib.import_module(_module)
			importlib.reload(__module)
			importlib.invalidate_caches()


class BaseTestCommands(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.setup_test_site()
		return super().setUpClass()

	@classmethod
	def execute(self, command, kwargs=None):
		site = {"site": vmraid.local.site}
		cmd_input = None
		if kwargs:
			cmd_input = kwargs.get("cmd_input", None)
			if cmd_input:
				if not isinstance(cmd_input, bytes):
					raise Exception(f"The input should be of type bytes, not {type(cmd_input).__name__}")

				del kwargs["cmd_input"]
			kwargs.update(site)
		else:
			kwargs = site

		self.command = " ".join(command.split()).format(**kwargs)
		click.secho(self.command, fg="bright_black")

		command = shlex.split(self.command)
		self._proc = subprocess.run(
			command, input=cmd_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE
		)
		self.stdout = clean(self._proc.stdout)
		self.stderr = clean(self._proc.stderr)
		self.returncode = clean(self._proc.returncode)

	@classmethod
	def setup_test_site(cls):
		cmd_config = {
			"test_site": TEST_SITE,
			"admin_password": vmraid.conf.admin_password,
			"root_login": vmraid.conf.root_login,
			"root_password": vmraid.conf.root_password,
			"db_type": vmraid.conf.db_type,
		}

		if not os.path.exists(os.path.join(TEST_SITE, "site_config.json")):
			cls.execute(
				"chair new-site {test_site} --admin-password {admin_password} --db-type" " {db_type}",
				cmd_config,
			)

	def _formatMessage(self, msg, standardMsg):
		output = super(BaseTestCommands, self)._formatMessage(msg, standardMsg)

		if not hasattr(self, "command") and _result:
			command = _result.command
			stdout = _result.stdout_bytes.decode() if _result.stdout_bytes else None
			stderr = _result.stderr_bytes.decode() if _result.stderr_bytes else None
			returncode = _result.exit_code
		else:
			command = self.command
			stdout = self.stdout
			stderr = self.stderr
			returncode = self.returncode

		cmd_execution_summary = "\n".join(
			[
				"-" * 70,
				"Last Command Execution Summary:",
				"Command: {}".format(command) if command else "",
				"Standard Output: {}".format(stdout) if stdout else "",
				"Standard Error: {}".format(stderr) if stderr else "",
				"Return Code: {}".format(returncode) if returncode else "",
			]
		).strip()

		return "{}\n\n{}".format(output, cmd_execution_summary)


class TestCommands(BaseTestCommands):
	def test_execute(self):
		# test 1: execute a command expecting a numeric output
		self.execute("chair --site {site} execute vmraid.db.get_database_size")
		self.assertEqual(self.returncode, 0)
		self.assertIsInstance(float(self.stdout), float)

		# test 2: execute a command expecting an errored output as local won't exist
		self.execute("chair --site {site} execute vmraid.local.site")
		self.assertEqual(self.returncode, 1)
		self.assertIsNotNone(self.stderr)

		# test 3: execute a command with kwargs
		# Note:
		# terminal command has been escaped to avoid .format string replacement
		# The returned value has quotes which have been trimmed for the test
		self.execute("""chair --site {site} execute vmraid.bold --kwargs '{{"text": "DocType"}}'""")
		self.assertEqual(self.returncode, 0)
		self.assertEqual(self.stdout[1:-1], vmraid.bold(text="DocType"))

	@unittest.skip
	def test_restore(self):
		# step 0: create a site to run the test on
		global_config = {
			"admin_password": vmraid.conf.admin_password,
			"root_login": vmraid.conf.root_login,
			"root_password": vmraid.conf.root_password,
			"db_type": vmraid.conf.db_type,
		}
		site_data = {"test_site": TEST_SITE, **global_config}
		for key, value in global_config.items():
			if value:
				self.execute(f"chair set-config {key} {value} -g")

		# test 1: chair restore from full backup
		self.execute("chair --site {test_site} backup --ignore-backup-conf", site_data)
		self.execute(
			"chair --site {test_site} execute vmraid.utils.backups.fetch_latest_backups",
			site_data,
		)
		site_data.update({"database": json.loads(self.stdout)["database"]})
		self.execute("chair --site {test_site} restore {database}", site_data)

		# test 2: restore from partial backup
		self.execute("chair --site {test_site} backup --exclude 'ToDo'", site_data)
		site_data.update({"kw": "\"{'partial':True}\""})
		self.execute(
			"chair --site {test_site} execute" " vmraid.utils.backups.fetch_latest_backups --kwargs {kw}",
			site_data,
		)
		site_data.update({"database": json.loads(self.stdout)["database"]})
		self.execute("chair --site {test_site} restore {database}", site_data)
		self.assertEqual(self.returncode, 1)

	def test_partial_restore(self):
		_now = now()
		for num in range(10):
			vmraid.get_doc(
				{
					"doctype": "ToDo",
					"date": add_to_date(_now, days=num),
					"description": vmraid.mock("paragraph"),
				}
			).insert()
		vmraid.db.commit()
		todo_count = vmraid.db.count("ToDo")

		# check if todos exist, create a partial backup and see if the state is the same after restore
		self.assertIsNot(todo_count, 0)
		self.execute("chair --site {site} backup --only 'ToDo'")
		db_path = fetch_latest_backups(partial=True)["database"]
		self.assertTrue("partial" in db_path)

		vmraid.db.sql_ddl("DROP TABLE IF EXISTS `tabToDo`")
		vmraid.db.commit()

		self.execute("chair --site {site} partial-restore {path}", {"path": db_path})
		self.assertEqual(self.returncode, 0)
		self.assertEqual(vmraid.db.count("ToDo"), todo_count)

	def test_recorder(self):
		vmraid.recorder.stop()

		self.execute("chair --site {site} start-recording")
		vmraid.local.cache = {}
		self.assertEqual(vmraid.recorder.status(), True)

		self.execute("chair --site {site} stop-recording")
		vmraid.local.cache = {}
		self.assertEqual(vmraid.recorder.status(), False)

	def test_remove_from_installed_apps(self):
		app = "test_remove_app"
		add_to_installed_apps(app)

		# check: confirm that add_to_installed_apps added the app in the default
		self.execute("chair --site {site} list-apps")
		self.assertIn(app, self.stdout)

		# test 1: remove app from installed_apps global default
		self.execute("chair --site {site} remove-from-installed-apps {app}", {"app": app})
		self.assertEqual(self.returncode, 0)
		self.execute("chair --site {site} list-apps")
		self.assertNotIn(app, self.stdout)

	def test_list_apps(self):
		# test 1: sanity check for command
		self.execute("chair --site all list-apps")
		self.assertIsNotNone(self.returncode)
		self.assertIsInstance(self.stdout or self.stderr, str)

		# test 2: bare functionality for single site
		self.execute("chair --site {site} list-apps")
		self.assertEqual(self.returncode, 0)
		list_apps = set(_x.split()[0] for _x in self.stdout.split("\n"))
		doctype = vmraid.get_single("Installed Applications").installed_applications
		if doctype:
			installed_apps = set(x.app_name for x in doctype)
		else:
			installed_apps = set(vmraid.get_installed_apps())
		self.assertSetEqual(list_apps, installed_apps)

		# test 3: parse json format
		self.execute("chair --site {site} list-apps --format json")
		self.assertEqual(self.returncode, 0)
		self.assertIsInstance(json.loads(self.stdout), dict)

		self.execute("chair --site {site} list-apps -f json")
		self.assertEqual(self.returncode, 0)
		self.assertIsInstance(json.loads(self.stdout), dict)

	def test_show_config(self):
		# test 1: sanity check for command
		self.execute("chair --site all show-config")
		self.assertEqual(self.returncode, 0)

		# test 2: test keys in table text
		self.execute(
			"chair --site {site} set-config test_key '{second_order}' --parse",
			{"second_order": json.dumps({"test_key": "test_value"})},
		)
		self.execute("chair --site {site} show-config")
		self.assertEqual(self.returncode, 0)
		self.assertIn("test_key.test_key", self.stdout.split())
		self.assertIn("test_value", self.stdout.split())

		# test 3: parse json format
		self.execute("chair --site all show-config --format json")
		self.assertEqual(self.returncode, 0)
		self.assertIsInstance(json.loads(self.stdout), dict)

		self.execute("chair --site {site} show-config --format json")
		self.assertIsInstance(json.loads(self.stdout), dict)

		self.execute("chair --site {site} show-config -f json")
		self.assertIsInstance(json.loads(self.stdout), dict)

	def test_get_chair_relative_path(self):
		chair_path = get_chair_path()
		test1_path = os.path.join(chair_path, "test1.txt")
		test2_path = os.path.join(chair_path, "sites", "test2.txt")

		with open(test1_path, "w+") as test1:
			test1.write("asdf")
		with open(test2_path, "w+") as test2:
			test2.write("asdf")

		self.assertTrue("test1.txt" in get_chair_relative_path("test1.txt"))
		self.assertTrue("sites/test2.txt" in get_chair_relative_path("test2.txt"))
		with self.assertRaises(SystemExit):
			get_chair_relative_path("test3.txt")

		os.remove(test1_path)
		os.remove(test2_path)

	def test_vmraid_site_env(self):
		os.putenv("VMRAID_SITE", vmraid.local.site)
		self.execute("chair execute vmraid.ping")
		self.assertEqual(self.returncode, 0)
		self.assertIn("pong", self.stdout)

	def test_version(self):
		self.execute("chair version")
		self.assertEqual(self.returncode, 0)

		for output in ["legacy", "plain", "table", "json"]:
			self.execute(f"chair version -f {output}")
			self.assertEqual(self.returncode, 0)

		self.execute("chair version -f invalid")
		self.assertEqual(self.returncode, 2)

	def test_set_password(self):
		from vmraid.utils.password import check_password

		self.execute("chair --site {site} set-password Administrator test1")
		self.assertEqual(self.returncode, 0)
		self.assertEqual(check_password("Administrator", "test1"), "Administrator")
		# to release the lock taken by check_password
		vmraid.db.commit()

		self.execute("chair --site {site} set-admin-password test2")
		self.assertEqual(self.returncode, 0)
		self.assertEqual(check_password("Administrator", "test2"), "Administrator")

	def test_make_app(self):
		user_input = [
			b"Test App",  # title
			b"This app's description contains 'single quotes' and \"double quotes\".",  # description
			b"Test Publisher",  # publisher
			b"example@example.org",  # email
			b"",  # icon
			b"",  # color
			b"MIT",  # app_license
		]
		app_name = "testapp0"
		apps_path = os.path.join(get_chair_path(), "apps")
		test_app_path = os.path.join(apps_path, app_name)
		self.execute(f"chair make-app {apps_path} {app_name}", {"cmd_input": b"\n".join(user_input)})
		self.assertEqual(self.returncode, 0)
		self.assertTrue(os.path.exists(test_app_path))

		# cleanup
		shutil.rmtree(test_app_path)

	@skipIf(
		not (
			vmraid.conf.root_password and vmraid.conf.admin_password and vmraid.conf.db_type == "mariadb"
		),
		"DB Root password and Admin password not set in config",
	)
	def test_chair_drop_site_should_archive_site(self):
		# TODO: Make this test postgres compatible
		site = TEST_SITE

		self.execute(
			f"chair new-site {site} --force --verbose "
			f"--admin-password {vmraid.conf.admin_password} "
			f"--mariadb-root-password {vmraid.conf.root_password} "
			f"--db-type {vmraid.conf.db_type or 'mariadb'} "
		)
		self.assertEqual(self.returncode, 0)

		self.execute(f"chair drop-site {site} --force --root-password {vmraid.conf.root_password}")
		self.assertEqual(self.returncode, 0)

		chair_path = get_chair_path()
		site_directory = os.path.join(chair_path, f"sites/{site}")
		self.assertFalse(os.path.exists(site_directory))
		archive_directory = os.path.join(chair_path, f"archived/sites/{site}")
		self.assertTrue(os.path.exists(archive_directory))


class TestBackups(BaseTestCommands):
	backup_map = {
		"includes": {
			"includes": [
				"ToDo",
				"Note",
			]
		},
		"excludes": {"excludes": ["Activity Log", "Access Log", "Error Log"]},
	}
	home = os.path.expanduser("~")
	site_backup_path = vmraid.utils.get_site_path("private", "backups")

	def setUp(self):
		self.files_to_trash = []

	def tearDown(self):
		if self._testMethodName == "test_backup":
			for file in self.files_to_trash:
				os.remove(file)
				try:
					os.rmdir(os.path.dirname(file))
				except OSError:
					pass

	def test_backup_no_options(self):
		"""Take a backup without any options"""
		before_backup = fetch_latest_backups(partial=True)
		self.execute("chair --site {site} backup")
		after_backup = fetch_latest_backups(partial=True)

		self.assertEqual(self.returncode, 0)
		self.assertIn("successfully completed", self.stdout)
		self.assertNotEqual(before_backup["database"], after_backup["database"])

	def test_backup_with_files(self):
		"""Take a backup with files (--with-files)"""
		before_backup = fetch_latest_backups()
		self.execute("chair --site {site} backup --with-files")
		after_backup = fetch_latest_backups()

		self.assertEqual(self.returncode, 0)
		self.assertIn("successfully completed", self.stdout)
		self.assertIn("with files", self.stdout)
		self.assertNotEqual(before_backup, after_backup)
		self.assertIsNotNone(after_backup["public"])
		self.assertIsNotNone(after_backup["private"])

	def test_backup_with_custom_path(self):
		"""Backup to a custom path (--backup-path)"""
		backup_path = os.path.join(self.home, "backups")
		self.execute(
			"chair --site {site} backup --backup-path {backup_path}", {"backup_path": backup_path}
		)

		self.assertEqual(self.returncode, 0)
		self.assertTrue(os.path.exists(backup_path))
		self.assertGreaterEqual(len(os.listdir(backup_path)), 2)

	def test_backup_with_different_file_paths(self):
		"""Backup with different file paths (--backup-path-db, --backup-path-files, --backup-path-private-files, --backup-path-conf)"""
		kwargs = {
			key: os.path.join(self.home, key, value)
			for key, value in {
				"db_path": "database.sql.gz",
				"files_path": "public.tar",
				"private_path": "private.tar",
				"conf_path": "config.json",
			}.items()
		}

		self.execute(
			"""chair
			--site {site} backup --with-files
			--backup-path-db {db_path}
			--backup-path-files {files_path}
			--backup-path-private-files {private_path}
			--backup-path-conf {conf_path}""",
			kwargs,
		)

		self.assertEqual(self.returncode, 0)
		for path in kwargs.values():
			self.assertTrue(os.path.exists(path))

	def test_backup_compress_files(self):
		"""Take a compressed backup (--compress)"""
		self.execute("chair --site {site} backup --with-files --compress")
		self.assertEqual(self.returncode, 0)
		compressed_files = glob(f"{self.site_backup_path}/*.tgz")
		self.assertGreater(len(compressed_files), 0)

	def test_backup_verbose(self):
		"""Take a verbose backup (--verbose)"""
		self.execute("chair --site {site} backup --verbose")
		self.assertEqual(self.returncode, 0)

	def test_backup_only_specific_doctypes(self):
		"""Take a backup with (include) backup options set in the site config `vmraid.conf.backup.includes`"""
		self.execute(
			"chair --site {site} set-config backup '{includes}' --parse",
			{"includes": json.dumps(self.backup_map["includes"])},
		)
		self.execute("chair --site {site} backup --verbose")
		self.assertEqual(self.returncode, 0)
		database = fetch_latest_backups(partial=True)["database"]
		self.assertEqual([], missing_in_backup(self.backup_map["includes"]["includes"], database))

	def test_backup_excluding_specific_doctypes(self):
		"""Take a backup with (exclude) backup options set (`vmraid.conf.backup.excludes`, `--exclude`)"""
		# test 1: take a backup with vmraid.conf.backup.excludes
		self.execute(
			"chair --site {site} set-config backup '{excludes}' --parse",
			{"excludes": json.dumps(self.backup_map["excludes"])},
		)
		self.execute("chair --site {site} backup --verbose")
		self.assertEqual(self.returncode, 0)
		database = fetch_latest_backups(partial=True)["database"]
		self.assertFalse(exists_in_backup(self.backup_map["excludes"]["excludes"], database))
		self.assertEqual([], missing_in_backup(self.backup_map["includes"]["includes"], database))

		# test 2: take a backup with --exclude
		self.execute(
			"chair --site {site} backup --exclude '{exclude}'",
			{"exclude": ",".join(self.backup_map["excludes"]["excludes"])},
		)
		self.assertEqual(self.returncode, 0)
		database = fetch_latest_backups(partial=True)["database"]
		self.assertFalse(exists_in_backup(self.backup_map["excludes"]["excludes"], database))

	def test_selective_backup_priority_resolution(self):
		"""Take a backup with conflicting backup options set (`vmraid.conf.excludes`, `--include`)"""
		self.execute(
			"chair --site {site} backup --include '{include}'",
			{"include": ",".join(self.backup_map["includes"]["includes"])},
		)
		self.assertEqual(self.returncode, 0)
		database = fetch_latest_backups(partial=True)["database"]
		self.assertEqual([], missing_in_backup(self.backup_map["includes"]["includes"], database))

	def test_dont_backup_conf(self):
		"""Take a backup ignoring vmraid.conf.backup settings (with --ignore-backup-conf option)"""
		self.execute("chair --site {site} backup --ignore-backup-conf")
		self.assertEqual(self.returncode, 0)
		database = fetch_latest_backups()["database"]
		self.assertEqual([], missing_in_backup(self.backup_map["excludes"]["excludes"], database))


class TestRemoveApp(unittest.TestCase):
	def test_delete_modules(self):
		from vmraid.installer import (
			_delete_doctypes,
			_delete_modules,
			_get_module_linked_doctype_field_map,
		)

		test_module = vmraid.new_doc("Module Def")

		test_module.update({"module_name": "RemoveThis", "app_name": "vmraid"})
		test_module.save()

		module_def_linked_doctype = vmraid.get_doc(
			{
				"doctype": "DocType",
				"name": "Doctype linked with module def",
				"module": "RemoveThis",
				"custom": 1,
				"fields": [
					{"label": "Modulen't", "fieldname": "notmodule", "fieldtype": "Link", "options": "Module Def"}
				],
			}
		).insert()

		doctype_to_link_field_map = _get_module_linked_doctype_field_map()

		self.assertIn("Report", doctype_to_link_field_map)
		self.assertIn(module_def_linked_doctype.name, doctype_to_link_field_map)
		self.assertEqual(doctype_to_link_field_map[module_def_linked_doctype.name], "notmodule")
		self.assertNotIn("DocType", doctype_to_link_field_map)

		doctypes_to_delete = _delete_modules([test_module.module_name], dry_run=False)
		self.assertEqual(len(doctypes_to_delete), 1)

		_delete_doctypes(doctypes_to_delete, dry_run=False)
		self.assertFalse(vmraid.db.exists("Module Def", test_module.module_name))
		self.assertFalse(vmraid.db.exists("DocType", module_def_linked_doctype.name))

	def test_dry_run(self):
		"""Check if dry run in not destructive."""

		# nothing to assert, if this fails rest of the test suite will crumble.
		remove_app("vmraid", dry_run=True, yes=True, no_backup=True)


class TestSiteMigration(BaseTestCommands):
	def test_migrate_cli(self):
		with cli(vmraid.commands.site.migrate) as result:
			self.assertTrue(TEST_SITE in result.stdout)
			self.assertEqual(result.exit_code, 0)
			self.assertEqual(result.exception, None)


class TestChairBuild(BaseTestCommands):
	def test_build_assets(self):
		with cli(vmraid.commands.utils.build) as result:
			self.assertEqual(result.exit_code, 0)
			self.assertEqual(result.exception, None)
