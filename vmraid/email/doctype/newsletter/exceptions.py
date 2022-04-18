# Copyright (c) 2021, VMRaid and Contributors
# MIT License. See LICENSE

from vmraid.exceptions import ValidationError


class NewsletterAlreadySentError(ValidationError):
	pass


class NoRecipientFoundError(ValidationError):
	pass


class NewsletterNotSavedError(ValidationError):
	pass
