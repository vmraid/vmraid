# Copyright (c) 2015, VMRaid Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

# Tree (Hierarchical) Nested Set Model (nsm)
#
# To use the nested set model,
# use the following pattern
# 1. name your parent field as "parent_item_group" if not have a property nsm_parent_field as your field name in the document class
# 2. have a field called "old_parent" in your fields list - this identifies whether the parent has been changed
# 3. call update_nsm(doc_obj) in the on_upate method

# ------------------------------------------
from __future__ import unicode_literals

import vmraid
from vmraid import _
from vmraid.model.document import Document
from vmraid.utils import now

class NestedSetRecursionError(vmraid.ValidationError): pass
class NestedSetMultipleRootsError(vmraid.ValidationError): pass
class NestedSetChildExistsError(vmraid.ValidationError): pass
class NestedSetInvalidMergeError(vmraid.ValidationError): pass

# called in the on_update method
def update_nsm(doc):
	# get fields, data from the DocType
	opf = 'old_parent'
	pf = "parent_" + vmraid.scrub(doc.doctype)

	if hasattr(doc,'nsm_parent_field'):
		pf = doc.nsm_parent_field
	if hasattr(doc,'nsm_oldparent_field'):
		opf = doc.nsm_oldparent_field

	p, op = doc.get(pf) or None, doc.get(opf) or None

	# has parent changed (?) or parent is None (root)
	if not doc.lft and not doc.rgt:
		update_add_node(doc, p or '', pf)
	elif op != p:
		update_move_node(doc, pf)

	# set old parent
	doc.set(opf, p)
	vmraid.db.set_value(doc.doctype, doc.name, opf, p or '', update_modified=False)

	doc.reload()

def update_add_node(doc, parent, parent_field):
	"""
		insert a new node
	"""

	n = now()

	doctype = doc.doctype
	name = doc.name

	# get the last sibling of the parent
	if parent:
		left, right = vmraid.db.sql("select lft, rgt from `tab{0}` where name=%s"
			.format(doctype), parent)[0]
		validate_loop(doc.doctype, doc.name, left, right)
	else: # root
		right = vmraid.db.sql("""
			SELECT COALESCE(MAX(rgt), 0) + 1 FROM `tab{0}`
			WHERE COALESCE(`{1}`, '') = ''
		""".format(doctype, parent_field))[0][0]
	right = right or 1

	# update all on the right
	vmraid.db.sql("update `tab{0}` set rgt = rgt+2, modified=%s where rgt >= %s"
		.format(doctype), (n, right))
	vmraid.db.sql("update `tab{0}` set lft = lft+2, modified=%s where lft >= %s"
		.format(doctype), (n, right))

	# update index of new node
	if vmraid.db.sql("select * from `tab{0}` where lft=%s or rgt=%s".format(doctype), (right, right+1)):
		vmraid.msgprint(_("Nested set error. Please contact the Administrator."))
		raise Exception

	vmraid.db.sql("update `tab{0}` set lft=%s, rgt=%s, modified=%s where name=%s".format(doctype),
		(right,right+1, n, name))
	return right


def update_move_node(doc, parent_field):
	n = now()
	parent = doc.get(parent_field)

	if parent:
		new_parent = vmraid.db.sql("""select lft, rgt from `tab{0}`
			where name = %s""".format(doc.doctype), parent, as_dict=1)[0]

		validate_loop(doc.doctype, doc.name, new_parent.lft, new_parent.rgt)

	# move to dark side
	vmraid.db.sql("""update `tab{0}` set lft = -lft, rgt = -rgt, modified=%s
		where lft >= %s and rgt <= %s""".format(doc.doctype), (n, doc.lft, doc.rgt))

	# shift left
	diff = doc.rgt - doc.lft + 1
	vmraid.db.sql("""update `tab{0}` set lft = lft -%s, rgt = rgt - %s, modified=%s
		where lft > %s""".format(doc.doctype), (diff, diff, n, doc.rgt))

	# shift left rgts of ancestors whose only rgts must shift
	vmraid.db.sql("""update `tab{0}` set rgt = rgt - %s, modified=%s
		where lft < %s and rgt > %s""".format(doc.doctype), (diff, n, doc.lft, doc.rgt))

	if parent:
		new_parent = vmraid.db.sql("""select lft, rgt from `tab%s`
			where name = %s""" % (doc.doctype, '%s'), parent, as_dict=1)[0]


		# set parent lft, rgt
		vmraid.db.sql("""update `tab{0}` set rgt = rgt + %s, modified=%s
			where name = %s""".format(doc.doctype), (diff, n, parent))

		# shift right at new parent
		vmraid.db.sql("""update `tab{0}` set lft = lft + %s, rgt = rgt + %s, modified=%s
			where lft > %s""".format(doc.doctype), (diff, diff, n, new_parent.rgt))

		# shift right rgts of ancestors whose only rgts must shift
		vmraid.db.sql("""update `tab{0}` set rgt = rgt + %s, modified=%s
			where lft < %s and rgt > %s""".format(doc.doctype),
			(diff, n, new_parent.lft, new_parent.rgt))


		new_diff = new_parent.rgt - doc.lft
	else:
		# new root
		max_rgt = vmraid.db.sql("""select max(rgt) from `tab{0}`""".format(doc.doctype))[0][0]
		new_diff = max_rgt + 1 - doc.lft

	# bring back from dark side
	vmraid.db.sql("""update `tab{0}` set lft = -lft + %s, rgt = -rgt + %s, modified=%s
		where lft < 0""".format(doc.doctype), (new_diff, new_diff, n))

@vmraid.whitelist()
def rebuild_tree(doctype, parent_field):
	"""
		call rebuild_node for all root nodes
	"""

	# Check for perm if called from client-side
	if vmraid.request and vmraid.local.form_dict.cmd == 'rebuild_tree':
		vmraid.only_for('System Manager')

	# get all roots
	vmraid.db.auto_commit_on_many_writes = 1

	right = 1
	result = vmraid.db.sql("SELECT name FROM `tab%s` WHERE `%s`='' or `%s` IS NULL ORDER BY name ASC" % (doctype, parent_field, parent_field))
	for r in result:
		right = rebuild_node(doctype, r[0], right, parent_field)

	vmraid.db.auto_commit_on_many_writes = 0

def rebuild_node(doctype, parent, left, parent_field):
	"""
		reset lft, rgt and recursive call for all children
	"""
	from vmraid.utils import now
	n = now()

	# the right value of this node is the left value + 1
	right = left+1

	# get all children of this node
	result = vmraid.db.sql("SELECT name FROM `tab{0}` WHERE `{1}`=%s"
		.format(doctype, parent_field), (parent))
	for r in result:
		right = rebuild_node(doctype, r[0], right, parent_field)

	# we've got the left value, and now that we've processed
	# the children of this node we also know the right value
	vmraid.db.sql("""UPDATE `tab{0}` SET lft=%s, rgt=%s, modified=%s
		WHERE name=%s""".format(doctype), (left,right,n,parent))

	#return the right value of this node + 1
	return right+1


def validate_loop(doctype, name, lft, rgt):
	"""check if item not an ancestor (loop)"""
	if name in vmraid.db.sql_list("""select name from `tab{0}` where lft <= %s and rgt >= %s"""
		 .format(doctype), (lft, rgt)):
		vmraid.throw(_("Item cannot be added to its own descendents"), NestedSetRecursionError)

class NestedSet(Document):
	def __setup__(self):
		if self.meta.get("nsm_parent_field"):
			self.nsm_parent_field = self.meta.nsm_parent_field

	def on_update(self):
		update_nsm(self)
		self.validate_ledger()

	def on_trash(self, allow_root_deletion=False):
		if not getattr(self, 'nsm_parent_field', None):
			self.nsm_parent_field = vmraid.scrub(self.doctype) + "_parent"

		parent = self.get(self.nsm_parent_field)
		if not parent and not allow_root_deletion:
			vmraid.throw(_("Root {0} cannot be deleted").format(_(self.doctype)))

		# cannot delete non-empty group
		self.validate_if_child_exists()

		self.set(self.nsm_parent_field, "")

		try:
			update_nsm(self)
		except vmraid.DoesNotExistError:
			if self.flags.on_rollback:
				pass
				vmraid.message_log.pop()
			else:
				raise

	def validate_if_child_exists(self):
		has_children = vmraid.db.sql("""select count(name) from `tab{doctype}`
			where `{nsm_parent_field}`=%s""".format(doctype=self.doctype, nsm_parent_field=self.nsm_parent_field),
			(self.name,))[0][0]
		if has_children:
			vmraid.throw(_("Cannot delete {0} as it has child nodes").format(self.name), NestedSetChildExistsError)

	def before_rename(self, olddn, newdn, merge=False, group_fname="is_group"):
		if merge and hasattr(self, group_fname):
			is_group = vmraid.db.get_value(self.doctype, newdn, group_fname)
			if self.get(group_fname) != is_group:
				vmraid.throw(_("Merging is only possible between Group-to-Group or Leaf Node-to-Leaf Node"), NestedSetInvalidMergeError)

	def after_rename(self, olddn, newdn, merge=False):
		if not self.nsm_parent_field:
			parent_field = "parent_" + self.doctype.replace(" ", "_").lower()
		else:
			parent_field = self.nsm_parent_field

		# set old_parent for children
		vmraid.db.sql("update `tab{0}` set old_parent=%s where {1}=%s"
			.format(self.doctype, parent_field), (newdn, newdn))

		if merge:
			rebuild_tree(self.doctype, parent_field)

	def validate_one_root(self):
		if not self.get(self.nsm_parent_field):
			if self.get_root_node_count() > 1:
				vmraid.throw(_("""Multiple root nodes not allowed."""), NestedSetMultipleRootsError)

	def get_root_node_count(self):
		return vmraid.db.count(self.doctype, {
			self.nsm_parent_field: ''
		})

	def validate_ledger(self, group_identifier="is_group"):
		if hasattr(self, group_identifier) and not bool(self.get(group_identifier)):
			if vmraid.db.sql("""select name from `tab{0}` where {1}=%s and docstatus!=2"""
				.format(self.doctype, self.nsm_parent_field), (self.name)):
				vmraid.throw(_("{0} {1} cannot be a leaf node as it has children").format(_(self.doctype), self.name))

	def get_ancestors(self):
		return get_ancestors_of(self.doctype, self.name)

def get_root_of(doctype):
	"""Get root element of a DocType with a tree structure"""
	result = vmraid.db.sql("""select t1.name from `tab{0}` t1 where
		(select count(*) from `tab{1}` t2 where
			t2.lft < t1.lft and t2.rgt > t1.rgt) = 0
		and t1.rgt > t1.lft""".format(doctype, doctype))
	return result[0][0] if result else None

def get_ancestors_of(doctype, name, order_by="lft desc", limit=None):
	"""Get ancestor elements of a DocType with a tree structure"""
	lft, rgt = vmraid.db.get_value(doctype, name, ["lft", "rgt"])

	result = [d["name"] for d in vmraid.db.get_all(doctype, {"lft": ["<", lft], "rgt": [">", rgt]},
		"name", order_by=order_by, limit_page_length=limit)]

	return result or []

def get_descendants_of(doctype, name, order_by="lft desc", limit=None,
	ignore_permissions=False):
	'''Return descendants of the current record'''
	lft, rgt = vmraid.db.get_value(doctype, name, ['lft', 'rgt'])

	result = [d["name"] for d in vmraid.db.get_list(doctype, {"lft": [">", lft], "rgt": ["<", rgt]},
		"name", order_by=order_by, limit_page_length=limit, ignore_permissions=ignore_permissions)]

	return result or []
