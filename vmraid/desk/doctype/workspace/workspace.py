# -*- coding: utf-8 -*-
# Copyright (c) 2020, VMRaid Technologies and contributors
# License: MIT. See LICENSE

from json import loads

import vmraid
from vmraid import _
from vmraid.desk.desktop import save_new_widget
from vmraid.desk.utils import validate_route_conflict
from vmraid.model.document import Document
from vmraid.model.rename_doc import rename_doc
from vmraid.modules.export_file import export_to_files


class Workspace(Document):
	def validate(self):
		if self.public and not is_workspace_manager() and not disable_saving_as_public():
			vmraid.throw(_("You need to be Workspace Manager to edit this document"))
		validate_route_conflict(self.doctype, self.name)

		try:
			if not isinstance(loads(self.content), list):
				raise
		except Exception:
			vmraid.throw(_("Content data shoud be a list"))

	def on_update(self):
		if disable_saving_as_public():
			return

		if vmraid.conf.developer_mode and self.module and self.public:
			export_to_files(record_list=[["Workspace", self.name]], record_module=self.module)

	@staticmethod
	def get_module_page_map():
		pages = vmraid.get_all(
			"Workspace", fields=["name", "module"], filters={"for_user": ""}, as_list=1
		)

		return {page[1]: page[0] for page in pages if page[1]}

	def get_link_groups(self):
		cards = []
		current_card = vmraid._dict(
			{
				"label": "Link",
				"type": "Card Break",
				"icon": None,
				"hidden": False,
			}
		)

		card_links = []

		for link in self.links:
			link = link.as_dict()
			if link.type == "Card Break":
				if card_links and (
					not current_card.get("only_for")
					or current_card.get("only_for") == vmraid.get_system_settings("country")
				):
					current_card["links"] = card_links
					cards.append(current_card)

				current_card = link
				card_links = []
			else:
				card_links.append(link)

		current_card["links"] = card_links
		cards.append(current_card)

		return cards

	def build_links_table_from_card(self, config):

		for idx, card in enumerate(config):
			links = loads(card.get("links"))

			# remove duplicate before adding
			for idx, link in enumerate(self.links):
				if link.label == card.get("label") and link.type == "Card Break":
					del self.links[idx : idx + link.link_count + 1]

			self.append(
				"links",
				{
					"label": card.get("label"),
					"type": "Card Break",
					"icon": card.get("icon"),
					"hidden": card.get("hidden") or False,
					"link_count": card.get("link_count"),
					"idx": 1 if not self.links else self.links[-1].idx + 1,
				},
			)

			for link in links:
				self.append(
					"links",
					{
						"label": link.get("label"),
						"type": "Link",
						"link_type": link.get("link_type"),
						"link_to": link.get("link_to"),
						"onboard": link.get("onboard"),
						"only_for": link.get("only_for"),
						"dependencies": link.get("dependencies"),
						"is_query_report": link.get("is_query_report"),
						"idx": self.links[-1].idx + 1,
					},
				)


def disable_saving_as_public():
	return (
		vmraid.flags.in_install
		or vmraid.flags.in_patch
		or vmraid.flags.in_test
		or vmraid.flags.in_fixtures
		or vmraid.flags.in_migrate
	)


def get_link_type(key):
	key = key.lower()

	link_type_map = {"doctype": "DocType", "page": "Page", "report": "Report"}

	if key in link_type_map:
		return link_type_map[key]

	return "DocType"


def get_report_type(report):
	report_type = vmraid.get_value("Report", report, "report_type")
	return report_type in ["Query Report", "Script Report", "Custom Report"]


@vmraid.whitelist()
def new_page(new_page):
	if not loads(new_page):
		return

	page = loads(new_page)

	if page.get("public") and not is_workspace_manager():
		return

	doc = vmraid.new_doc("Workspace")
	doc.title = page.get("title")
	doc.icon = page.get("icon")
	doc.content = page.get("content")
	doc.parent_page = page.get("parent_page")
	doc.label = page.get("label")
	doc.for_user = page.get("for_user")
	doc.public = page.get("public")
	doc.sequence_id = last_sequence_id(doc) + 1
	doc.save(ignore_permissions=True)

	return doc


@vmraid.whitelist()
def save_page(title, public, new_widgets, blocks):
	public = vmraid.parse_json(public)

	filters = {"public": public, "label": title}

	if not public:
		filters = {"for_user": vmraid.session.user, "label": title + "-" + vmraid.session.user}
	pages = vmraid.get_list("Workspace", filters=filters)
	if pages:
		doc = vmraid.get_doc("Workspace", pages[0])

	doc.content = blocks
	doc.save(ignore_permissions=True)

	save_new_widget(doc, title, blocks, new_widgets)

	return {"name": title, "public": public, "label": doc.label}


@vmraid.whitelist()
def update_page(name, title, icon, parent, public):
	public = vmraid.parse_json(public)

	doc = vmraid.get_doc("Workspace", name)

	filters = {"parent_page": doc.title, "public": doc.public}
	child_docs = vmraid.get_list("Workspace", filters=filters)

	if doc:
		doc.title = title
		doc.icon = icon
		doc.parent_page = parent
		if doc.public != public:
			doc.sequence_id = vmraid.db.count("Workspace", {"public": public}, cache=True)
			doc.public = public
		doc.for_user = "" if public else doc.for_user or vmraid.session.user
		doc.label = "{0}-{1}".format(title, doc.for_user) if doc.for_user else title
		doc.save(ignore_permissions=True)

		if name != doc.label:
			rename_doc("Workspace", name, doc.label, force=True, ignore_permissions=True)

		# update new name and public in child pages
		if child_docs:
			for child in child_docs:
				child_doc = vmraid.get_doc("Workspace", child.name)
				child_doc.parent_page = doc.title
				child_doc.public = doc.public
				child_doc.save(ignore_permissions=True)

	return {"name": doc.title, "public": doc.public, "label": doc.label}


@vmraid.whitelist()
def duplicate_page(page_name, new_page):
	if not loads(new_page):
		return

	new_page = loads(new_page)

	if new_page.get("is_public") and not is_workspace_manager():
		return

	old_doc = vmraid.get_doc("Workspace", page_name)
	doc = vmraid.copy_doc(old_doc)
	doc.title = new_page.get("title")
	doc.icon = new_page.get("icon")
	doc.parent_page = new_page.get("parent") or ""
	doc.public = new_page.get("is_public")
	doc.for_user = ""
	doc.label = doc.title
	if not doc.public:
		doc.for_user = doc.for_user or vmraid.session.user
		doc.label = "{0}-{1}".format(doc.title, doc.for_user)
	doc.name = doc.label
	if old_doc.public == doc.public:
		doc.sequence_id += 0.1
	else:
		doc.sequence_id = last_sequence_id(doc) + 1
	doc.insert(ignore_permissions=True)

	return doc


@vmraid.whitelist()
def delete_page(page):
	if not loads(page):
		return

	page = loads(page)

	if page.get("public") and not is_workspace_manager():
		return

	if vmraid.db.exists("Workspace", page.get("name")):
		vmraid.get_doc("Workspace", page.get("name")).delete(ignore_permissions=True)

	return {"name": page.get("name"), "public": page.get("public"), "title": page.get("title")}


@vmraid.whitelist()
def sort_pages(sb_public_items, sb_private_items):
	if not loads(sb_public_items) and not loads(sb_private_items):
		return

	sb_public_items = loads(sb_public_items)
	sb_private_items = loads(sb_private_items)

	workspace_public_pages = get_page_list(["name", "title"], {"public": 1})
	workspace_private_pages = get_page_list(["name", "title"], {"for_user": vmraid.session.user})

	if sb_private_items:
		return sort_page(workspace_private_pages, sb_private_items)

	if sb_public_items and is_workspace_manager():
		return sort_page(workspace_public_pages, sb_public_items)

	return False


def sort_page(workspace_pages, pages):
	for seq, d in enumerate(pages):
		for page in workspace_pages:
			if page.title == d.get("title"):
				doc = vmraid.get_doc("Workspace", page.name)
				doc.sequence_id = seq + 1
				doc.parent_page = d.get("parent_page") or ""
				doc.flags.ignore_links = True
				doc.save(ignore_permissions=True)
				break

	return True


def last_sequence_id(doc):
	doc_exists = vmraid.db.exists(
		{"doctype": "Workspace", "public": doc.public, "for_user": doc.for_user}
	)

	if not doc_exists:
		return 0

	return vmraid.db.get_list(
		"Workspace",
		fields=["sequence_id"],
		filters={"public": doc.public, "for_user": doc.for_user},
		order_by="sequence_id desc",
	)[0].sequence_id


def get_page_list(fields, filters):
	return vmraid.get_list("Workspace", fields=fields, filters=filters, order_by="sequence_id asc")


def is_workspace_manager():
	return "Workspace Manager" in vmraid.get_roles()
