# Copyright (c) 2021, VMRaid and Contributors
# License: MIT. See LICENSE

import os
import re

import git

import vmraid
from vmraid.utils import cstr, touch_file


def make_boilerplate(dest, app_name, no_git=False):
	if not os.path.exists(dest):
		print("Destination directory does not exist")
		return

	# app_name should be in snake_case
	app_name = vmraid.scrub(app_name)

	hooks = vmraid._dict()
	hooks.app_name = app_name
	app_title = hooks.app_name.replace("_", " ").title()
	for key in (
		"App Title (default: {0})".format(app_title),
		"App Description",
		"App Publisher",
		"App Email",
		"App Icon (default 'octicon octicon-file-directory')",
		"App Color (default 'grey')",
		"App License (default 'MIT')",
	):
		hook_key = key.split(" (")[0].lower().replace(" ", "_")
		hook_val = None
		while not hook_val:
			hook_val = cstr(input(key + ": "))

			if not hook_val:
				defaults = {
					"app_title": app_title,
					"app_icon": "octicon octicon-file-directory",
					"app_color": "grey",
					"app_license": "MIT",
				}
				if hook_key in defaults:
					hook_val = defaults[hook_key]

			if hook_key == "app_name" and hook_val.lower().replace(" ", "_") != hook_val:
				print("App Name must be all lowercase and without spaces")
				hook_val = ""
			elif hook_key == "app_title" and not re.match(
				r"^(?![\W])[^\d_\s][\w -]+$", hook_val, re.UNICODE
			):
				print(
					"App Title should start with a letter and it can only consist of letters, numbers, spaces and underscores"
				)
				hook_val = ""

		hooks[hook_key] = hook_val

	vmraid.create_folder(
		os.path.join(dest, hooks.app_name, hooks.app_name, vmraid.scrub(hooks.app_title)), with_init=True
	)
	vmraid.create_folder(
		os.path.join(dest, hooks.app_name, hooks.app_name, "templates"), with_init=True
	)
	vmraid.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "www"))
	vmraid.create_folder(
		os.path.join(dest, hooks.app_name, hooks.app_name, "templates", "pages"), with_init=True
	)
	vmraid.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "templates", "includes"))
	vmraid.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "config"), with_init=True)
	vmraid.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "public", "css"))
	vmraid.create_folder(os.path.join(dest, hooks.app_name, hooks.app_name, "public", "js"))

	# add .gitkeep file so that public folder is committed to git
	# this is needed because if public doesn't exist, chair build doesn't symlink the apps assets
	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "public", ".gitkeep"), "w") as f:
		f.write("")

	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "__init__.py"), "w") as f:
		f.write(vmraid.as_unicode(init_template))

	with open(os.path.join(dest, hooks.app_name, "MANIFEST.in"), "w") as f:
		f.write(vmraid.as_unicode(manifest_template.format(**hooks)))

	with open(os.path.join(dest, hooks.app_name, "requirements.txt"), "w") as f:
		f.write("# vmraid -- https://github.com/vmraid/vmraid is installed via 'chair init'")

	with open(os.path.join(dest, hooks.app_name, "README.md"), "w") as f:
		f.write(
			vmraid.as_unicode(
				"## {0}\n\n{1}\n\n#### License\n\n{2}".format(
					hooks.app_title, hooks.app_description, hooks.app_license
				)
			)
		)

	with open(os.path.join(dest, hooks.app_name, "license.txt"), "w") as f:
		f.write(vmraid.as_unicode("License: " + hooks.app_license))

	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "modules.txt"), "w") as f:
		f.write(vmraid.as_unicode(hooks.app_title))

	# These values could contain quotes and can break string declarations
	# So escaping them before setting variables in setup.py and hooks.py
	for key in ("app_publisher", "app_description", "app_license"):
		hooks[key] = hooks[key].replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

	with open(os.path.join(dest, hooks.app_name, "setup.py"), "w") as f:
		f.write(vmraid.as_unicode(setup_template.format(**hooks)))

	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "hooks.py"), "w") as f:
		f.write(vmraid.as_unicode(hooks_template.format(**hooks)))

	touch_file(os.path.join(dest, hooks.app_name, hooks.app_name, "patches.txt"))

	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "config", "desktop.py"), "w") as f:
		f.write(vmraid.as_unicode(desktop_template.format(**hooks)))

	with open(os.path.join(dest, hooks.app_name, hooks.app_name, "config", "docs.py"), "w") as f:
		f.write(vmraid.as_unicode(docs_template.format(**hooks)))

	app_directory = os.path.join(dest, hooks.app_name)

	if not no_git:
		with open(os.path.join(dest, hooks.app_name, ".gitignore"), "w") as f:
			f.write(vmraid.as_unicode(gitignore_template.format(app_name=hooks.app_name)))

		# initialize git repository
		app_repo = git.Repo.init(app_directory)
		app_repo.git.add(A=True)
		app_repo.index.commit("feat: Initialize App")

	print("'{app}' created at {path}".format(app=app_name, path=app_directory))


manifest_template = """include MANIFEST.in
include requirements.txt
include *.json
include *.md
include *.py
include *.txt
recursive-include {app_name} *.css
recursive-include {app_name} *.csv
recursive-include {app_name} *.html
recursive-include {app_name} *.ico
recursive-include {app_name} *.js
recursive-include {app_name} *.json
recursive-include {app_name} *.md
recursive-include {app_name} *.png
recursive-include {app_name} *.py
recursive-include {app_name} *.svg
recursive-include {app_name} *.txt
recursive-exclude {app_name} *.pyc"""

init_template = """
__version__ = '0.0.1'

"""

hooks_template = """from . import __version__ as app_version

app_name = "{app_name}"
app_title = "{app_title}"
app_publisher = "{app_publisher}"
app_description = "{app_description}"
app_icon = "{app_icon}"
app_color = "{app_color}"
app_email = "{app_email}"
app_license = "{app_license}"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/{app_name}/css/{app_name}.css"
# app_include_js = "/assets/{app_name}/js/{app_name}.js"

# include js, css files in header of web template
# web_include_css = "/assets/{app_name}/css/{app_name}.css"
# web_include_js = "/assets/{app_name}/js/{app_name}.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "{app_name}/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {{"doctype": "public/js/doctype.js"}}
# webform_include_css = {{"doctype": "public/css/doctype.css"}}

# include js in page
# page_js = {{"page" : "public/js/file.js"}}

# include js in doctype views
# doctype_js = {{"doctype" : "public/js/doctype.js"}}
# doctype_list_js = {{"doctype" : "public/js/doctype_list.js"}}
# doctype_tree_js = {{"doctype" : "public/js/doctype_tree.js"}}
# doctype_calendar_js = {{"doctype" : "public/js/doctype_calendar.js"}}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {{
#	"Role": "home_page"
# }}

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {{
# 	"methods": "{app_name}.utils.jinja_methods",
# 	"filters": "{app_name}.utils.jinja_filters"
# }}

# Installation
# ------------

# before_install = "{app_name}.install.before_install"
# after_install = "{app_name}.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "{app_name}.uninstall.before_uninstall"
# after_uninstall = "{app_name}.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See vmraid.core.notifications.get_notification_config

# notification_config = "{app_name}.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {{
# 	"Event": "vmraid.desk.doctype.event.event.get_permission_query_conditions",
# }}
#
# has_permission = {{
# 	"Event": "vmraid.desk.doctype.event.event.has_permission",
# }}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {{
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {{
# 	"*": {{
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
#	}}
# }}

# Scheduled Tasks
# ---------------

# scheduler_events = {{
# 	"all": [
# 		"{app_name}.tasks.all"
# 	],
# 	"daily": [
# 		"{app_name}.tasks.daily"
# 	],
# 	"hourly": [
# 		"{app_name}.tasks.hourly"
# 	],
# 	"weekly": [
# 		"{app_name}.tasks.weekly"
# 	],
# 	"monthly": [
# 		"{app_name}.tasks.monthly"
# 	],
# }}

# Testing
# -------

# before_tests = "{app_name}.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {{
# 	"vmraid.desk.doctype.event.event.get_events": "{app_name}.event.get_events"
# }}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other VMRaid apps
# override_doctype_dashboards = {{
# 	"Task": "{app_name}.task.get_dashboard_data"
# }}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

# user_data_fields = [
# 	{{
# 		"doctype": "{{doctype_1}}",
# 		"filter_by": "{{filter_by}}",
# 		"redact_fields": ["{{field_1}}", "{{field_2}}"],
# 		"partial": 1,
# 	}},
# 	{{
# 		"doctype": "{{doctype_2}}",
# 		"filter_by": "{{filter_by}}",
# 		"partial": 1,
# 	}},
# 	{{
# 		"doctype": "{{doctype_3}}",
# 		"strict": False,
# 	}},
# 	{{
# 		"doctype": "{{doctype_4}}"
# 	}}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"{app_name}.auth.validate"
# ]

# Translation
# --------------------------------

# Make link fields search translated document names for these DocTypes
# Recommended only for DocTypes which have limited documents with untranslated names
# For example: Role, Gender, etc.
# translated_search_doctypes = []
"""

desktop_template = """from vmraid import _

def get_data():
	return [
		{{
			"module_name": "{app_title}",
			"color": "{app_color}",
			"icon": "{app_icon}",
			"type": "module",
			"label": _("{app_title}")
		}}
	]
"""

setup_template = """from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\\n")

# get version from __version__ variable in {app_name}/__init__.py
from {app_name} import __version__ as version

setup(
	name="{app_name}",
	version=version,
	description="{app_description}",
	author="{app_publisher}",
	author_email="{app_email}",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
"""

gitignore_template = """.DS_Store
*.pyc
*.egg-info
*.swp
tags
{app_name}/docs/current"""

docs_template = '''"""
Configuration for docs
"""

# source_link = "https://github.com/[org_name]/{app_name}"
# headline = "App that does everything"
# sub_heading = "Yes, you got that right the first time, everything"

def get_context(context):
	context.brand_html = "{app_title}"
'''
