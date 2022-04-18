import vmraid


def execute():
	vmraid.db.change_column_type("__Auth", column="password", type="TEXT")
