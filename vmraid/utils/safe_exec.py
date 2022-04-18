import copy
import inspect
import json
import mimetypes

import RestrictedPython.Guards
from html2text import html2text
from RestrictedPython import compile_restricted, safe_globals

import vmraid
import vmraid.exceptions
import vmraid.integrations.utils
import vmraid.utils
import vmraid.utils.data
from vmraid import _
from vmraid.vmraidclient import VMRaidClient
from vmraid.handler import execute_cmd
from vmraid.modules import scrub
from vmraid.utils.background_jobs import enqueue, get_jobs
from vmraid.website.utils import get_next_link, get_shade, get_toc
from vmraid.www.printview import get_visible_columns


class ServerScriptNotEnabled(vmraid.PermissionError):
	pass


class NamespaceDict(vmraid._dict):
	"""Raise AttributeError if function not found in namespace"""

	def __getattr__(self, key):
		ret = self.get(key)
		if (not ret and key.startswith("__")) or (key not in self):

			def default_function(*args, **kwargs):
				raise AttributeError(f"module has no attribute '{key}'")

			return default_function
		return ret


def safe_exec(script, _globals=None, _locals=None, restrict_commit_rollback=False):
	# server scripts can be disabled via site_config.json
	# they are enabled by default
	if "server_script_enabled" in vmraid.conf:
		enabled = vmraid.conf.server_script_enabled
	else:
		enabled = True

	if not enabled:
		vmraid.throw(_("Please Enable Server Scripts"), ServerScriptNotEnabled)

	# build globals
	exec_globals = get_safe_globals()
	if _globals:
		exec_globals.update(_globals)

	if restrict_commit_rollback:
		# prevent user from using these in docevents
		exec_globals.vmraid.db.pop("commit", None)
		exec_globals.vmraid.db.pop("rollback", None)
		exec_globals.vmraid.db.pop("add_index", None)

	# execute script compiled by RestrictedPython
	vmraid.flags.in_safe_exec = True
	exec(compile_restricted(script), exec_globals, _locals)  # pylint: disable=exec-used
	vmraid.flags.in_safe_exec = False

	return exec_globals, _locals


def get_safe_globals():
	datautils = vmraid._dict()

	if vmraid.db:
		date_format = vmraid.db.get_default("date_format") or "yyyy-mm-dd"
		time_format = vmraid.db.get_default("time_format") or "HH:mm:ss"
	else:
		date_format = "yyyy-mm-dd"
		time_format = "HH:mm:ss"

	add_data_utils(datautils)

	form_dict = getattr(vmraid.local, "form_dict", vmraid._dict())

	if "_" in form_dict:
		del vmraid.local.form_dict["_"]

	user = getattr(vmraid.local, "session", None) and vmraid.local.session.user or "Guest"

	out = NamespaceDict(
		# make available limited methods of vmraid
		json=NamespaceDict(loads=json.loads, dumps=json.dumps),
		as_json=vmraid.as_json,
		dict=dict,
		log=vmraid.log,
		_dict=vmraid._dict,
		args=form_dict,
		vmraid=NamespaceDict(
			call=call_whitelisted_function,
			flags=vmraid._dict(),
			format=vmraid.format_value,
			format_value=vmraid.format_value,
			date_format=date_format,
			time_format=time_format,
			format_date=vmraid.utils.data.global_date_format,
			form_dict=form_dict,
			bold=vmraid.bold,
			copy_doc=vmraid.copy_doc,
			errprint=vmraid.errprint,
			qb=vmraid.qb,
			get_meta=vmraid.get_meta,
			get_doc=vmraid.get_doc,
			get_cached_doc=vmraid.get_cached_doc,
			get_list=vmraid.get_list,
			get_all=vmraid.get_all,
			get_system_settings=vmraid.get_system_settings,
			rename_doc=vmraid.rename_doc,
			utils=datautils,
			get_url=vmraid.utils.get_url,
			render_template=vmraid.render_template,
			msgprint=vmraid.msgprint,
			throw=vmraid.throw,
			sendmail=vmraid.sendmail,
			get_print=vmraid.get_print,
			attach_print=vmraid.attach_print,
			user=user,
			get_fullname=vmraid.utils.get_fullname,
			get_gravatar=vmraid.utils.get_gravatar_url,
			full_name=vmraid.local.session.data.full_name
			if getattr(vmraid.local, "session", None)
			else "Guest",
			request=getattr(vmraid.local, "request", {}),
			session=vmraid._dict(
				user=user,
				csrf_token=vmraid.local.session.data.csrf_token
				if getattr(vmraid.local, "session", None)
				else "",
			),
			make_get_request=vmraid.integrations.utils.make_get_request,
			make_post_request=vmraid.integrations.utils.make_post_request,
			socketio_port=vmraid.conf.socketio_port,
			get_hooks=get_hooks,
			enqueue=safe_enqueue,
			sanitize_html=vmraid.utils.sanitize_html,
			log_error=vmraid.log_error,
			db=NamespaceDict(
				get_list=vmraid.get_list,
				get_all=vmraid.get_all,
				get_value=vmraid.db.get_value,
				set_value=vmraid.db.set_value,
				get_single_value=vmraid.db.get_single_value,
				get_default=vmraid.db.get_default,
				exists=vmraid.db.exists,
				count=vmraid.db.count,
				escape=vmraid.db.escape,
				sql=read_sql,
				commit=vmraid.db.commit,
				rollback=vmraid.db.rollback,
				add_index=vmraid.db.add_index,
			),
		),
		VMRaidClient=VMRaidClient,
		style=vmraid._dict(border_color="#d1d8dd"),
		get_toc=get_toc,
		get_next_link=get_next_link,
		_=vmraid._,
		get_shade=get_shade,
		scrub=scrub,
		guess_mimetype=mimetypes.guess_type,
		html2text=html2text,
		dev_server=1 if vmraid._dev_server else 0,
		run_script=run_script,
		is_job_queued=is_job_queued,
		get_visible_columns=get_visible_columns,
	)

	add_module_properties(
		vmraid.exceptions, out.vmraid, lambda obj: inspect.isclass(obj) and issubclass(obj, Exception)
	)

	if vmraid.response:
		out.vmraid.response = vmraid.response

	out.update(safe_globals)

	# default writer allows write access
	out._write_ = _write
	out._getitem_ = _getitem
	out._getattr_ = _getattr

	# allow iterators and list comprehension
	out._getiter_ = iter
	out._iter_unpack_sequence_ = RestrictedPython.Guards.guarded_iter_unpack_sequence

	# add common python builtins
	out.update(get_python_builtins())

	return out


def is_job_queued(job_name, queue="default"):
	"""
	:param job_name: used to identify a queued job, usually dotted path to function
	:param queue: should be either long, default or short
	"""

	site = vmraid.local.site
	queued_jobs = get_jobs(site=site, queue=queue, key="job_name").get(site)
	return queued_jobs and job_name in queued_jobs


def safe_enqueue(function, **kwargs):
	"""
	Enqueue function to be executed using a background worker
	Accepts vmraid.enqueue params like job_name, queue, timeout, etc.
	in addition to params to be passed to function

	:param function: whitelised function or API Method set in Server Script
	"""

	return enqueue("vmraid.utils.safe_exec.call_whitelisted_function", function=function, **kwargs)


def call_whitelisted_function(function, **kwargs):
	"""Executes a whitelisted function or Server Script of type API"""

	return call_with_form_dict(lambda: execute_cmd(function), kwargs)


def run_script(script, **kwargs):
	"""run another server script"""

	return call_with_form_dict(
		lambda: vmraid.get_doc("Server Script", script).execute_method(), kwargs
	)


def call_with_form_dict(function, kwargs):
	# temporarily update form_dict, to use inside below call
	form_dict = getattr(vmraid.local, "form_dict", vmraid._dict())
	if kwargs:
		vmraid.local.form_dict = form_dict.copy().update(kwargs)

	try:
		return function()
	finally:
		vmraid.local.form_dict = form_dict


def get_python_builtins():
	return {
		"abs": abs,
		"all": all,
		"any": any,
		"bool": bool,
		"dict": dict,
		"enumerate": enumerate,
		"isinstance": isinstance,
		"issubclass": issubclass,
		"list": list,
		"max": max,
		"min": min,
		"range": range,
		"set": set,
		"sorted": sorted,
		"sum": sum,
		"tuple": tuple,
	}


def get_hooks(hook=None, default=None, app_name=None):
	hooks = vmraid.get_hooks(hook=hook, default=default, app_name=app_name)
	return copy.deepcopy(hooks)


def read_sql(query, *args, **kwargs):
	"""a wrapper for vmraid.db.sql to allow reads"""
	query = str(query)
	if vmraid.flags.in_safe_exec:
		check_safe_sql_query(query)
	return vmraid.db.sql(query, *args, **kwargs)


def check_safe_sql_query(query: str, throw: bool = True) -> bool:
	"""Check if SQL query is safe for running in restricted context.

	Safe queries:
	        1. Read only 'select' or 'explain' queries
	        2. CTE on mariadb where writes are not allowed.
	"""

	query = query.strip().lower()
	whitelisted_statements = ("select", "explain")

	if query.startswith(whitelisted_statements) or (
		query.startswith("with") and vmraid.db.db_type == "mariadb"
	):
		return True

	if throw:
		vmraid.throw(
			_("Query must be of SELECT or read-only WITH type."),
			title=_("Unsafe SQL query"),
			exc=vmraid.PermissionError,
		)

	return False


def _getitem(obj, key):
	# guard function for RestrictedPython
	# allow any key to be accessed as long as it does not start with underscore
	if isinstance(key, str) and key.startswith("_"):
		raise SyntaxError("Key starts with _")
	return obj[key]


def _getattr(object, name, default=None):
	# guard function for RestrictedPython
	# allow any key to be accessed as long as
	# 1. it does not start with an underscore (safer_getattr)
	# 2. it is not an UNSAFE_ATTRIBUTES

	UNSAFE_ATTRIBUTES = {
		# Generator Attributes
		"gi_frame",
		"gi_code",
		# Coroutine Attributes
		"cr_frame",
		"cr_code",
		"cr_origin",
		# Async Generator Attributes
		"ag_code",
		"ag_frame",
		# Traceback Attributes
		"tb_frame",
		"tb_next",
	}

	if isinstance(name, str) and (name in UNSAFE_ATTRIBUTES):
		raise SyntaxError("{name} is an unsafe attribute".format(name=name))
	return RestrictedPython.Guards.safer_getattr(object, name, default=default)


def _write(obj):
	# guard function for RestrictedPython
	# allow writing to any object
	return obj


def add_data_utils(data):
	for key, obj in vmraid.utils.data.__dict__.items():
		if key in VALID_UTILS:
			data[key] = obj


def add_module_properties(module, data, filter_method):
	for key, obj in module.__dict__.items():
		if key.startswith("_"):
			# ignore
			continue

		if filter_method(obj):
			# only allow functions
			data[key] = obj


VALID_UTILS = (
	"DATE_FORMAT",
	"TIME_FORMAT",
	"DATETIME_FORMAT",
	"is_invalid_date_string",
	"getdate",
	"get_datetime",
	"to_timedelta",
	"get_timedelta",
	"add_to_date",
	"add_days",
	"add_months",
	"add_years",
	"date_diff",
	"month_diff",
	"time_diff",
	"time_diff_in_seconds",
	"time_diff_in_hours",
	"now_datetime",
	"get_timestamp",
	"get_eta",
	"get_time_zone",
	"convert_utc_to_user_timezone",
	"now",
	"nowdate",
	"today",
	"nowtime",
	"get_first_day",
	"get_quarter_start",
	"get_first_day_of_week",
	"get_year_start",
	"get_last_day_of_week",
	"get_last_day",
	"get_time",
	"get_datetime_in_timezone",
	"get_datetime_str",
	"get_date_str",
	"get_time_str",
	"get_user_date_format",
	"get_user_time_format",
	"format_date",
	"format_time",
	"format_datetime",
	"format_duration",
	"get_weekdays",
	"get_weekday",
	"get_timespan_date_range",
	"global_date_format",
	"has_common",
	"flt",
	"cint",
	"floor",
	"ceil",
	"cstr",
	"rounded",
	"remainder",
	"safe_div",
	"round_based_on_smallest_currency_fraction",
	"encode",
	"parse_val",
	"fmt_money",
	"get_number_format_info",
	"money_in_words",
	"in_words",
	"is_html",
	"is_image",
	"get_thumbnail_base64_for_image",
	"image_to_base64",
	"pdf_to_base64",
	"strip_html",
	"escape_html",
	"pretty_date",
	"comma_or",
	"comma_and",
	"comma_sep",
	"new_line_sep",
	"filter_strip_join",
	"get_url",
	"get_host_name_from_request",
	"url_contains_port",
	"get_host_name",
	"get_link_to_form",
	"get_link_to_report",
	"get_absolute_url",
	"get_url_to_form",
	"get_url_to_list",
	"get_url_to_report",
	"get_url_to_report_with_filters",
	"evaluate_filters",
	"compare",
	"get_filter",
	"make_filter_tuple",
	"make_filter_dict",
	"sanitize_column",
	"scrub_urls",
	"expand_relative_urls",
	"quoted",
	"quote_urls",
	"unique",
	"strip",
	"to_markdown",
	"md_to_html",
	"markdown",
	"is_subset",
	"generate_hash",
	"formatdate",
	"get_user_info_for_avatar",
	"get_abbr",
)
