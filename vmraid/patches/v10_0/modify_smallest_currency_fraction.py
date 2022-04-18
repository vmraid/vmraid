# Copyright (c) 2018, VMRaid and Contributors
# License: MIT. See LICENSE

import vmraid


def execute():
	vmraid.db.set_value("Currency", "USD", "smallest_currency_fraction_value", "0.01")
