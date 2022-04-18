# Copyright (c) 2022, VMRaid and Contributors
# License: MIT. See LICENSE
import datetime
import json

import vmraid
from vmraid import _
from vmraid.model import child_table_fields, default_fields, display_fieldtypes, table_fields
from vmraid.model.docstatus import DocStatus
from vmraid.model.naming import set_new_name
from vmraid.model.utils.link_count import notify_link_count
from vmraid.modules import load_doctype_module
from vmraid.utils import cast_fieldtype, cint, cstr, flt, now, sanitize_html, strip_html
from vmraid.utils.html_utils import unescape_html

max_positive_value = {"smallint": 2**15, "int": 2**31, "bigint": 2**63}

DOCTYPES_FOR_DOCTYPE = ("DocType", "DocField", "DocPerm", "DocType Action", "DocType Link")


def get_controller(doctype):
	"""Returns the **class** object of the given DocType.
	For `custom` type, returns `vmraid.model.document.Document`.

	:param doctype: DocType name as string."""

	def _get_controller():
		from vmraid.model.document import Document
		from vmraid.utils.nestedset import NestedSet

		module_name, custom = vmraid.db.get_value(
			"DocType", doctype, ("module", "custom"), cache=True
		) or ("Core", False)

		if custom:
			is_tree = vmraid.db.get_value("DocType", doctype, "is_tree", ignore=True, cache=True)
			_class = NestedSet if is_tree else Document
		else:
			class_overrides = vmraid.get_hooks("override_doctype_class")
			if class_overrides and class_overrides.get(doctype):
				import_path = class_overrides[doctype][-1]
				module_path, classname = import_path.rsplit(".", 1)
				module = vmraid.get_module(module_path)
				if not hasattr(module, classname):
					raise ImportError(
						"{0}: {1} does not exist in module {2}".format(doctype, classname, module_path)
					)
			else:
				module = load_doctype_module(doctype, module_name)
				classname = doctype.replace(" ", "").replace("-", "")

			if hasattr(module, classname):
				_class = getattr(module, classname)
				if issubclass(_class, BaseDocument):
					_class = getattr(module, classname)
				else:
					raise ImportError(doctype)
			else:
				raise ImportError(doctype)
		return _class

	if vmraid.local.dev_server:
		return _get_controller()

	site_controllers = vmraid.controllers.setdefault(vmraid.local.site, {})
	if doctype not in site_controllers:
		site_controllers[doctype] = _get_controller()

	return site_controllers[doctype]


class BaseDocument(object):
	ignore_in_setter = ("doctype", "_meta", "meta", "_table_fields", "_valid_columns")

	def __init__(self, d):
		if d.get("doctype"):
			self.doctype = d["doctype"]

		self.update(d)
		self.dont_update_if_missing = []

		if hasattr(self, "__setup__"):
			self.__setup__()

	@property
	def meta(self):
		if not getattr(self, "_meta", None):
			self._meta = vmraid.get_meta(self.doctype)

		return self._meta

	def __getstate__(self):
		self._meta = None
		return self.__dict__

	def update(self, d):
		"""Update multiple fields of a doctype using a dictionary of key-value pairs.

		Example:
		        doc.update({
		                "user": "admin",
		                "balance": 42000
		        })
		"""

		# set name first, as it is used a reference in child document
		if "name" in d:
			self.name = d["name"]

		for key, value in d.items():
			self.set(key, value)

		return self

	def update_if_missing(self, d):
		"""Set default values for fields without existing values"""
		if isinstance(d, BaseDocument):
			d = d.get_valid_dict()

		for key, value in d.items():
			if (
				value is not None
				and self.get(key) is None
				# dont_update_if_missing is a list of fieldnames
				# for which you don't want to set default value
				and key not in self.dont_update_if_missing
			):
				self.set(key, value)

	def get_db_value(self, key):
		return vmraid.db.get_value(self.doctype, self.name, key)

	def get(self, key, filters=None, limit=None, default=None):
		if isinstance(key, dict):
			return _filter(self.get_all_children(), key, limit=limit)

		if filters:
			if isinstance(filters, dict):
				value = _filter(self.__dict__.get(key, []), filters, limit=limit)
			else:
				default = filters
				filters = None
				value = self.__dict__.get(key, default)
		else:
			value = self.__dict__.get(key, default)

		if value is None and key in (d.fieldname for d in self.meta.get_table_fields()):
			value = []
			self.set(key, value)

		if limit and isinstance(value, (list, tuple)) and len(value) > limit:
			value = value[:limit]

		return value

	def getone(self, key, filters=None):
		return self.get(key, filters=filters, limit=1)[0]

	def set(self, key, value, as_value=False):
		if key in self.ignore_in_setter:
			return

		if isinstance(value, list) and not as_value:
			self.__dict__[key] = []
			self.extend(key, value)
		else:
			self.__dict__[key] = value

	def delete_key(self, key):
		if key in self.__dict__:
			del self.__dict__[key]

	def append(self, key, value=None):
		"""Append an item to a child table.

		Example:
		        doc.append("childtable", {
		                "child_table_field": "value",
		                "child_table_int_field": 0,
		                ...
		        })
		"""
		if value is None:
			value = {}
		if isinstance(value, (dict, BaseDocument)):
			if not self.__dict__.get(key):
				self.__dict__[key] = []

			value = self._init_child(value, key)
			self.__dict__[key].append(value)

			# reference parent document
			value.parent_doc = self

			return value
		else:

			# metaclasses may have arbitrary lists
			# which we can ignore
			if getattr(self, "_metaclass", None) or self.__class__.__name__ in (
				"Meta",
				"FormMeta",
				"DocField",
			):
				return value

			raise ValueError(
				'Document for field "{0}" attached to child table of "{1}" must be a dict or BaseDocument, not {2} ({3})'.format(
					key, self.name, str(type(value))[1:-1], value
				)
			)

	def extend(self, key, value):
		if isinstance(value, list):
			for v in value:
				self.append(key, v)
		else:
			raise ValueError

	def remove(self, doc):
		# Usage: from the parent doc, pass the child table doc
		# to remove that child doc from the child table, thus removing it from the parent doc
		if doc.get("parentfield"):
			self.get(doc.parentfield).remove(doc)

	def _init_child(self, value, key):
		if not self.doctype:
			return value

		if not isinstance(value, BaseDocument):
			value["doctype"] = self.get_table_field_doctype(key)
			if not value["doctype"]:
				raise AttributeError(key)

			value = get_controller(value["doctype"])(value)
			value.init_valid_columns()

		value.parent = self.name
		value.parenttype = self.doctype
		value.parentfield = key

		if value.docstatus is None:
			value.docstatus = DocStatus.draft()

		if not getattr(value, "idx", None):
			value.idx = len(self.get(key) or []) + 1

		if not getattr(value, "name", None):
			value.__dict__["__islocal"] = 1

		return value

	def get_valid_dict(
		self, sanitize=True, convert_dates_to_str=False, ignore_nulls=False, ignore_virtual=False
	):
		d = vmraid._dict()
		for fieldname in self.meta.get_valid_columns():
			d[fieldname] = self.get(fieldname)

			# if no need for sanitization and value is None, continue
			if not sanitize and d[fieldname] is None:
				continue

			df = self.meta.get_field(fieldname)

			if df and df.get("is_virtual"):
				if ignore_virtual:
					del d[fieldname]
					continue

				from vmraid.utils.safe_exec import get_safe_globals

				if d[fieldname] is None:
					if df.get("options"):
						d[fieldname] = vmraid.safe_eval(
							code=df.get("options"),
							eval_globals=get_safe_globals(),
							eval_locals={"doc": self},
						)
					else:
						_val = getattr(self, fieldname, None)
						if _val and not callable(_val):
							d[fieldname] = _val
			elif df:
				if df.fieldtype == "Check":
					d[fieldname] = 1 if cint(d[fieldname]) else 0

				elif df.fieldtype == "Int" and not isinstance(d[fieldname], int):
					d[fieldname] = cint(d[fieldname])

				elif df.fieldtype == "JSON" and isinstance(d[fieldname], dict):
					d[fieldname] = json.dumps(d[fieldname], sort_keys=True, indent=4, separators=(",", ": "))

				elif df.fieldtype in ("Currency", "Float", "Percent") and not isinstance(d[fieldname], float):
					d[fieldname] = flt(d[fieldname])

				elif df.fieldtype in ("Datetime", "Date", "Time") and d[fieldname] == "":
					d[fieldname] = None

				elif df.get("unique") and cstr(d[fieldname]).strip() == "":
					# unique empty field should be set to None
					d[fieldname] = None

				if isinstance(d[fieldname], list) and df.fieldtype not in table_fields:
					vmraid.throw(_("Value for {0} cannot be a list").format(_(df.label)))

			if convert_dates_to_str and isinstance(
				d[fieldname], (datetime.datetime, datetime.date, datetime.time, datetime.timedelta)
			):
				d[fieldname] = str(d[fieldname])

			if d[fieldname] is None and ignore_nulls:
				del d[fieldname]

		return d

	def init_valid_columns(self):
		for key in default_fields:
			if key not in self.__dict__:
				self.__dict__[key] = None

			if self.__dict__[key] is None:
				if key == "docstatus":
					self.docstatus = DocStatus.draft()
				elif key == "idx":
					self.__dict__[key] = 0

		for key in self.get_valid_columns():
			if key not in self.__dict__:
				self.__dict__[key] = None

	def get_valid_columns(self):
		if self.doctype not in vmraid.local.valid_columns:
			if self.doctype in DOCTYPES_FOR_DOCTYPE:
				from vmraid.model.meta import get_table_columns

				valid = get_table_columns(self.doctype)
			else:
				valid = self.meta.get_valid_columns()

			vmraid.local.valid_columns[self.doctype] = valid

		return vmraid.local.valid_columns[self.doctype]

	def is_new(self):
		return self.get("__islocal")

	@property
	def docstatus(self):
		return DocStatus(self.get("docstatus"))

	@docstatus.setter
	def docstatus(self, value):
		self.__dict__["docstatus"] = DocStatus(cint(value))

	def as_dict(
		self,
		no_nulls=False,
		no_default_fields=False,
		convert_dates_to_str=False,
		no_child_table_fields=False,
	):
		doc = self.get_valid_dict(convert_dates_to_str=convert_dates_to_str)
		doc["doctype"] = self.doctype

		for df in self.meta.get_table_fields():
			children = self.get(df.fieldname) or []
			doc[df.fieldname] = [
				d.as_dict(
					convert_dates_to_str=convert_dates_to_str,
					no_nulls=no_nulls,
					no_default_fields=no_default_fields,
					no_child_table_fields=no_child_table_fields,
				)
				for d in children
			]

		if no_nulls:
			for k in list(doc):
				if doc[k] is None:
					del doc[k]

		if no_default_fields:
			for k in list(doc):
				if k in default_fields:
					del doc[k]

		if no_child_table_fields:
			for k in list(doc):
				if k in child_table_fields:
					del doc[k]

		for key in (
			"_user_tags",
			"__islocal",
			"__onload",
			"_liked_by",
			"__run_link_triggers",
			"__unsaved",
		):
			if self.get(key):
				doc[key] = self.get(key)

		return doc

	def as_json(self):
		return vmraid.as_json(self.as_dict())

	def get_table_field_doctype(self, fieldname):
		try:
			return self.meta.get_field(fieldname).options
		except AttributeError:
			if self.doctype == "DocType":
				return dict(links="DocType Link", actions="DocType Action", states="DocType State").get(
					fieldname
				)
			raise

	def get_parentfield_of_doctype(self, doctype):
		fieldname = [df.fieldname for df in self.meta.get_table_fields() if df.options == doctype]
		return fieldname[0] if fieldname else None

	def db_insert(self, ignore_if_duplicate=False):
		"""INSERT the document (with valid columns) in the database.

		args:
		        ignore_if_duplicate: ignore primary key collision
		                                        at database level (postgres)
		                                        in python (mariadb)
		"""
		if not self.name:
			# name will be set by document class in most cases
			set_new_name(self)

		conflict_handler = ""
		# On postgres we can't implcitly ignore PK collision
		# So instruct pg to ignore `name` field conflicts
		if ignore_if_duplicate and vmraid.db.db_type == "postgres":
			conflict_handler = "on conflict (name) do nothing"

		if not self.creation:
			self.creation = self.modified = now()
			self.created_by = self.modified_by = vmraid.session.user

		# if doctype is "DocType", don't insert null values as we don't know who is valid yet
		d = self.get_valid_dict(
			convert_dates_to_str=True,
			ignore_nulls=self.doctype in DOCTYPES_FOR_DOCTYPE,
			ignore_virtual=True,
		)

		columns = list(d)
		try:
			vmraid.db.sql(
				"""INSERT INTO `tab{doctype}` ({columns})
					VALUES ({values}) {conflict_handler}""".format(
					doctype=self.doctype,
					columns=", ".join("`" + c + "`" for c in columns),
					values=", ".join(["%s"] * len(columns)),
					conflict_handler=conflict_handler,
				),
				list(d.values()),
			)
		except Exception as e:
			if vmraid.db.is_primary_key_violation(e):
				if self.meta.autoname == "hash":
					# hash collision? try again
					vmraid.flags.retry_count = (vmraid.flags.retry_count or 0) + 1
					if vmraid.flags.retry_count > 5 and not vmraid.flags.in_test:
						raise
					self.name = None
					self.db_insert()
					return

				if not ignore_if_duplicate:
					vmraid.msgprint(
						_("{0} {1} already exists").format(self.doctype, vmraid.bold(self.name)),
						title=_("Duplicate Name"),
						indicator="red",
					)
					raise vmraid.DuplicateEntryError(self.doctype, self.name, e)

			elif vmraid.db.is_unique_key_violation(e):
				# unique constraint
				self.show_unique_validation_message(e)

			else:
				raise

		self.set("__islocal", False)

	def db_update(self):
		if self.get("__islocal") or not self.name:
			self.db_insert()
			return

		d = self.get_valid_dict(
			convert_dates_to_str=True, ignore_nulls=self.doctype in DOCTYPES_FOR_DOCTYPE
		)

		# don't update name, as case might've been changed
		name = cstr(d["name"])
		del d["name"]

		columns = list(d)

		try:
			vmraid.db.sql(
				"""UPDATE `tab{doctype}`
				SET {values} WHERE `name`=%s""".format(
					doctype=self.doctype, values=", ".join("`" + c + "`=%s" for c in columns)
				),
				list(d.values()) + [name],
			)
		except Exception as e:
			if vmraid.db.is_unique_key_violation(e):
				self.show_unique_validation_message(e)
			else:
				raise

	def db_update_all(self):
		"""Raw update parent + children
		DOES NOT VALIDATE AND CALL TRIGGERS"""
		self.db_update()
		for df in self.meta.get_table_fields():
			for doc in self.get(df.fieldname):
				doc.db_update()

	def show_unique_validation_message(self, e):
		if vmraid.db.db_type != "postgres":
			fieldname = str(e).split("'")[-2]
			label = None

			# MariaDB gives key_name in error. Extracting fieldname from key name
			try:
				fieldname = self.get_field_name_by_key_name(fieldname)
			except IndexError:
				pass

			label = self.get_label_from_fieldname(fieldname)

			vmraid.msgprint(_("{0} must be unique").format(label or fieldname))

		# this is used to preserve traceback
		raise vmraid.UniqueValidationError(self.doctype, self.name, e)

	def get_field_name_by_key_name(self, key_name):
		"""MariaDB stores a mapping between `key_name` and `column_name`.
		This function returns the `column_name` associated with the `key_name` passed

		Args:
		        key_name (str): The name of the database index.

		Raises:
		        IndexError: If the key is not found in the table.

		Returns:
		        str: The column name associated with the key.
		"""
		return vmraid.db.sql(
			f"""
			SHOW
				INDEX
			FROM
				`tab{self.doctype}`
			WHERE
				key_name=%s
			AND
				Non_unique=0
			""",
			key_name,
			as_dict=True,
		)[0].get("Column_name")

	def get_label_from_fieldname(self, fieldname):
		"""Returns the associated label for fieldname

		Args:
		        fieldname (str): The fieldname in the DocType to use to pull the label.

		Returns:
		        str: The label associated with the fieldname, if found, otherwise `None`.
		"""
		df = self.meta.get_field(fieldname)
		if df:
			return df.label

	def update_modified(self):
		"""Update modified timestamp"""
		self.set("modified", now())
		vmraid.db.set_value(self.doctype, self.name, "modified", self.modified, update_modified=False)

	def _fix_numeric_types(self):
		for df in self.meta.get("fields"):
			if df.fieldtype == "Check":
				self.set(df.fieldname, cint(self.get(df.fieldname)))

			elif self.get(df.fieldname) is not None:
				if df.fieldtype == "Int":
					self.set(df.fieldname, cint(self.get(df.fieldname)))

				elif df.fieldtype in ("Float", "Currency", "Percent"):
					self.set(df.fieldname, flt(self.get(df.fieldname)))

		if self.docstatus is not None:
			self.docstatus = DocStatus(cint(self.docstatus))

	def _get_missing_mandatory_fields(self):
		"""Get mandatory fields that do not have any values"""

		def get_msg(df):
			if df.fieldtype in table_fields:
				return "{}: {}: {}".format(_("Error"), _("Data missing in table"), _(df.label))

			# check if parentfield exists (only applicable for child table doctype)
			elif self.get("parentfield"):
				return "{}: {} {} #{}: {}: {}".format(
					_("Error"),
					vmraid.bold(_(self.doctype)),
					_("Row"),
					self.idx,
					_("Value missing for"),
					_(df.label),
				)

			return _("Error: Value missing for {0}: {1}").format(_(df.parent), _(df.label))

		missing = []

		for df in self.meta.get("fields", {"reqd": ("=", 1)}):
			if self.get(df.fieldname) in (None, []) or not strip_html(cstr(self.get(df.fieldname))).strip():
				missing.append((df.fieldname, get_msg(df)))

		# check for missing parent and parenttype
		if self.meta.istable:
			for fieldname in ("parent", "parenttype"):
				if not self.get(fieldname):
					missing.append((fieldname, get_msg(vmraid._dict(label=fieldname))))

		return missing

	def get_invalid_links(self, is_submittable=False):
		"""Returns list of invalid links and also updates fetch values if not set"""

		def get_msg(df, docname):
			# check if parentfield exists (only applicable for child table doctype)
			if self.get("parentfield"):
				return "{} #{}: {}: {}".format(_("Row"), self.idx, _(df.label), docname)

			return "{}: {}".format(_(df.label), docname)

		invalid_links = []
		cancelled_links = []

		for df in self.meta.get_link_fields() + self.meta.get(
			"fields", {"fieldtype": ("=", "Dynamic Link")}
		):
			docname = self.get(df.fieldname)

			if docname:
				if df.fieldtype == "Link":
					doctype = df.options
					if not doctype:
						vmraid.throw(_("Options not set for link field {0}").format(df.fieldname))
				else:
					doctype = self.get(df.options)
					if not doctype:
						vmraid.throw(_("{0} must be set first").format(self.meta.get_label(df.options)))

				# MySQL is case insensitive. Preserve case of the original docname in the Link Field.

				# get a map of values ot fetch along with this link query
				# that are mapped as link_fieldname.source_fieldname in Options of
				# Readonly or Data or Text type fields

				fields_to_fetch = [
					_df
					for _df in self.meta.get_fields_to_fetch(df.fieldname)
					if not _df.get("fetch_if_empty")
					or (_df.get("fetch_if_empty") and not self.get(_df.fieldname))
				]
				if not vmraid.get_meta(doctype).get("is_virtual"):
					if not fields_to_fetch:
						# cache a single value type
						values = vmraid._dict(name=vmraid.db.get_value(doctype, docname, "name", cache=True))
					else:
						values_to_fetch = ["name"] + [_df.fetch_from.split(".")[-1] for _df in fields_to_fetch]

						# don't cache if fetching other values too
						values = vmraid.db.get_value(doctype, docname, values_to_fetch, as_dict=True)

				if vmraid.get_meta(doctype).issingle:
					values.name = doctype

				if vmraid.get_meta(doctype).get("is_virtual"):
					values = vmraid.get_doc(doctype, docname)

				if values:
					setattr(self, df.fieldname, values.name)

					for _df in fields_to_fetch:
						if self.is_new() or not self.docstatus.is_submitted() or _df.allow_on_submit:
							self.set_fetch_from_value(doctype, _df, values)

					notify_link_count(doctype, docname)

					if not values.name:
						invalid_links.append((df.fieldname, docname, get_msg(df, docname)))

					elif (
						df.fieldname != "amended_from"
						and (is_submittable or self.meta.is_submittable)
						and vmraid.get_meta(doctype).is_submittable
						and cint(vmraid.db.get_value(doctype, docname, "docstatus")) == DocStatus.cancelled()
					):

						cancelled_links.append((df.fieldname, docname, get_msg(df, docname)))

		return invalid_links, cancelled_links

	def set_fetch_from_value(self, doctype, df, values):
		fetch_from_fieldname = df.fetch_from.split(".")[-1]
		value = values[fetch_from_fieldname]
		if df.fieldtype in ["Small Text", "Text", "Data"]:
			from vmraid.model.meta import get_default_df

			fetch_from_df = get_default_df(fetch_from_fieldname) or vmraid.get_meta(doctype).get_field(
				fetch_from_fieldname
			)

			if not fetch_from_df:
				vmraid.throw(
					_('Please check the value of "Fetch From" set for field {0}').format(vmraid.bold(df.label)),
					title=_("Wrong Fetch From value"),
				)

			fetch_from_ft = fetch_from_df.get("fieldtype")
			if fetch_from_ft == "Text Editor" and value:
				value = unescape_html(strip_html(value))
		setattr(self, df.fieldname, value)

	def _validate_selects(self):
		if vmraid.flags.in_import:
			return

		for df in self.meta.get_select_fields():
			if df.fieldname == "naming_series" or not (self.get(df.fieldname) and df.options):
				continue

			options = (df.options or "").split("\n")

			# if only empty options
			if not filter(None, options):
				continue

			# strip and set
			self.set(df.fieldname, cstr(self.get(df.fieldname)).strip())
			value = self.get(df.fieldname)

			if value not in options and not (vmraid.flags.in_test and value.startswith("_T-")):
				# show an elaborate message
				prefix = _("Row #{0}:").format(self.idx) if self.get("parentfield") else ""
				label = _(self.meta.get_label(df.fieldname))
				comma_options = '", "'.join(_(each) for each in options)

				vmraid.throw(
					_('{0} {1} cannot be "{2}". It should be one of "{3}"').format(
						prefix, label, value, comma_options
					)
				)

	def _validate_data_fields(self):
		# data_field options defined in vmraid.model.data_field_options
		for data_field in self.meta.get_data_fields():
			data = self.get(data_field.fieldname)
			data_field_options = data_field.get("options")
			old_fieldtype = data_field.get("oldfieldtype")

			if old_fieldtype and old_fieldtype != "Data":
				continue

			if data_field_options == "Email":
				if (self.owner in vmraid.STANDARD_USERS) and (data in vmraid.STANDARD_USERS):
					continue
				for email_address in vmraid.utils.split_emails(data):
					vmraid.utils.validate_email_address(email_address, throw=True)

			if data_field_options == "Name":
				vmraid.utils.validate_name(data, throw=True)

			if data_field_options == "Phone":
				vmraid.utils.validate_phone_number(data, throw=True)

			if data_field_options == "URL":
				if not data:
					continue

				vmraid.utils.validate_url(data, throw=True)

	def _validate_constants(self):
		if vmraid.flags.in_import or self.is_new() or self.flags.ignore_validate_constants:
			return

		constants = [d.fieldname for d in self.meta.get("fields", {"set_only_once": ("=", 1)})]
		if constants:
			values = vmraid.db.get_value(self.doctype, self.name, constants, as_dict=True)

		for fieldname in constants:
			df = self.meta.get_field(fieldname)

			# This conversion to string only when fieldtype is Date
			if df.fieldtype == "Date" or df.fieldtype == "Datetime":
				value = str(values.get(fieldname))

			else:
				value = values.get(fieldname)

			if self.get(fieldname) != value:
				vmraid.throw(
					_("Value cannot be changed for {0}").format(self.meta.get_label(fieldname)),
					vmraid.CannotChangeConstantError,
				)

	def _validate_length(self):
		if vmraid.flags.in_install:
			return

		if self.meta.issingle:
			# single doctype value type is mediumtext
			return

		type_map = vmraid.db.type_map

		for fieldname, value in self.get_valid_dict(ignore_virtual=True).items():
			df = self.meta.get_field(fieldname)

			if not df or df.fieldtype == "Check":
				# skip standard fields and Check fields
				continue

			column_type = type_map[df.fieldtype][0] or None

			if column_type == "varchar":
				default_column_max_length = type_map[df.fieldtype][1] or None
				max_length = cint(df.get("length")) or cint(default_column_max_length)

				if len(cstr(value)) > max_length:
					self.throw_length_exceeded_error(df, max_length, value)

			elif column_type in ("int", "bigint", "smallint"):
				max_length = max_positive_value[column_type]

				if abs(cint(value)) > max_length:
					self.throw_length_exceeded_error(df, max_length, value)

	def _validate_code_fields(self):
		for field in self.meta.get_code_fields():
			code_string = self.get(field.fieldname)
			language = field.get("options")

			if language == "Python":
				vmraid.utils.validate_python_code(code_string, fieldname=field.label, is_expression=False)

			elif language == "PythonExpression":
				vmraid.utils.validate_python_code(code_string, fieldname=field.label)

	def _sync_autoname_field(self):
		"""Keep autoname field in sync with `name`"""
		autoname = self.meta.autoname or ""
		_empty, _field_specifier, fieldname = autoname.partition("field:")

		if fieldname and self.name and self.name != self.get(fieldname):
			self.set(fieldname, self.name)

	def throw_length_exceeded_error(self, df, max_length, value):
		# check if parentfield exists (only applicable for child table doctype)
		if self.get("parentfield"):
			reference = _("{0}, Row {1}").format(_(self.doctype), self.idx)
		else:
			reference = "{0} {1}".format(_(self.doctype), self.name)

		vmraid.throw(
			_("{0}: '{1}' ({3}) will get truncated, as max characters allowed is {2}").format(
				reference, _(df.label), max_length, value
			),
			vmraid.CharacterLengthExceededError,
			title=_("Value too big"),
		)

	def _validate_update_after_submit(self):
		# get the full doc with children
		db_values = vmraid.get_doc(self.doctype, self.name).as_dict()

		for key in self.as_dict():
			df = self.meta.get_field(key)
			db_value = db_values.get(key)

			if df and not df.allow_on_submit and (self.get(key) or db_value):
				if df.fieldtype in table_fields:
					# just check if the table size has changed
					# individual fields will be checked in the loop for children
					self_value = len(self.get(key))
					db_value = len(db_value)

				else:
					self_value = self.get_value(key)
				# Postgres stores values as `datetime.time`, MariaDB as `timedelta`
				if isinstance(self_value, datetime.timedelta) and isinstance(db_value, datetime.time):
					db_value = datetime.timedelta(
						hours=db_value.hour,
						minutes=db_value.minute,
						seconds=db_value.second,
						microseconds=db_value.microsecond,
					)
				if self_value != db_value:
					vmraid.throw(
						_("Not allowed to change {0} after submission").format(df.label),
						vmraid.UpdateAfterSubmitError,
					)

	def _sanitize_content(self):
		"""Sanitize HTML and Email in field values. Used to prevent XSS.

		- Ignore if 'Ignore XSS Filter' is checked or fieldtype is 'Code'
		"""
		from bs4 import BeautifulSoup

		if vmraid.flags.in_install:
			return

		for fieldname, value in self.get_valid_dict(ignore_virtual=True).items():
			if not value or not isinstance(value, str):
				continue

			value = vmraid.as_unicode(value)

			if "<" not in value and ">" not in value:
				# doesn't look like html so no need
				continue

			elif "<!-- markdown -->" in value and not bool(BeautifulSoup(value, "html.parser").find()):
				# should be handled separately via the markdown converter function
				continue

			df = self.meta.get_field(fieldname)
			sanitized_value = value

			if df and (
				df.get("ignore_xss_filter")
				or (df.get("fieldtype") in ("Data", "Small Text", "Text") and df.get("options") == "Email")
				or df.get("fieldtype") in ("Attach", "Attach Image", "Barcode", "Code")
				# cancelled and submit but not update after submit should be ignored
				or self.docstatus.is_cancelled()
				or (self.docstatus.is_submitted() and not df.get("allow_on_submit"))
			):
				continue

			else:
				sanitized_value = sanitize_html(value, linkify=df and df.fieldtype == "Text Editor")

			self.set(fieldname, sanitized_value)

	def _save_passwords(self):
		"""Save password field values in __Auth table"""
		from vmraid.utils.password import remove_encrypted_password, set_encrypted_password

		if self.flags.ignore_save_passwords is True:
			return

		for df in self.meta.get("fields", {"fieldtype": ("=", "Password")}):
			if self.flags.ignore_save_passwords and df.fieldname in self.flags.ignore_save_passwords:
				continue
			new_password = self.get(df.fieldname)

			if not new_password:
				remove_encrypted_password(self.doctype, self.name, df.fieldname)

			if new_password and not self.is_dummy_password(new_password):
				# is not a dummy password like '*****'
				set_encrypted_password(self.doctype, self.name, new_password, df.fieldname)

				# set dummy password like '*****'
				self.set(df.fieldname, "*" * len(new_password))

	def get_password(self, fieldname="password", raise_exception=True):
		from vmraid.utils.password import get_decrypted_password

		if self.get(fieldname) and not self.is_dummy_password(self.get(fieldname)):
			return self.get(fieldname)

		return get_decrypted_password(
			self.doctype, self.name, fieldname, raise_exception=raise_exception
		)

	def is_dummy_password(self, pwd):
		return "".join(set(pwd)) == "*"

	def precision(self, fieldname, parentfield=None):
		"""Returns float precision for a particular field (or get global default).

		:param fieldname: Fieldname for which precision is required.
		:param parentfield: If fieldname is in child table."""
		from vmraid.model.meta import get_field_precision

		if parentfield and not isinstance(parentfield, str) and parentfield.get("parentfield"):
			parentfield = parentfield.parentfield

		cache_key = parentfield or "main"

		if not hasattr(self, "_precision"):
			self._precision = vmraid._dict()

		if cache_key not in self._precision:
			self._precision[cache_key] = vmraid._dict()

		if fieldname not in self._precision[cache_key]:
			self._precision[cache_key][fieldname] = None

			doctype = self.meta.get_field(parentfield).options if parentfield else self.doctype
			df = vmraid.get_meta(doctype).get_field(fieldname)

			if df.fieldtype in ("Currency", "Float", "Percent"):
				self._precision[cache_key][fieldname] = get_field_precision(df, self)

		return self._precision[cache_key][fieldname]

	def get_formatted(
		self, fieldname, doc=None, currency=None, absolute_value=False, translated=False, format=None
	):
		from vmraid.utils.formatters import format_value

		df = self.meta.get_field(fieldname)
		if not df:
			from vmraid.model.meta import get_default_df

			df = get_default_df(fieldname)

		if (
			df.fieldtype == "Currency"
			and not currency
			and (currency_field := df.get("options"))
			and (currency_value := self.get(currency_field))
		):
			currency = vmraid.db.get_value("Currency", currency_value, cache=True)

		val = self.get(fieldname)

		if translated:
			val = _(val)

		if not doc:
			doc = getattr(self, "parent_doc", None) or self

		if (absolute_value or doc.get("absolute_value")) and isinstance(val, (int, float)):
			val = abs(self.get(fieldname))

		return format_value(val, df=df, doc=doc, currency=currency, format=format)

	def is_print_hide(self, fieldname, df=None, for_print=True):
		"""Returns true if fieldname is to be hidden for print.

		Print Hide can be set via the Print Format Builder or in the controller as a list
		of hidden fields. Example

		        class MyDoc(Document):
		                def __setup__(self):
		                        self.print_hide = ["field1", "field2"]

		:param fieldname: Fieldname to be checked if hidden.
		"""
		meta_df = self.meta.get_field(fieldname)
		if meta_df and meta_df.get("__print_hide"):
			return True

		print_hide = 0

		if self.get(fieldname) == 0 and not self.meta.istable:
			print_hide = (df and df.print_hide_if_no_value) or (meta_df and meta_df.print_hide_if_no_value)

		if not print_hide:
			if df and df.print_hide is not None:
				print_hide = df.print_hide
			elif meta_df:
				print_hide = meta_df.print_hide

		return print_hide

	def in_format_data(self, fieldname):
		"""Returns True if shown via Print Format::`format_data` property.
		Called from within standard print format."""
		doc = getattr(self, "parent_doc", self)

		if hasattr(doc, "format_data_map"):
			return fieldname in doc.format_data_map
		else:
			return True

	def reset_values_if_no_permlevel_access(self, has_access_to, high_permlevel_fields):
		"""If the user does not have permissions at permlevel > 0, then reset the values to original / default"""
		to_reset = []

		for df in high_permlevel_fields:
			if (
				df.permlevel not in has_access_to
				and df.fieldtype not in display_fieldtypes
				and df.fieldname not in self.flags.get("ignore_permlevel_for_fields", [])
			):
				to_reset.append(df)

		if to_reset:
			if self.is_new():
				# if new, set default value
				ref_doc = vmraid.new_doc(self.doctype)
			else:
				# get values from old doc
				if self.get("parent_doc"):
					parent_doc = self.parent_doc.get_latest()
					ref_doc = [d for d in parent_doc.get(self.parentfield) if d.name == self.name][0]
				else:
					ref_doc = self.get_latest()

			for df in to_reset:
				self.set(df.fieldname, ref_doc.get(df.fieldname))

	def get_value(self, fieldname):
		df = self.meta.get_field(fieldname)
		val = self.get(fieldname)

		return self.cast(val, df)

	def cast(self, value, df):
		return cast_fieldtype(df.fieldtype, value, show_warning=False)

	def _extract_images_from_text_editor(self):
		from vmraid.core.doctype.file.file import extract_images_from_doc

		if self.doctype != "DocType":
			for df in self.meta.get("fields", {"fieldtype": ("=", "Text Editor")}):
				extract_images_from_doc(self, df.fieldname)


def _filter(data, filters, limit=None):
	"""pass filters as:
	{"key": "val", "key": ["!=", "val"],
	"key": ["in", "val"], "key": ["not in", "val"], "key": "^val",
	"key" : True (exists), "key": False (does not exist) }"""

	out, _filters = [], {}

	if not data:
		return out

	# setup filters as tuples
	if filters:
		for f in filters:
			fval = filters[f]

			if not isinstance(fval, (tuple, list)):
				if fval is True:
					fval = ("not None", fval)
				elif fval is False:
					fval = ("None", fval)
				elif isinstance(fval, str) and fval.startswith("^"):
					fval = ("^", fval[1:])
				else:
					fval = ("=", fval)

			_filters[f] = fval

	for d in data:
		for f, fval in _filters.items():
			if not vmraid.compare(getattr(d, f, None), fval[0], fval[1]):
				break
		else:
			out.append(d)
			if limit and len(out) >= limit:
				break

	return out
