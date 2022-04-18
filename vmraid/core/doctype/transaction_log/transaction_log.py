# Copyright (c) 2021, VMRaid Technologies and contributors
# License: MIT. See LICENSE

import hashlib

import vmraid
from vmraid import _
from vmraid.model.document import Document
from vmraid.query_builder import DocType
from vmraid.utils import cint, now_datetime


class TransactionLog(Document):
	def before_insert(self):
		index = get_current_index()
		self.row_index = index
		self.timestamp = now_datetime()
		if index != 1:
			prev_hash = vmraid.get_all(
				"Transaction Log", filters={"row_index": str(index - 1)}, pluck="chaining_hash", limit=1
			)
			if prev_hash:
				self.previous_hash = prev_hash[0]
			else:
				self.previous_hash = "Indexing broken"
		else:
			self.previous_hash = self.hash_line()
		self.transaction_hash = self.hash_line()
		self.chaining_hash = self.hash_chain()
		self.checksum_version = "v1.0.1"

	def hash_line(self):
		sha = hashlib.sha256()
		sha.update(
			vmraid.safe_encode(str(self.row_index))
			+ vmraid.safe_encode(str(self.timestamp))
			+ vmraid.safe_encode(str(self.data))
		)
		return sha.hexdigest()

	def hash_chain(self):
		sha = hashlib.sha256()
		sha.update(
			vmraid.safe_encode(str(self.transaction_hash)) + vmraid.safe_encode(str(self.previous_hash))
		)
		return sha.hexdigest()


def get_current_index():
	series = DocType("Series")
	current = (
		vmraid.qb.from_(series).where(series.name == "TRANSACTLOG").for_update().select("current")
	).run()

	if current and current[0][0] is not None:
		current = current[0][0]

		vmraid.db.sql(
			"""UPDATE `tabSeries`
			SET `current` = `current` + 1
			where `name` = 'TRANSACTLOG'"""
		)
		current = cint(current) + 1
	else:
		vmraid.db.sql("INSERT INTO `tabSeries` (name, current) VALUES ('TRANSACTLOG', 1)")
		current = 1
	return current
