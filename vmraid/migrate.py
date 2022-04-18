# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE

import json
import os
from textwrap import dedent

import vmraid
import vmraid.model.sync
import vmraid.modules.patch_handler
import vmraid.translate
from vmraid.cache_manager import clear_global_cache
from vmraid.core.doctype.language.language import sync_languages
from vmraid.core.doctype.scheduled_job_type.scheduled_job_type import sync_jobs
from vmraid.database.schema import add_column
from vmraid.desk.notifications import clear_notifications
from vmraid.modules.patch_handler import PatchType
from vmraid.modules.utils import sync_customizations
from vmraid.search.website_search import build_index_for_all_routes
from vmraid.utils.connections import check_connection
from vmraid.utils.dashboard import sync_dashboards
from vmraid.utils.fixtures import sync_fixtures
from vmraid.website.utils import clear_website_cache

CHAIR_START_MESSAGE = dedent(
	"""
	Cannot run chair migrate without the services running.
	If you are running chair in development mode, make sure that chair is running:

	$ chair start

	Otherwise, check the server logs and ensure that all the required services are running.
	"""
)


def atomic(method):
	def wrapper(*args, **kwargs):
		try:
			ret = method(*args, **kwargs)
			vmraid.db.commit()
			return ret
		except Exception:
			vmraid.db.rollback()
			raise

	return wrapper


class SiteMigration:
	"""Migrate all apps to the current version, will:
	- run before migrate hooks
	- run patches
	- sync doctypes (schema)
	- sync dashboards
	- sync jobs
	- sync fixtures
	- sync customizations
	- sync languages
	- sync web pages (from /www)
	- run after migrate hooks
	"""

	def __init__(self, skip_failing: bool = False, skip_search_index: bool = False) -> None:
		self.skip_failing = skip_failing
		self.skip_search_index = skip_search_index

	def setUp(self):
		"""Complete setup required for site migration"""
		vmraid.flags.touched_tables = set()
		self.touched_tables_file = vmraid.get_site_path("touched_tables.json")
		add_column(doctype="DocType", column_name="migration_hash", fieldtype="Data")
		clear_global_cache()

		if os.path.exists(self.touched_tables_file):
			os.remove(self.touched_tables_file)

		vmraid.flags.in_migrate = True

	def tearDown(self):
		"""Run operations that should be run post schema updation processes
		This should be executed irrespective of outcome
		"""
		vmraid.translate.clear_cache()
		clear_website_cache()
		clear_notifications()

		with open(self.touched_tables_file, "w") as f:
			json.dump(list(vmraid.flags.touched_tables), f, sort_keys=True, indent=4)

		if not self.skip_search_index:
			print(f"Building search index for {vmraid.local.site}")
			build_index_for_all_routes()

		vmraid.publish_realtime("version-update")
		vmraid.flags.touched_tables.clear()
		vmraid.flags.in_migrate = False

	@atomic
	def pre_schema_updates(self):
		"""Executes `before_migrate` hooks"""
		for app in vmraid.get_installed_apps():
			for fn in vmraid.get_hooks("before_migrate", app_name=app):
				vmraid.get_attr(fn)()

	@atomic
	def run_schema_updates(self):
		"""Run patches as defined in patches.txt, sync schema changes as defined in the {doctype}.json files"""
		vmraid.modules.patch_handler.run_all(
			skip_failing=self.skip_failing, patch_type=PatchType.pre_model_sync
		)
		vmraid.model.sync.sync_all()
		vmraid.modules.patch_handler.run_all(
			skip_failing=self.skip_failing, patch_type=PatchType.post_model_sync
		)

	@atomic
	def post_schema_updates(self):
		"""Execute pending migration tasks post patches execution & schema sync
		This includes:
		* Sync `Scheduled Job Type` and scheduler events defined in hooks
		* Sync fixtures & custom scripts
		* Sync in-Desk Module Dashboards
		* Sync customizations: Custom Fields, Property Setters, Custom Permissions
		* Sync VMRaid's internal language master
		* Sync Portal Menu Items
		* Sync Installed Applications Version History
		* Execute `after_migrate` hooks
		"""
		sync_jobs()
		sync_fixtures()
		sync_dashboards()
		sync_customizations()
		sync_languages()

		vmraid.get_single("Portal Settings").sync_menu()
		vmraid.get_single("Installed Applications").update_versions()

		for app in vmraid.get_installed_apps():
			for fn in vmraid.get_hooks("after_migrate", app_name=app):
				vmraid.get_attr(fn)()

	def required_services_running(self) -> bool:
		"""Returns True if all required services are running. Returns False and prints
		instructions to stdout when required services are not available.
		"""
		service_status = check_connection(redis_services=["redis_cache"])
		are_services_running = all(service_status.values())

		if not are_services_running:
			for service in service_status:
				if not service_status.get(service, True):
					print(f"Service {service} is not running.")
			print(CHAIR_START_MESSAGE)

		return are_services_running

	def run(self, site: str):
		"""Run Migrate operation on site specified. This method initializes
		and destroys connections to the site database.
		"""
		if not self.required_services_running():
			raise SystemExit(1)

		if site:
			vmraid.init(site=site)
			vmraid.connect()

		self.setUp()
		try:
			self.pre_schema_updates()
			self.run_schema_updates()
		finally:
			self.post_schema_updates()
			self.tearDown()
			vmraid.destroy()
