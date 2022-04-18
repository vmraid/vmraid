# Copyright (c) 2019, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import vmraid
from vmraid.model.document import Document
from vmraid.query_builder import DocType
from vmraid.utils import unique


class Tag(Document):
	pass


def check_user_tags(dt):
	"if the user does not have a tags column, then it creates one"
	try:
		doctype = DocType(dt)
		vmraid.qb.from_(doctype).select(doctype._user_tags).limit(1).run()
	except Exception as e:
		if vmraid.db.is_column_missing(e):
			DocTags(dt).setup()


@vmraid.whitelist()
def add_tag(tag, dt, dn, color=None):
	"adds a new tag to a record, and creates the Tag master"
	DocTags(dt).add(dn, tag)

	return tag


@vmraid.whitelist()
def add_tags(tags, dt, docs, color=None):
	"adds a new tag to a record, and creates the Tag master"
	tags = vmraid.parse_json(tags)
	docs = vmraid.parse_json(docs)
	for doc in docs:
		for tag in tags:
			DocTags(dt).add(doc, tag)

	# return tag


@vmraid.whitelist()
def remove_tag(tag, dt, dn):
	"removes tag from the record"
	DocTags(dt).remove(dn, tag)


@vmraid.whitelist()
def get_tagged_docs(doctype, tag):
	vmraid.has_permission(doctype, throw=True)
	doctype = DocType(doctype)
	return (vmraid.qb.from_(doctype).where(doctype._user_tags.like(tag)).select(doctype.name)).run()


@vmraid.whitelist()
def get_tags(doctype, txt):
	tag = vmraid.get_list("Tag", filters=[["name", "like", "%{}%".format(txt)]])
	tags = [t.name for t in tag]

	return sorted(filter(lambda t: t and txt.lower() in t.lower(), list(set(tags))))


class DocTags:
	"""Tags for a particular doctype"""

	def __init__(self, dt):
		self.dt = dt

	def get_tag_fields(self):
		"""returns tag_fields property"""
		return vmraid.db.get_value("DocType", self.dt, "tag_fields")

	def get_tags(self, dn):
		"""returns tag for a particular item"""
		return (vmraid.db.get_value(self.dt, dn, "_user_tags", ignore=1) or "").strip()

	def add(self, dn, tag):
		"""add a new user tag"""
		tl = self.get_tags(dn).split(",")
		if not tag in tl:
			tl.append(tag)
			if not vmraid.db.exists("Tag", tag):
				vmraid.get_doc({"doctype": "Tag", "name": tag}).insert(ignore_permissions=True)
			self.update(dn, tl)

	def remove(self, dn, tag):
		"""remove a user tag"""
		tl = self.get_tags(dn).split(",")
		self.update(dn, filter(lambda x: x.lower() != tag.lower(), tl))

	def remove_all(self, dn):
		"""remove all user tags (call before delete)"""
		self.update(dn, [])

	def update(self, dn, tl):
		"""updates the _user_tag column in the table"""

		if not tl:
			tags = ""
		else:
			tl = unique(filter(lambda x: x, tl))
			tags = "," + ",".join(tl)
		try:
			vmraid.db.sql(
				"update `tab%s` set _user_tags=%s where name=%s" % (self.dt, "%s", "%s"), (tags, dn)
			)
			doc = vmraid.get_doc(self.dt, dn)
			update_tags(doc, tags)
		except Exception as e:
			if vmraid.db.is_column_missing(e):
				if not tags:
					# no tags, nothing to do
					return

				self.setup()
				self.update(dn, tl)
			else:
				raise

	def setup(self):
		"""adds the _user_tags column if not exists"""
		from vmraid.database.schema import add_column

		add_column(self.dt, "_user_tags", "Data")


def delete_tags_for_document(doc):
	"""
	Delete the Tag Link entry of a document that has
	been deleted
	:param doc: Deleted document
	"""
	if not vmraid.db.table_exists("Tag Link"):
		return

	vmraid.db.delete("Tag Link", {"document_type": doc.doctype, "document_name": doc.name})


def update_tags(doc, tags):
	"""Adds tags for documents

	:param doc: Document to be added to global tags
	"""
	new_tags = {tag.strip() for tag in tags.split(",") if tag}
	existing_tags = [
		tag.tag
		for tag in vmraid.get_list(
			"Tag Link", filters={"document_type": doc.doctype, "document_name": doc.name}, fields=["tag"]
		)
	]

	added_tags = set(new_tags) - set(existing_tags)
	for tag in added_tags:
		vmraid.get_doc(
			{
				"doctype": "Tag Link",
				"document_type": doc.doctype,
				"document_name": doc.name,
				"title": doc.get_title() or "",
				"tag": tag,
			}
		).insert(ignore_permissions=True)

	deleted_tags = list(set(existing_tags) - set(new_tags))
	for tag in deleted_tags:
		vmraid.db.delete(
			"Tag Link", {"document_type": doc.doctype, "document_name": doc.name, "tag": tag}
		)


@vmraid.whitelist()
def get_documents_for_tag(tag):
	"""
	Search for given text in Tag Link
	:param tag: tag to be searched
	"""
	# remove hastag `#` from tag
	tag = tag[1:]
	results = []

	result = vmraid.get_list(
		"Tag Link", filters={"tag": tag}, fields=["document_type", "document_name", "title", "tag"]
	)

	for res in result:
		results.append({"doctype": res.document_type, "name": res.document_name, "content": res.title})

	return results


@vmraid.whitelist()
def get_tags_list_for_awesomebar():
	return [t.name for t in vmraid.get_list("Tag")]
