# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import json
import os
import sys
from collections import OrderedDict
from typing import Dict, List, Tuple

import vmraid
from vmraid.defaults import _clear_cache
from vmraid.utils import is_git_url


def _new_site(
	db_name,
	site,
	db_root_username=None,
	db_root_password=None,
	admin_password=None,
	verbose=False,
	install_apps=None,
	source_sql=None,
	force=False,
	no_mariadb_socket=False,
	reinstall=False,
	db_password=None,
	db_type=None,
	db_host=None,
	db_port=None,
	new_site=False,
):
	"""Install a new VMRaid site"""

	from vmraid.commands.scheduler import _is_scheduler_enabled
	from vmraid.utils import get_site_path, scheduler, touch_file

	if not force and os.path.exists(site):
		print("Site {0} already exists".format(site))
		sys.exit(1)

	if no_mariadb_socket and not db_type == "mariadb":
		print("--no-mariadb-socket requires db_type to be set to mariadb.")
		sys.exit(1)

	vmraid.init(site=site)

	if not db_name:
		import hashlib

		db_name = "_" + hashlib.sha1(os.path.realpath(vmraid.get_site_path()).encode()).hexdigest()[:16]

	try:
		# enable scheduler post install?
		enable_scheduler = _is_scheduler_enabled()
	except Exception:
		enable_scheduler = False

	make_site_dirs()

	installing = touch_file(get_site_path("locks", "installing.lock"))

	install_db(
		root_login=db_root_username,
		root_password=db_root_password,
		db_name=db_name,
		admin_password=admin_password,
		verbose=verbose,
		source_sql=source_sql,
		force=force,
		reinstall=reinstall,
		db_password=db_password,
		db_type=db_type,
		db_host=db_host,
		db_port=db_port,
		no_mariadb_socket=no_mariadb_socket,
	)
	apps_to_install = (
		["vmraid"] + (vmraid.conf.get("install_apps") or []) + (list(install_apps) or [])
	)

	for app in apps_to_install:
		install_app(app, verbose=verbose, set_as_patched=not source_sql)

	os.remove(installing)

	scheduler.toggle_scheduler(enable_scheduler)
	vmraid.db.commit()

	scheduler_status = "disabled" if vmraid.utils.scheduler.is_scheduler_disabled() else "enabled"
	print("*** Scheduler is", scheduler_status, "***")


def install_db(
	root_login=None,
	root_password=None,
	db_name=None,
	source_sql=None,
	admin_password=None,
	verbose=True,
	force=0,
	site_config=None,
	reinstall=False,
	db_password=None,
	db_type=None,
	db_host=None,
	db_port=None,
	no_mariadb_socket=False,
):
	import vmraid.database
	from vmraid.database import setup_database

	if not db_type:
		db_type = vmraid.conf.db_type or "mariadb"

	if not root_login and db_type == "mariadb":
		root_login = "root"
	elif not root_login and db_type == "postgres":
		root_login = "postgres"

	make_conf(
		db_name,
		site_config=site_config,
		db_password=db_password,
		db_type=db_type,
		db_host=db_host,
		db_port=db_port,
	)
	vmraid.flags.in_install_db = True

	vmraid.flags.root_login = root_login
	vmraid.flags.root_password = root_password
	setup_database(force, source_sql, verbose, no_mariadb_socket)

	vmraid.conf.admin_password = vmraid.conf.admin_password or admin_password

	remove_missing_apps()

	vmraid.db.create_auth_table()
	vmraid.db.create_global_search_table()
	vmraid.db.create_user_settings_table()

	vmraid.flags.in_install_db = False


def find_org(org_repo: str) -> Tuple[str, str]:
	"""find the org a repo is in

	find_org()
	ref -> https://github.com/vmraid/chair/blob/develop/chair/utils/__init__.py#L390

	:param org_repo:
	:type org_repo: str

	:raises InvalidRemoteException: if the org is not found

	:return: organisation and repository
	:rtype: Tuple[str, str]
	"""
	import requests

	from vmraid.exceptions import InvalidRemoteException

	for org in ["vmraid", "erpadda"]:
		response = requests.head(f"https://api.github.com/repos/{org}/{org_repo}")
		if response.status_code == 400:
			response = requests.head(f"https://github.com/{org}/{org_repo}")
		if response.ok:
			return org, org_repo

	raise InvalidRemoteException


def fetch_details_from_tag(_tag: str) -> Tuple[str, str, str]:
	"""parse org, repo, tag from string

	fetch_details_from_tag()
	ref -> https://github.com/vmraid/chair/blob/develop/chair/utils/__init__.py#L403

	:param _tag: input string
	:type _tag: str

	:return: organisation, repostitory, tag
	:rtype: Tuple[str, str, str]
	"""
	app_tag = _tag.split("@")
	org_repo = app_tag[0].split("/")

	try:
		repo, tag = app_tag
	except ValueError:
		repo, tag = app_tag + [None]

	try:
		org, repo = org_repo
	except Exception:
		org, repo = find_org(org_repo[0])

	return org, repo, tag


def parse_app_name(name: str) -> str:
	"""parse repo name from name

	__setup_details_from_git()
	ref -> https://github.com/vmraid/chair/blob/develop/chair/app.py#L114


	:param name: git tag
	:type name: str

	:return: repository name
	:rtype: str
	"""
	name = name.rstrip("/")
	if os.path.exists(name):
		repo = os.path.split(name)[-1]
	elif is_git_url(name):
		if name.startswith("git@") or name.startswith("ssh://"):
			_repo = name.split(":")[1].rsplit("/", 1)[1]
		else:
			_repo = name.rsplit("/", 2)[2]
		repo = _repo.split(".")[0]
	else:
		_, repo, _ = fetch_details_from_tag(name)
	return repo


def install_app(name, verbose=False, set_as_patched=True):
	from vmraid.core.doctype.scheduled_job_type.scheduled_job_type import sync_jobs
	from vmraid.model.sync import sync_for
	from vmraid.modules.utils import sync_customizations
	from vmraid.utils.fixtures import sync_fixtures

	vmraid.flags.in_install = name
	vmraid.flags.ignore_in_install = False

	vmraid.clear_cache()
	app_hooks = vmraid.get_hooks(app_name=name)
	installed_apps = vmraid.get_installed_apps()

	# install pre-requisites
	if app_hooks.required_apps:
		for app in app_hooks.required_apps:
			required_app = parse_app_name(app)
			install_app(required_app, verbose=verbose)

	vmraid.flags.in_install = name
	vmraid.clear_cache()

	if name not in vmraid.get_all_apps():
		raise Exception("App not in apps.txt")

	if name in installed_apps:
		vmraid.msgprint(vmraid._("App {0} already installed").format(name))
		return

	print("\nInstalling {0}...".format(name))

	if name != "vmraid":
		vmraid.only_for("System Manager")

	for before_install in app_hooks.before_install or []:
		out = vmraid.get_attr(before_install)()
		if out is False:
			return

	if name != "vmraid":
		add_module_defs(name)

	sync_for(name, force=True, reset_permissions=True)

	add_to_installed_apps(name)

	vmraid.get_doc("Portal Settings", "Portal Settings").sync_menu()

	if set_as_patched:
		set_all_patches_as_completed(name)

	for after_install in app_hooks.after_install or []:
		vmraid.get_attr(after_install)()

	sync_jobs()
	sync_fixtures(name)
	sync_customizations(name)

	for after_sync in app_hooks.after_sync or []:
		vmraid.get_attr(after_sync)()  #

	vmraid.flags.in_install = False


def add_to_installed_apps(app_name, rebuild_website=True):
	installed_apps = vmraid.get_installed_apps()
	if app_name not in installed_apps:
		installed_apps.append(app_name)
		vmraid.db.set_global("installed_apps", json.dumps(installed_apps))
		vmraid.db.commit()
		if vmraid.flags.in_install:
			post_install(rebuild_website)


def remove_from_installed_apps(app_name):
	installed_apps = vmraid.get_installed_apps()
	if app_name in installed_apps:
		installed_apps.remove(app_name)
		vmraid.db.set_value(
			"DefaultValue", {"defkey": "installed_apps"}, "defvalue", json.dumps(installed_apps)
		)
		_clear_cache("__global")
		vmraid.db.commit()
		if vmraid.flags.in_install:
			post_install()


def remove_app(app_name, dry_run=False, yes=False, no_backup=False, force=False):
	"""Remove app and all linked to the app's module with the app from a site."""
	import click

	site = vmraid.local.site
	app_hooks = vmraid.get_hooks(app_name=app_name)

	# dont allow uninstall app if not installed unless forced
	if not force:
		if app_name not in vmraid.get_installed_apps():
			click.secho(f"App {app_name} not installed on Site {site}", fg="yellow")
			return

	print(f"Uninstalling App {app_name} from Site {site}...")

	if not dry_run and not yes:
		confirm = click.confirm(
			"All doctypes (including custom), modules related to this app will be"
			" deleted. Are you sure you want to continue?"
		)
		if not confirm:
			return

	if not (dry_run or no_backup):
		from vmraid.utils.backups import scheduled_backup

		print("Backing up...")
		scheduled_backup(ignore_files=True)

	vmraid.flags.in_uninstall = True

	for before_uninstall in app_hooks.before_uninstall or []:
		vmraid.get_attr(before_uninstall)()

	modules = vmraid.get_all("Module Def", filters={"app_name": app_name}, pluck="name")

	drop_doctypes = _delete_modules(modules, dry_run=dry_run)
	_delete_doctypes(drop_doctypes, dry_run=dry_run)

	if not dry_run:
		remove_from_installed_apps(app_name)
		vmraid.get_single("Installed Applications").update_versions()
		vmraid.db.commit()

	for after_uninstall in app_hooks.after_uninstall or []:
		vmraid.get_attr(after_uninstall)()

	click.secho(f"Uninstalled App {app_name} from Site {site}", fg="green")
	vmraid.flags.in_uninstall = False


def _delete_modules(modules: List[str], dry_run: bool) -> List[str]:
	"""Delete modules belonging to the app and all related doctypes.

	Note: All record linked linked to Module Def are also deleted.

	Returns: list of deleted doctypes."""
	drop_doctypes = []

	doctype_link_field_map = _get_module_linked_doctype_field_map()
	for module_name in modules:
		print(f"Deleting Module '{module_name}'")

		for doctype in vmraid.get_all(
			"DocType", filters={"module": module_name}, fields=["name", "issingle"]
		):
			print(f"* removing DocType '{doctype.name}'...")

			if not dry_run:
				if doctype.issingle:
					vmraid.delete_doc("DocType", doctype.name, ignore_on_trash=True)
				else:
					drop_doctypes.append(doctype.name)

		_delete_linked_documents(module_name, doctype_link_field_map, dry_run=dry_run)

		print(f"* removing Module Def '{module_name}'...")
		if not dry_run:
			vmraid.delete_doc("Module Def", module_name, ignore_on_trash=True, force=True)

	return drop_doctypes


def _delete_linked_documents(
	module_name: str, doctype_linkfield_map: Dict[str, str], dry_run: bool
) -> None:

	"""Deleted all records linked with module def"""
	for doctype, fieldname in doctype_linkfield_map.items():
		for record in vmraid.get_all(doctype, filters={fieldname: module_name}, pluck="name"):
			print(f"* removing {doctype} '{record}'...")
			if not dry_run:
				vmraid.delete_doc(doctype, record, ignore_on_trash=True, force=True)


def _get_module_linked_doctype_field_map() -> Dict[str, str]:
	"""Get all the doctypes which have module linked with them.

	returns ordered dictionary with doctype->link field mapping."""

	# Hardcoded to change order of deletion
	ordered_doctypes = [
		("Workspace", "module"),
		("Report", "module"),
		("Page", "module"),
		("Web Form", "module"),
	]
	doctype_to_field_map = OrderedDict(ordered_doctypes)

	linked_doctypes = vmraid.get_all(
		"DocField",
		filters={"fieldtype": "Link", "options": "Module Def"},
		fields=["parent", "fieldname"],
	)
	existing_linked_doctypes = [d for d in linked_doctypes if vmraid.db.exists("DocType", d.parent)]

	for d in existing_linked_doctypes:
		# DocType deletion is handled separately in the end
		if d.parent not in doctype_to_field_map and d.parent != "DocType":
			doctype_to_field_map[d.parent] = d.fieldname

	return doctype_to_field_map


def _delete_doctypes(doctypes: List[str], dry_run: bool) -> None:
	for doctype in set(doctypes):
		print(f"* dropping Table for '{doctype}'...")
		if not dry_run:
			vmraid.delete_doc("DocType", doctype, ignore_on_trash=True)
			vmraid.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")


def post_install(rebuild_website=False):
	from vmraid.website.utils import clear_website_cache

	if rebuild_website:
		clear_website_cache()

	init_singles()
	vmraid.db.commit()
	vmraid.clear_cache()


def set_all_patches_as_completed(app):
	from vmraid.modules.patch_handler import get_patches_from_app

	patches = get_patches_from_app(app)
	for patch in patches:
		vmraid.get_doc({"doctype": "Patch Log", "patch": patch}).insert(ignore_permissions=True)
	vmraid.db.commit()


def init_singles():
	singles = [single["name"] for single in vmraid.get_all("DocType", filters={"issingle": True})]
	for single in singles:
		if not vmraid.db.get_singles_dict(single):
			doc = vmraid.new_doc(single)
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_validate = True
			doc.save()


def make_conf(
	db_name=None, db_password=None, site_config=None, db_type=None, db_host=None, db_port=None
):
	site = vmraid.local.site
	make_site_config(
		db_name, db_password, site_config, db_type=db_type, db_host=db_host, db_port=db_port
	)
	sites_path = vmraid.local.sites_path
	vmraid.destroy()
	vmraid.init(site, sites_path=sites_path)


def make_site_config(
	db_name=None, db_password=None, site_config=None, db_type=None, db_host=None, db_port=None
):
	vmraid.create_folder(os.path.join(vmraid.local.site_path))
	site_file = get_site_config_path()

	if not os.path.exists(site_file):
		if not (site_config and isinstance(site_config, dict)):
			site_config = get_conf_params(db_name, db_password)

			if db_type:
				site_config["db_type"] = db_type

			if db_host:
				site_config["db_host"] = db_host

			if db_port:
				site_config["db_port"] = db_port

		with open(site_file, "w") as f:
			f.write(json.dumps(site_config, indent=1, sort_keys=True))


def update_site_config(key, value, validate=True, site_config_path=None):
	"""Update a value in site_config"""
	if not site_config_path:
		site_config_path = get_site_config_path()

	with open(site_config_path, "r") as f:
		site_config = json.loads(f.read())

	# In case of non-int value
	if value in ("0", "1"):
		value = int(value)

	# boolean
	if value == "false":
		value = False
	if value == "true":
		value = True

	# remove key if value is None
	if value == "None":
		if key in site_config:
			del site_config[key]
	else:
		site_config[key] = value

	with open(site_config_path, "w") as f:
		f.write(json.dumps(site_config, indent=1, sort_keys=True))

	if hasattr(vmraid.local, "conf"):
		vmraid.local.conf[key] = value


def get_site_config_path():
	return os.path.join(vmraid.local.site_path, "site_config.json")


def get_conf_params(db_name=None, db_password=None):
	if not db_name:
		db_name = input("Database Name: ")
		if not db_name:
			raise Exception("Database Name Required")

	if not db_password:
		from vmraid.utils import random_string

		db_password = random_string(16)

	return {"db_name": db_name, "db_password": db_password}


def make_site_dirs():
	for dir_path in [
		os.path.join("public", "files"),
		os.path.join("private", "backups"),
		os.path.join("private", "files"),
		"error-snapshots",
		"locks",
		"logs",
	]:
		path = vmraid.get_site_path(dir_path)
		os.makedirs(path, exist_ok=True)


def add_module_defs(app):
	modules = vmraid.get_module_list(app)
	for module in modules:
		d = vmraid.new_doc("Module Def")
		d.app_name = app
		d.module_name = module
		d.insert(ignore_permissions=True, ignore_if_duplicate=True)


def remove_missing_apps():
	import importlib

	apps = ("vmraid_subscription", "shopping_cart")
	installed_apps = json.loads(vmraid.db.get_global("installed_apps") or "[]")
	for app in apps:
		if app in installed_apps:
			try:
				importlib.import_module(app)

			except ImportError:
				installed_apps.remove(app)
				vmraid.db.set_global("installed_apps", json.dumps(installed_apps))


def extract_sql_from_archive(sql_file_path):
	"""Return the path of an SQL file if the passed argument is the path of a gzipped
	SQL file or an SQL file path. The path may be absolute or relative from the chair
	root directory or the sites sub-directory.

	Args:
	        sql_file_path (str): Path of the SQL file

	Returns:
	        str: Path of the decompressed SQL file
	"""
	from vmraid.utils import get_chair_relative_path

	sql_file_path = get_chair_relative_path(sql_file_path)
	# Extract the gzip file if user has passed *.sql.gz file instead of *.sql file
	if sql_file_path.endswith("sql.gz"):
		decompressed_file_name = extract_sql_gzip(sql_file_path)
	else:
		decompressed_file_name = sql_file_path

	# convert archive sql to latest compatible
	convert_archive_content(decompressed_file_name)

	return decompressed_file_name


def convert_archive_content(sql_file_path):
	if vmraid.conf.db_type == "mariadb":
		# ever since mariaDB 10.6, row_format COMPRESSED has been deprecated and removed
		# this step is added to ease restoring sites depending on older mariaDB servers
		from pathlib import Path

		from vmraid.utils import random_string

		old_sql_file_path = Path(f"{sql_file_path}_{random_string(10)}")
		sql_file_path = Path(sql_file_path)

		os.rename(sql_file_path, old_sql_file_path)
		sql_file_path.touch()

		with open(old_sql_file_path) as r, open(sql_file_path, "a") as w:
			for line in r:
				w.write(line.replace("ROW_FORMAT=COMPRESSED", "ROW_FORMAT=DYNAMIC"))

		old_sql_file_path.unlink()


def extract_sql_gzip(sql_gz_path):
	import subprocess

	try:
		original_file = sql_gz_path
		decompressed_file = original_file.rstrip(".gz")
		cmd = "gzip --decompress --force < {0} > {1}".format(original_file, decompressed_file)
		subprocess.check_call(cmd, shell=True)
	except Exception:
		raise

	return decompressed_file


def extract_files(site_name, file_path):
	import shutil
	import subprocess

	from vmraid.utils import get_chair_relative_path

	file_path = get_chair_relative_path(file_path)

	# Need to do vmraid.init to maintain the site locals
	vmraid.init(site=site_name)
	abs_site_path = os.path.abspath(vmraid.get_site_path())

	# Copy the files to the parent directory and extract
	shutil.copy2(os.path.abspath(file_path), abs_site_path)

	# Get the file name splitting the file path on
	tar_name = os.path.split(file_path)[1]
	tar_path = os.path.join(abs_site_path, tar_name)

	try:
		if file_path.endswith(".tar"):
			subprocess.check_output(["tar", "xvf", tar_path, "--strip", "2"], cwd=abs_site_path)
		elif file_path.endswith(".tgz"):
			subprocess.check_output(["tar", "zxvf", tar_path, "--strip", "2"], cwd=abs_site_path)
	except:
		raise
	finally:
		vmraid.destroy()

	return tar_path


def is_downgrade(sql_file_path, verbose=False):
	"""checks if input db backup will get downgraded on current chair"""

	# This function is only tested with mariadb
	# TODO: Add postgres support
	if vmraid.conf.db_type not in (None, "mariadb"):
		return False

	from semantic_version import Version

	head = "INSERT INTO `tabInstalled Application` VALUES"

	with open(sql_file_path) as f:
		for line in f:
			if head in line:
				# 'line' (str) format: ('2056588823','2020-05-11 18:21:31.488367','2020-06-12 11:49:31.079506','Administrator','Administrator',0,'Installed Applications','installed_applications','Installed Applications',1,'vmraid','v10.1.71-74 (3c50d5e) (v10.x.x)','v10.x.x'),('855c640b8e','2020-05-11 18:21:31.488367','2020-06-12 11:49:31.079506','Administrator','Administrator',0,'Installed Applications','installed_applications','Installed Applications',2,'your_custom_app','0.0.1','master')
				line = line.strip().lstrip(head).rstrip(";").strip()
				app_rows = vmraid.safe_eval(line)
				# check if iterable consists of tuples before trying to transform
				apps_list = (
					app_rows
					if all(isinstance(app_row, (tuple, list, set)) for app_row in app_rows)
					else (app_rows,)
				)
				# 'all_apps' (list) format: [('vmraid', '12.x.x-develop ()', 'develop'), ('your_custom_app', '0.0.1', 'master')]
				all_apps = [x[-3:] for x in apps_list]

				for app in all_apps:
					app_name = app[0]
					app_version = app[1].split(" ")[0]

					if app_name == "vmraid":
						try:
							current_version = Version(vmraid.__version__)
							backup_version = Version(app_version[1:] if app_version[0] == "v" else app_version)
						except ValueError:
							return False

						downgrade = backup_version > current_version

						if verbose and downgrade:
							print(f"Your site will be downgraded from VMRaid {backup_version} to {current_version}")

						return downgrade


def is_partial(sql_file_path):
	with open(sql_file_path) as f:
		header = " ".join(f.readline() for _ in range(5))
		if "Partial Backup" in header:
			return True
	return False


def partial_restore(sql_file_path, verbose=False):
	sql_file = extract_sql_from_archive(sql_file_path)

	if vmraid.conf.db_type in (None, "mariadb"):
		from vmraid.database.mariadb.setup_db import import_db_from_sql
	elif vmraid.conf.db_type == "postgres":
		import warnings

		from click import style

		from vmraid.database.postgres.setup_db import import_db_from_sql

		warn = style(
			"Delete the tables you want to restore manually before attempting"
			" partial restore operation for PostreSQL databases",
			fg="yellow",
		)
		warnings.warn(warn)

	import_db_from_sql(source_sql=sql_file, verbose=verbose)

	# Removing temporarily created file
	if sql_file != sql_file_path:
		os.remove(sql_file)


def validate_database_sql(path, _raise=True):
	"""Check if file has contents and if DefaultValue table exists

	Args:
	        path (str): Path of the decompressed SQL file
	        _raise (bool, optional): Raise exception if invalid file. Defaults to True.
	"""
	empty_file = False
	missing_table = True

	error_message = ""

	if not os.path.getsize(path):
		error_message = f"{path} is an empty file!"
		empty_file = True

	# dont bother checking if empty file
	if not empty_file:
		with open(path, "r") as f:
			for line in f:
				if "tabDefaultValue" in line:
					missing_table = False
					break

		if missing_table:
			error_message = "Table `tabDefaultValue` not found in file."

	if error_message:
		import click

		click.secho(error_message, fg="red")

	if _raise and (missing_table or empty_file):
		raise vmraid.InvalidDatabaseFile
