# Copyright (c) 2015, VMRaid Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

import os
import re
import json
import shutil
import subprocess
from tempfile import mkdtemp, mktemp
from distutils.spawn import find_executable

import vmraid
from vmraid.utils.minify import JavascriptMinify

import click
import psutil
from urllib.parse import urlparse
from simple_chalk import green
from semantic_version import Version


timestamps = {}
app_paths = None
sites_path = os.path.abspath(os.getcwd())


def download_file(url, prefix):
	from requests import get

	filename = urlparse(url).path.split("/")[-1]
	local_filename = os.path.join(prefix, filename)
	with get(url, stream=True, allow_redirects=True) as r:
		r.raise_for_status()
		with open(local_filename, "wb") as f:
			for chunk in r.iter_content(chunk_size=8192):
				f.write(chunk)
	return local_filename


def build_missing_files():
	'''Check which files dont exist yet from the assets.json and run build for those files'''

	missing_assets = []
	current_asset_files = []

	for type in ["css", "js"]:
		folder = os.path.join(sites_path, "assets", "vmraid", "dist", type)
		current_asset_files.extend(os.listdir(folder))

	development = vmraid.local.conf.developer_mode or vmraid.local.dev_server
	build_mode = "development" if development else "production"

	assets_json = vmraid.read_file("assets/assets.json")
	if assets_json:
		assets_json = vmraid.parse_json(assets_json)

		for bundle_file, output_file in assets_json.items():
			if not output_file.startswith('/assets/vmraid'):
				continue

			if os.path.basename(output_file) not in current_asset_files:
				missing_assets.append(bundle_file)

		if missing_assets:
			click.secho("\nBuilding missing assets...\n", fg="yellow")
			files_to_build = ["vmraid/" + name for name in missing_assets]
			bundle(build_mode, files=files_to_build)
	else:
		# no assets.json, run full build
		bundle(build_mode, apps="vmraid")


def get_assets_link(vmraid_head):
	from subprocess import getoutput
	from requests import head

	tag = getoutput(
			r"cd ../apps/vmraid && git show-ref --tags -d | grep %s | sed -e 's,.*"
			r" refs/tags/,,' -e 's/\^{}//'"
			% vmraid_head
		)

	if tag:
		# if tag exists, download assets from github release
		url = "https://github.com/vmraid/vmraid/releases/download/{0}/assets.tar.gz".format(tag)
	else:
		url = "http://assets.vmraidframework.com/{0}.tar.gz".format(vmraid_head)

	if not head(url):
		raise ValueError("URL {0} doesn't exist".format(url))

	return url


def download_vmraid_assets(verbose=True):
	"""Downloads and sets up VMRaid assets if they exist based on the current
	commit HEAD.
	Returns True if correctly setup else returns False.
	"""
	from subprocess import getoutput

	assets_setup = False
	vmraid_head = getoutput("cd ../apps/vmraid && git rev-parse HEAD")

	if vmraid_head:
		try:
			print("VmRaid Head: ", vmraid_head)
			url = get_assets_link(vmraid_head)
			click.secho("Retrieving assets...", fg="yellow")
			prefix = mkdtemp(prefix="vmraid-assets-", suffix=vmraid_head)
			assets_archive = download_file(url, prefix)
			print("\n{0} Downloaded VMRaid assets from {1}".format(green('✔'), url))

			if assets_archive:
				import tarfile
				directories_created = set()

				click.secho("\nExtracting assets...\n", fg="yellow")
				with tarfile.open(assets_archive) as tar:
					for file in tar:
						if not file.isdir():
							dest = "." + file.name.replace("./vmraid-chair/sites", "")
							asset_directory = os.path.dirname(dest)
							show = dest.replace("./assets/", "")

							if asset_directory not in directories_created:
								if not os.path.exists(asset_directory):
									os.makedirs(asset_directory, exist_ok=True)
								directories_created.add(asset_directory)

							tar.makefile(file, dest)
							print("{0} Restored {1}".format(green('✔'), show))

				build_missing_files()
				return True
			else:
				raise
		except Exception:
			# TODO: log traceback in chair.log
			click.secho("An Error occurred while downloading assets...", fg="red")
			assets_setup = False
		finally:
			try:
				shutil.rmtree(os.path.dirname(assets_archive))
			except Exception:
				pass

	return assets_setup


def symlink(target, link_name, overwrite=False):
	"""
	Create a symbolic link named link_name pointing to target.
	If link_name exists then FileExistsError is raised, unless overwrite=True.
	When trying to overwrite a directory, IsADirectoryError is raised.

	Source: https://stackoverflow.com/a/55742015/10309266
	"""

	if not overwrite:
		return os.symlink(target, link_name)

	# os.replace() may fail if files are on different filesystems
	link_dir = os.path.dirname(link_name)

	# Create link to target with temporary filename
	while True:
		temp_link_name = mktemp(dir=link_dir)

		# os.* functions mimic as closely as possible system functions
		# The POSIX symlink() returns EEXIST if link_name already exists
		# https://pubs.opengroup.org/onlinepubs/9699919799/functions/symlink.html
		try:
			os.symlink(target, temp_link_name)
			break
		except FileExistsError:
			pass

	# Replace link_name with temp_link_name
	try:
		# Pre-empt os.replace on a directory with a nicer message
		if os.path.isdir(link_name):
			raise IsADirectoryError("Cannot symlink over existing directory: '{}'".format(link_name))
		try:
			os.replace(temp_link_name, link_name)
		except AttributeError:
			os.renames(temp_link_name, link_name)
	except:
		if os.path.islink(temp_link_name):
			os.remove(temp_link_name)
		raise


def setup():
	global app_paths, assets_path

	pymodules = []
	for app in vmraid.get_all_apps(True):
		try:
			pymodules.append(vmraid.get_module(app))
		except ImportError:
			pass
	app_paths = [os.path.dirname(pymodule.__file__) for pymodule in pymodules]
	assets_path = os.path.join(vmraid.local.sites_path, "assets")


def bundle(mode, apps=None, hard_link=False, make_copy=False, restore=False, verbose=False, skip_vmraid=False, files=None):
	"""concat / minify js files"""
	setup()
	make_asset_dirs(hard_link=hard_link)

	mode = "production" if mode == "production" else "build"
	command = "yarn run {mode}".format(mode=mode)

	if apps:
		command += " --apps {apps}".format(apps=apps)

	if skip_vmraid:
		command += " --skip_vmraid"

	if files:
		command += " --files {files}".format(files=','.join(files))

	command += " --run-build-command"

	check_node_executable()
	vmraid_app_path = vmraid.get_app_path("vmraid", "..")
	vmraid.commands.popen(command, cwd=vmraid_app_path, env=get_node_env())


def watch(apps=None):
	"""watch and rebuild if necessary"""
	setup()

	command = "yarn run watch"
	if apps:
		command += " --apps {apps}".format(apps=apps)

	check_node_executable()
	vmraid_app_path = vmraid.get_app_path("vmraid", "..")
	vmraid.commands.popen(command, cwd=vmraid_app_path, env=get_node_env())


def check_node_executable():
	node_version = Version(subprocess.getoutput('node -v')[1:])
	warn = '⚠️ '
	if node_version.major < 14:
		click.echo(f"{warn} Please update your node version to 14")
	if not find_executable("yarn"):
		click.echo(f"{warn} Please install yarn using below command and try again.\nnpm install -g yarn")
	click.echo()

def get_node_env():
	node_env = {
		"NODE_OPTIONS": f"--max_old_space_size={get_safe_max_old_space_size()}"
	}
	return node_env

def get_safe_max_old_space_size():
	safe_max_old_space_size = 0
	try:
		total_memory = psutil.virtual_memory().total / (1024 * 1024)
		# reference for the safe limit assumption
		# https://nodejs.org/api/cli.html#cli_max_old_space_size_size_in_megabytes
		# set minimum value 1GB
		safe_max_old_space_size = max(1024, int(total_memory * 0.75))
	except Exception:
		pass

	return safe_max_old_space_size

def generate_assets_map():
	symlinks = {}

	for app_name in vmraid.get_all_apps():
		app_doc_path = None

		pymodule = vmraid.get_module(app_name)
		app_base_path = os.path.abspath(os.path.dirname(pymodule.__file__))
		app_public_path = os.path.join(app_base_path, "public")
		app_node_modules_path = os.path.join(app_base_path, "..", "node_modules")
		app_docs_path = os.path.join(app_base_path, "docs")
		app_www_docs_path = os.path.join(app_base_path, "www", "docs")

		app_assets = os.path.abspath(app_public_path)
		app_node_modules = os.path.abspath(app_node_modules_path)

		# {app}/public > assets/{app}
		if os.path.isdir(app_assets):
			symlinks[app_assets] = os.path.join(assets_path, app_name)

		# {app}/node_modules > assets/{app}/node_modules
		if os.path.isdir(app_node_modules):
			symlinks[app_node_modules] = os.path.join(assets_path, app_name, "node_modules")

		# {app}/docs > assets/{app}_docs
		if os.path.isdir(app_docs_path):
			app_doc_path = os.path.join(app_base_path, "docs")
		elif os.path.isdir(app_www_docs_path):
			app_doc_path = os.path.join(app_base_path, "www", "docs")
		if app_doc_path:
			app_docs = os.path.abspath(app_doc_path)
			symlinks[app_docs] = os.path.join(assets_path, app_name + "_docs")

	return symlinks


def setup_assets_dirs():
	for dir_path in (os.path.join(assets_path, x) for x in ("js", "css")):
		os.makedirs(dir_path, exist_ok=True)


def clear_broken_symlinks():
	for path in os.listdir(assets_path):
		path = os.path.join(assets_path, path)
		if os.path.islink(path) and not os.path.exists(path):
			os.remove(path)



def unstrip(message: str) -> str:
	"""Pads input string on the right side until the last available column in the terminal
	"""
	_len = len(message)
	try:
		max_str = os.get_terminal_size().columns
	except Exception:
		max_str = 80

	if _len < max_str:
		_rem = max_str - _len
	else:
		_rem = max_str % _len

	return f"{message}{' ' * _rem}"


def make_asset_dirs(hard_link=False):
	setup_assets_dirs()
	clear_broken_symlinks()
	symlinks = generate_assets_map()

	for source, target in symlinks.items():
		start_message = unstrip(f"{'Copying assets from' if hard_link else 'Linking'} {source} to {target}")
		fail_message = unstrip(f"Cannot {'copy' if hard_link else 'link'} {source} to {target}")

		# Used '\r' instead of '\x1b[1K\r' to print entire lines in smaller terminal sizes
		try:
			print(start_message, end="\r")
			link_assets_dir(source, target, hard_link=hard_link)
		except Exception:
			print(fail_message, end="\r")

	print(unstrip(f"{green('✔')} Application Assets Linked") + "\n")


def link_assets_dir(source, target, hard_link=False):
	if not os.path.exists(source):
		return

	if os.path.exists(target):
		if os.path.islink(target):
			os.unlink(target)
		else:
			shutil.rmtree(target)

	if hard_link:
		shutil.copytree(source, target, dirs_exist_ok=True)
	else:
		symlink(source, target, overwrite=True)


def build(no_compress=False, verbose=False):
	for target, sources in get_build_maps().items():
		pack(os.path.join(assets_path, target), sources, no_compress, verbose)


def get_build_maps():
	"""get all build.jsons with absolute paths"""
	# framework js and css files

	build_maps = {}
	for app_path in app_paths:
		path = os.path.join(app_path, "public", "build.json")
		if os.path.exists(path):
			with open(path) as f:
				try:
					for target, sources in (json.loads(f.read() or "{}")).items():
						# update app path
						source_paths = []
						for source in sources:
							if isinstance(source, list):
								s = vmraid.get_pymodule_path(source[0], *source[1].split("/"))
							else:
								s = os.path.join(app_path, source)
							source_paths.append(s)

						build_maps[target] = source_paths
				except ValueError as e:
					print(path)
					print("JSON syntax error {0}".format(str(e)))
	return build_maps


def pack(target, sources, no_compress, verbose):
	from six import StringIO

	outtype, outtxt = target.split(".")[-1], ""
	jsm = JavascriptMinify()

	for f in sources:
		suffix = None
		if ":" in f:
			f, suffix = f.split(":")
		if not os.path.exists(f) or os.path.isdir(f):
			print("did not find " + f)
			continue
		timestamps[f] = os.path.getmtime(f)
		try:
			with open(f, "r") as sourcefile:
				data = str(sourcefile.read(), "utf-8", errors="ignore")

			extn = f.rsplit(".", 1)[1]

			if (
				outtype == "js"
				and extn == "js"
				and (not no_compress)
				and suffix != "concat"
				and (".min." not in f)
			):
				tmpin, tmpout = StringIO(data.encode("utf-8")), StringIO()
				jsm.minify(tmpin, tmpout)
				minified = tmpout.getvalue()
				if minified:
					outtxt += str(minified or "", "utf-8").strip("\n") + ";"

				if verbose:
					print("{0}: {1}k".format(f, int(len(minified) / 1024)))
			elif outtype == "js" and extn == "html":
				# add to vmraid.templates
				outtxt += html_to_js_template(f, data)
			else:
				outtxt += "\n/*\n *\t%s\n */" % f
				outtxt += "\n" + data + "\n"

		except Exception:
			print("--Error in:" + f + "--")
			print(vmraid.get_traceback())

	with open(target, "w") as f:
		f.write(outtxt.encode("utf-8"))

	print("Wrote %s - %sk" % (target, str(int(os.path.getsize(target) / 1024))))


def html_to_js_template(path, content):
	"""returns HTML template content as Javascript code, adding it to `vmraid.templates`"""
	return """vmraid.templates["{key}"] = '{content}';\n""".format(
		key=path.rsplit("/", 1)[-1][:-5], content=scrub_html_template(content))


def scrub_html_template(content):
	"""Returns HTML content with removed whitespace and comments"""
	# remove whitespace to a single space
	content = re.sub(r"\s+", " ", content)

	# strip comments
	content = re.sub(r"(<!--.*?-->)", "", content)

	return content.replace("'", "\'")


def files_dirty():
	for target, sources in get_build_maps().items():
		for f in sources:
			if ":" in f:
				f, suffix = f.split(":")
			if not os.path.exists(f) or os.path.isdir(f):
				continue
			if os.path.getmtime(f) != timestamps.get(f):
				print(f + " dirty")
				return True
	else:
		return False


def compile_less():
	if not find_executable("lessc"):
		return

	for path in app_paths:
		less_path = os.path.join(path, "public", "less")
		if os.path.exists(less_path):
			for fname in os.listdir(less_path):
				if fname.endswith(".less") and fname != "variables.less":
					fpath = os.path.join(less_path, fname)
					mtime = os.path.getmtime(fpath)
					if fpath in timestamps and mtime == timestamps[fpath]:
						continue

					timestamps[fpath] = mtime

					print("compiling {0}".format(fpath))

					css_path = os.path.join(path, "public", "css", fname.rsplit(".", 1)[0] + ".css")
					os.system("lessc {0} > {1}".format(fpath, css_path))
