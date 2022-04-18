# Copyright (c) 2015, VMRaid and Contributors
# License: MIT. See LICENSE

import io
import os
import re

from werkzeug.routing import Map, NotFound, Rule

import vmraid
from vmraid.website.utils import extract_title


def get_page_info_from_web_page_with_dynamic_routes(path):
	"""
	Query Web Page with dynamic_route = 1 and evaluate if any of the routes match
	"""
	rules, page_info = [], {}

	# build rules from all web page with `dynamic_route = 1`
	for d in vmraid.get_all(
		"Web Page", fields=["name", "route", "modified"], filters=dict(published=1, dynamic_route=1)
	):
		rules.append(Rule("/" + d.route, endpoint=d.name))
		d.doctype = "Web Page"
		page_info[d.name] = d

	end_point = evaluate_dynamic_routes(rules, path)
	if end_point:
		return page_info[end_point]


def evaluate_dynamic_routes(rules, path):
	"""
	Use Werkzeug routing to evaluate dynamic routes like /project/<name>
	https://werkzeug.palletsprojects.com/en/1.0.x/routing/
	"""
	route_map = Map(rules)
	endpoint = None

	if hasattr(vmraid.local, "request") and vmraid.local.request.environ:
		urls = route_map.bind_to_environ(vmraid.local.request.environ)
		try:
			endpoint, args = urls.match("/" + path)
			path = endpoint
			if args:
				# don't cache when there's a query string!
				vmraid.local.no_cache = 1
				vmraid.local.form_dict.update(args)

		except NotFound:
			pass

	return endpoint


def get_pages(app=None):
	"""Get all pages. Called for docs / sitemap"""

	def _build(app):
		pages = {}

		if app:
			apps = [app]
		else:
			apps = vmraid.local.flags.web_pages_apps or vmraid.get_installed_apps()

		for app in apps:
			app_path = vmraid.get_app_path(app)

			for start in get_start_folders():
				pages.update(get_pages_from_path(start, app, app_path))

		return pages

	return vmraid.cache().get_value("website_pages", lambda: _build(app))


def get_pages_from_path(start, app, app_path):
	pages = {}
	start_path = os.path.join(app_path, start)
	if os.path.exists(start_path):
		for basepath, folders, files in os.walk(start_path):
			# add missing __init__.py
			if not "__init__.py" in files:
				open(os.path.join(basepath, "__init__.py"), "a").close()

			for fname in files:
				fname = vmraid.utils.cstr(fname)
				if not "." in fname:
					continue
				page_name, extn = fname.rsplit(".", 1)
				if extn in ("js", "css") and os.path.exists(os.path.join(basepath, page_name + ".html")):
					# js, css is linked to html, skip
					continue

				if extn in ("html", "xml", "js", "css", "md"):
					page_info = get_page_info(
						os.path.join(basepath, fname), app, start, basepath, app_path, fname
					)
					pages[page_info.route] = page_info
					# print vmraid.as_json(pages[-1])

	return pages


def get_page_info(path, app, start, basepath=None, app_path=None, fname=None):
	"""Load page info"""
	if fname is None:
		fname = os.path.basename(path)

	if app_path is None:
		app_path = vmraid.get_app_path(app)

	if basepath is None:
		basepath = os.path.dirname(path)

	page_name, extn = os.path.splitext(fname)

	# add website route
	page_info = vmraid._dict()

	page_info.basename = page_name if extn in ("html", "md") else fname
	page_info.basepath = basepath
	page_info.page_or_generator = "Page"

	page_info.template = os.path.relpath(os.path.join(basepath, fname), app_path)

	if page_info.basename == "index":
		page_info.basename = ""

	# get route from template name
	page_info.route = page_info.template.replace(start, "").strip("/")
	if os.path.basename(page_info.route) in ("index.html", "index.md"):
		page_info.route = os.path.dirname(page_info.route)

	# remove the extension
	if page_info.route.endswith(".md") or page_info.route.endswith(".html"):
		page_info.route = page_info.route.rsplit(".", 1)[0]

	page_info.name = page_info.page_name = page_info.route
	# controller
	page_info.controller_path = os.path.join(basepath, page_name.replace("-", "_") + ".py")

	if os.path.exists(page_info.controller_path):
		controller = (
			app + "." + os.path.relpath(page_info.controller_path, app_path).replace(os.path.sep, ".")[:-3]
		)

		page_info.controller = controller

	# get the source
	setup_source(page_info)

	if not page_info.title:
		page_info.title = extract_title(page_info.source, page_info.route)

	# extract properties from controller attributes
	load_properties_from_controller(page_info)

	return page_info


def get_frontmatter(string):
	"""
	Reference: https://github.com/jonbeebe/frontmatter
	"""
	import yaml

	fmatter = ""
	body = ""
	result = re.compile(r"^\s*(?:---|\+\+\+)(.*?)(?:---|\+\+\+)\s*(.+)$", re.S | re.M).search(string)

	if result:
		fmatter = result.group(1)
		body = result.group(2)

	return {
		"attributes": yaml.safe_load(fmatter),
		"body": body,
	}


def setup_source(page_info):
	"""Get the HTML source of the template"""
	jenv = vmraid.get_jenv()
	source = jenv.loader.get_source(jenv, page_info.template)[0]
	html = ""

	if page_info.template.endswith((".md", ".html")):
		# extract frontmatter block if exists
		try:
			# values will be used to update page_info
			res = get_frontmatter(source)
			if res["attributes"]:
				page_info.update(res["attributes"])
				source = res["body"]
		except Exception:
			pass

		if page_info.template.endswith(".md"):
			source = vmraid.utils.md_to_html(source)
			page_info.page_toc_html = source.toc_html

			if not page_info.show_sidebar:
				source = '<div class="from-markdown">' + source + "</div>"

	if not page_info.base_template:
		page_info.base_template = get_base_template(page_info.route)

	if (
		page_info.template.endswith(
			(
				".html",
				".md",
			)
		)
		and "{%- extends" not in source
		and "{% extends" not in source
	):
		# set the source only if it contains raw content
		html = source

	# load css/js files
	js_path = os.path.join(page_info.basepath, (page_info.basename or "index") + ".js")
	if os.path.exists(js_path) and "{% block script %}" not in html:
		with io.open(js_path, "r", encoding="utf-8") as f:
			js = f.read()
			page_info.colocated_js = js

	css_path = os.path.join(page_info.basepath, (page_info.basename or "index") + ".css")
	if os.path.exists(css_path) and "{% block style %}" not in html:
		with io.open(css_path, "r", encoding="utf-8") as f:
			css = f.read()
			page_info.colocated_css = css

	if html:
		page_info.source = html
		page_info.base_template = page_info.base_template or "templates/web.html"
	else:
		page_info.source = ""

	# show table of contents
	setup_index(page_info)


def get_base_template(path=None):
	"""
	Returns the `base_template` for given `path`.
	The default `base_template` for any web route is `templates/web.html` defined in `hooks.py`.
	This can be overridden for certain routes in `custom_app/hooks.py` based on regex pattern.
	"""
	if not path:
		path = vmraid.local.request.path

	base_template_map = vmraid.get_hooks("base_template_map") or {}
	patterns = list(base_template_map.keys())
	patterns_desc = sorted(patterns, key=lambda x: len(x), reverse=True)
	for pattern in patterns_desc:
		if re.match(pattern, path):
			templates = base_template_map[pattern]
			base_template = templates[-1]
			return base_template


def setup_index(page_info):
	"""Build page sequence from index.txt"""
	if page_info.basename == "":
		# load index.txt if loading all pages
		index_txt_path = os.path.join(page_info.basepath, "index.txt")
		if os.path.exists(index_txt_path):
			with open(index_txt_path, "r") as f:
				page_info.index = f.read().splitlines()


def load_properties_from_controller(page_info):
	if not page_info.controller:
		return

	module = vmraid.get_module(page_info.controller)
	if not module:
		return

	for prop in ("base_template_path", "template", "no_cache", "sitemap", "condition_field"):
		if hasattr(module, prop):
			page_info[prop] = getattr(module, prop)


def get_doctypes_with_web_view():
	"""Return doctypes with Has Web View or set via hooks"""

	def _get():
		installed_apps = vmraid.get_installed_apps()
		doctypes = vmraid.get_hooks("website_generators")
		doctypes_with_web_view = vmraid.get_all(
			"DocType", fields=["name", "module"], filters=dict(has_web_view=1)
		)
		module_app_map = vmraid.local.module_app
		doctypes += [
			d.name
			for d in doctypes_with_web_view
			if module_app_map.get(vmraid.scrub(d.module)) in installed_apps
		]
		return doctypes

	return vmraid.cache().get_value("doctypes_with_web_view", _get)


def get_start_folders():
	return vmraid.local.flags.web_pages_folders or ("www", "templates/pages")
