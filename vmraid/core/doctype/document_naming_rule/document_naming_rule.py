# -*- coding: utf-8 -*-
# Copyright (c) 2020, VMRaid Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import vmraid
from vmraid.model.document import Document
from vmraid.utils.data import evaluate_filters
from vmraid import _

class DocumentNamingRule(Document):
	def validate(self):
		self.validate_fields_in_conditions()

	def validate_fields_in_conditions(self):
		if self.has_value_changed("document_type"):
			docfields = [x.fieldname for x in vmraid.get_meta(self.document_type).fields]
			for condition in self.conditions:
				if condition.field not in docfields:
					vmraid.throw(_("{0} is not a field of doctype {1}").format(vmraid.bold(condition.field), vmraid.bold(self.document_type)))

	def apply(self, doc):
		'''
		Apply naming rules for the given document. Will set `name` if the rule is matched.
		'''
		if self.conditions:
			if not evaluate_filters(doc, [(self.document_type, d.field, d.condition, d.value) for d in self.conditions]):
				return

		counter = vmraid.db.get_value(self.doctype, self.name, 'counter', for_update=True) or 0
		doc.name = self.prefix + ('%0'+str(self.prefix_digits)+'d') % (counter + 1)
		vmraid.db.set_value(self.doctype, self.name, 'counter', counter + 1)

@vmraid.whitelist()
def update_current(name, new_counter):
	vmraid.only_for('System Manager')
	vmraid.db.set_value('Document Naming Rule', name, 'counter', new_counter)