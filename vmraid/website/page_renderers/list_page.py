import vmraid
from vmraid.website.page_renderers.template_page import TemplatePage


class ListPage(TemplatePage):
	def can_render(self):
		return vmraid.db.exists("DocType", self.path, True)

	def render(self):
		vmraid.local.form_dict.doctype = self.path
		self.set_standard_path("list")
		return super().render()
