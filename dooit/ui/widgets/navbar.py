from rich.table import Table
from rich.text import Text
from dooit.api.workspace import Workspace

from dooit.ui.widgets.sort_options import SortOptions
from dooit.utils import default_config

from ...api.model import MaybeModel
from ...api.manager import Manager, Model
from .tree import TreeList
from ..events import TopicSelect, SwitchTab
from dooit.utils.default_config import navbar


class NavBar(TreeList):
    def __init__(self):
        super().__init__()
        self.sort_menu = SortOptions(
            name=f"Sort_{self.name}", options=Workspace.fields, parent_widget=self
        )
        self.sort_menu.visible = False

    @property
    def EMPTY(self):
        return [
            Text.from_markup(i) if isinstance(i, str) else i
            for i in default_config.EMPTY_NAVBAR
        ]

    def set_styles(self):
        self.style_on = navbar["about"]["highlight"]
        self.style_off = navbar["about"]["dim"]
        self.style_edit = navbar["about"]["edit"]

    def _setup_table(self) -> None:
        self.table = Table.grid(expand=True)
        self.table.add_column("about")

    async def handle_tab(self):
        if self.current == -1:
            return

        if self.filter.value:

            if self.item:
                await self.emit(
                    TopicSelect(
                        self,
                        self.item,
                    )
                )

            await self._stop_filtering()
            self.current = -1

        await self.emit(SwitchTab(self))

    async def watch_current(self, value: int):

        value = min(value, len(self.row_vals) - 1)
        self.current = value

        self._fix_view()
        if self.current != -1 and self.item:
            await self.emit(TopicSelect(self, self.item))

        self.refresh()

    # ##########################################

    def add_row(self, row, highlight: bool):

        items = [str(i.render()) for i in row.get_field_values()]
        desc = self._stylize_desc(items[0], highlight)

        return self.push_row([desc], row.depth)

    # ##########################################

    def _stylize_desc(self, item, highlight: bool = False) -> Text:
        fmt = navbar["about"]

        if highlight:
            if self.editing == "none":
                text: str = fmt["highlight"]
            else:
                text: str = fmt["edit"]
        else:
            text: str = fmt["dim"]

        text = text.format(desc=item)
        return Text.from_markup(text)

    def _get_children(self, model: Manager):
        return model.workspaces

    def _add_sibling(self):
        if self.item and self.current >= 0:
            self.item.add_sibling()
        else:
            self.model.add_child_workspace()

    def _add_child(self) -> Model:
        if self.item:
            return self.item.add_workspace()
        else:
            return self.model.add_child_workspace()

    def _drop(self):
        if self.item:
            self.item.drop()

    def _next_sibling(self) -> MaybeModel:
        if self.item:
            return self.item.next_sibling()

    def _prev_sibling(self) -> MaybeModel:
        if self.item:
            return self.item.prev_sibling()

    def _shift_down(self):
        if self.item:
            return self.item.shift_down()

    def _shift_up(self):
        if self.item:
            return self.item.shift_up()
