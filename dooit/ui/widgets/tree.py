import re
from functools import partial
from typing import List, Optional
from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text
from textual import events
from textual.reactive import Reactive
from textual.widget import Widget
from rich.table import Table, box
from .simple_input import SimpleInput
from ...api.workspace import Workspace
from ...api.manager import Manager, manager, Model
from ...api.model import MaybeModel
from ...ui.widgets.sort_options import SortOptions
from ...ui.events.events import ChangeStatus, Notify


class Component:
    def __init__(
        self,
        item: Workspace,
        depth: int = 0,
        index: int = 0,
        expanded: bool = False,
    ) -> None:
        self.item = item
        self.expanded = expanded
        self.depth = depth
        self.index = index
        self.fields = {
            field: SimpleInput(
                value=getattr(item, field),
            )
            for field in item.fields
        }

    def refresh_item(self, field: str):
        self.fields[field] = SimpleInput(
            value=getattr(
                self.item,
                field,
            )
        )

    def get_field_values(self):
        return self.fields.values()

    def toggle_expand(self):
        self.expanded = not self.expanded

    def expand(self, expand: bool = True):
        self.expanded = expand


class VerticalView:
    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

    def fix_view(self, current: int):
        if self.a < 0:
            self.shift(-self.a)

        if current <= self.a:
            self.shift(current - self.a)

        if self.b <= current:
            self.shift(current - self.b)

    def shift_upper(self, delta):
        self.a += delta

    def shift_lower(self, delta):
        self.b += delta

    def shift(self, delta: int):
        self.shift_lower(delta)
        self.shift_upper(delta)

    def height(self):
        return self.b - self.a

    def range(self):
        return range(self.a, self.b + 1)


class TreeList(Widget):
    _has_focus = False
    current = Reactive(-1)
    _rows = {}

    def __init__(
        self,
        name: str | None = None,
        model: Manager = manager,
    ) -> None:
        super().__init__(name)
        self.set_styles()

        self.model = model
        self.editing = "none"
        self.sort_menu = SortOptions()
        self.sort_menu.visible = False
        self.filter = SimpleInput()

    @property
    def EMPTY(self):
        return ""

    def set_styles(self):
        self.style_off = "b white"
        self.style_on = "dim grey50"
        self.style_edit = "b cyan"

    async def on_mount(self):
        self._set_screen()
        self._refresh_rows()

    # ------------ INTERNALS ----------------

    def toggle_highlight(self):
        self._has_focus = not self._has_focus
        self.refresh()

    @property
    def has_focus(self):
        return self._has_focus

    @property
    def component(self):
        if self.current != -1:
            return self.row_vals[self.current]

    @property
    def item(self):
        if self.component:
            return self.component.item

    # --------------------------------------

    def _fix_view(self):
        self.view.fix_view(self.current)

    def _set_screen(self):
        y = self._size.height - 3  # Panel
        self.view = VerticalView(0, y)

    def _set_view(self) -> None:
        prev_size = self.view.height()
        curr_size = self._size.height - 3  # Panel
        diff = prev_size - curr_size

        if diff <= 0:
            self.view.shift_upper(diff)
        else:
            self.view.shift_lower(-diff)
            bottom = max(self.current + 1, self.view.b)
            self.view.a = bottom - curr_size
            self.view.b = bottom

        self._fix_view()

    def _setup_table(self) -> None:
        self.table = Table.grid(expand=True)

    def _get_children(self, model: Model):
        return model.workspaces

    def _refresh_rows(self):
        _rows_copy = self._rows
        self._rows = {}

        def add_rows(item: Workspace, nest_level=0):

            name = item.name

            def push_item(item: Workspace):
                self._rows[name] = _rows_copy.get(
                    name,
                    Component(
                        item, nest_level, len(self._rows)
                    ),  # defaults to a new Component
                )
                self._rows[name].index = len(self._rows) - 1

            if pattern := self.filter.value:
                if re.findall(pattern, item.about):
                    push_item(item)
                for i in self._get_children(item):
                    add_rows(i, nest_level + 1)
            else:
                push_item(item)
                if self._rows[name].expanded:
                    for i in self._get_children(item):
                        add_rows(i, nest_level + 1)

        for i in self._get_children(self.model):
            add_rows(i)

        self.row_vals: List[Component] = list(self._rows.values())
        self.refresh()

    async def _start_edit(self, field: str):
        if not self.component:
            return

        if field == "about":
            await self.emit(ChangeStatus(self, "INSERT"))
        else:
            await self.emit(ChangeStatus(self, "DATE"))

        self.component.fields[field].on_focus()
        self.editing = field

    async def _stop_edit(self):
        if not self.component:
            return

        await self.emit(ChangeStatus(self, "NORMAL"))
        self.component.fields[self.editing].on_blur()
        self.component.item.edit(
            self.editing,
            self.component.fields[self.editing].value,
        )
        self.editing = "none"

    async def _start_filtering(self):
        self.filter.on_focus()
        await self.emit(Notify(self, self.filter.render()))

    async def _stop_filtering(self):
        self.filter.clear()
        self._refresh_rows()
        await self.emit(Notify(self, self.filter.render()))
        await self.emit(ChangeStatus(self, "NORMAL"))

    def _add_child(self) -> Model:
        ...

    def _drop(self) -> None:
        ...

    def _add_sibling(self) -> Model:
        ...

    def _next_sibling(self) -> MaybeModel:
        ...

    def _prev_sibling(self) -> MaybeModel:
        ...

    def _shift_up(self) -> None:
        ...

    def _shift_down(self) -> None:
        ...

    async def remove_item(self):
        if not self.item:
            return

        self._drop()
        self._refresh_rows()
        self.current = self.current

    async def add_child(self):

        if self.component and self.item:
            self.component.expand()

        self._add_child()
        self._refresh_rows()
        await self.move_down()
        await self._start_edit("about")

    async def add_sibling(self):

        if not self.item:
            child = self._add_child()
            self._refresh_rows()
            self.current = self._rows[child.name].index
            await self._start_edit("about")
            return

        self._add_sibling()
        self._refresh_rows()
        await self.to_next_sibling("about")

    async def to_next_sibling(self, edit: Optional[str] = None):
        if not self.item:
            return

        await self._move_to_item(self._next_sibling(), edit)

    async def to_prev_sibling(self, edit: Optional[str] = None):
        if not self.item:
            return

        await self._move_to_item(self._prev_sibling(), edit)

    async def _move_to_item(self, item: MaybeModel, edit: Optional[str] = None):
        if item is None:
            return

        self.current = self._rows[item.name].index
        if edit:
            await self._start_edit(edit)

    async def shift_up(self):
        if not self.item:
            return

        self._shift_up()
        self._refresh_rows()
        await self.move_up()

    async def shift_down(self):
        if not self.item:
            return

        self._shift_down()
        self._refresh_rows()
        await self.move_down()

    async def move_up(self):
        if self.current:
            self.current -= 1

    async def move_down(self):
        self.current += 1

    async def move_to_top(self):
        self.current = 0

    async def move_to_bottom(self):
        self.current = len(self.row_vals)

    async def toggle_expand(self):
        if not self.component:
            return

        self.component.toggle_expand()
        self._refresh_rows()

    async def toggle_expand_parent(self):
        if not self.item:
            return

        parent = self.item.parent
        if parent and not isinstance(parent, Manager):
            index = self._rows[parent.name].index
            self.current = index

        await self.toggle_expand()

    def sort(self, attr: str):
        if self.item:
            curr = self.item.name
            self.item.sort(attr)
            self._refresh_rows()
            self.current = self._rows[curr].index

    async def show_sort_menu(self):
        self.sort_menu.visible = True

    async def check_extra_keys(self, event: events.Key):
        pass

    async def handle_tab(self):
        pass

    async def handle_key(self, event: events.Key):

        key = event.key

        if self.editing != "none":
            field = self.row_vals[self.current].fields[self.editing]

            if key == "escape":
                await self._stop_edit()
            else:
                await field.handle_keypress(event.key)

        else:

            if self.sort_menu.visible:
                await self.sort_menu.handle_key(event)

            elif self.filter.has_focus:
                await self.filter.handle_keypress(event.key)
                await self.emit(Notify(self, self.filter.render()))
                self._refresh_rows()
                self.current = 0

            else:

                keybinds = {
                    "escape": self._stop_filtering,
                    "ctrl+i": self.handle_tab,
                    "k": self.move_up,
                    "up": self.move_up,
                    "K": self.shift_up,
                    "shift+up": self.shift_up,
                    "j": self.move_down,
                    "down": self.move_down,
                    "J": self.shift_down,
                    "shift+down": self.shift_down,
                    "i": partial(self._start_edit, "about"),
                    "z": self.toggle_expand,
                    "Z": self.toggle_expand_parent,
                    "A": self.add_child,
                    "a": self.add_sibling,
                    "x": self.remove_item,
                    "g": self.move_to_top,
                    "home": self.move_to_top,
                    "G": self.move_to_bottom,
                    "s": self.show_sort_menu,
                    "/": self._start_filtering,
                }

                if key in keybinds:
                    await keybinds[key]()

        await self.check_extra_keys(event)
        self.refresh(layout=True)

    def add_row(self, _: Component, __: bool):
        ...

    def make_table(self):
        self._setup_table()

        # for i in self.view.range():
        for i in range(len(self.row_vals)):
            try:
                self.add_row(self.row_vals[i], i == self.current)
            except:
                pass

    def push_row(self, row: List[Text], padding: int):
        if pattern := self.filter.value:
            for i in row:
                i.highlight_regex(pattern, style="b red")

        else:
            pad = " " * padding
            row = [Text(pad) + i for i in row]

        if row:
            self.table.add_row(*row)

    def render(self) -> RenderableType:

        if self.sort_menu.visible:
            to_render = self.sort_menu.render()
        elif not self.row_vals:
            to_render = Align.center(
                Group(
                    *[Align.center(i) for i in self.EMPTY],
                ),
                vertical="middle",
            )
        else:
            self.make_table()
            to_render = self.table

        height = self._size.height
        return Panel(
            to_render,
            expand=True,
            height=height,
            box=box.HEAVY,
            border_style="cyan" if self._has_focus else "dim white",
        )

    async def on_resize(self, event: events.Resize) -> None:
        self._set_view()
        return await super().on_resize(event)
