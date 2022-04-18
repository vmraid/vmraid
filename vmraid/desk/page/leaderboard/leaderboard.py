# Copyright (c) 2017, VMRaid and Contributors
# License: MIT. See LICENSE
import vmraid


@vmraid.whitelist()
def get_leaderboard_config():
	leaderboard_config = vmraid._dict()
	leaderboard_hooks = vmraid.get_hooks("leaderboards")
	for hook in leaderboard_hooks:
		leaderboard_config.update(vmraid.get_attr(hook)())

	return leaderboard_config
