"""《鸣潮》3.5 中文角色养成与配装助手。"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # --check-data 不需要 Pillow，GUI 会给出明确提示。
    Image = ImageDraw = ImageTk = None  # type: ignore[assignment]

from calculator import calculate_level_details, calculate_materials, material_rows
from data_loader import (
    ELEMENT_FILTERS,
    DataValidationError,
    load_all_data,
    search_characters,
)


MODE_LABELS = {
    "等级 + 技能合计": "total",
    "角色等级档位": "level",
    "五项技能": "skills",
}
ELEMENT_COLORS = {
    "冷凝": ("#d9edff", "#22618c"),
    "热熔": ("#ffe2d8", "#a3422d"),
    "导电": ("#eadfff", "#6442a2"),
    "气动": ("#d7f5ed", "#217765"),
    "衍射": ("#fff0ba", "#806315"),
    "湮灭": ("#e2e3ec", "#454a69"),
}
BACKGROUND = "#f1f4f9"
CARD = "#ffffff"
TEXT = "#1f2937"
MUTED = "#667085"
ACCENT = "#4263a8"


class ImageCache:
    """加载本地图片并保持 Tk 引用，缺图时返回纯色占位卡。"""

    def __init__(
        self, root: tk.Misc, project_dir: Path, assets: dict[str, dict[str, Any]]
    ) -> None:
        self.root = root
        self.project_dir = project_dir
        self.assets = assets
        self.cache: dict[tuple[str, tuple[int, int]], Any] = {}

    def get(self, asset_key: str, size: tuple[int, int]) -> Any:
        cache_key = (asset_key, size)
        if cache_key in self.cache:
            return self.cache[cache_key]
        image = self._load(asset_key, size)
        photo = ImageTk.PhotoImage(image, master=self.root)
        self.cache[cache_key] = photo
        return photo

    def _load(self, asset_key: str, size: tuple[int, int]) -> Any:
        entry = self.assets.get(asset_key)
        if entry:
            path = self.project_dir / entry["path"]
            try:
                with Image.open(path) as source:
                    source.load()
                    image = source.convert("RGBA")
                if image.size != size:
                    image.thumbnail(size, Image.Resampling.LANCZOS)
                    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
                    canvas.alpha_composite(
                        image,
                        ((size[0] - image.width) // 2, (size[1] - image.height) // 2),
                    )
                    return canvas
                return image
            except (OSError, ValueError):
                pass
        placeholder = Image.new("RGBA", size, (224, 229, 239, 255))
        draw = ImageDraw.Draw(placeholder)
        inset = max(4, min(size) // 9)
        draw.rounded_rectangle(
            (inset, inset, size[0] - inset, size[1] - inset),
            radius=max(4, inset),
            fill=(197, 205, 220, 255),
        )
        return placeholder


class ScrollArea(ttk.Frame):
    """可复用的垂直滚动内容区。"""

    def __init__(self, parent: tk.Misc, *, background: str = CARD) -> None:
        super().__init__(parent, style="Card.TFrame")
        self.canvas = tk.Canvas(
            self, background=background, highlightthickness=0, borderwidth=0
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = tk.Frame(self.canvas, background=background)
        self.window_id = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.body.bind("<Configure>", self._update_scrollregion)
        self.canvas.bind("<Configure>", self._resize_body)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _update_scrollregion(self, _event: tk.Event[tk.Misc]) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_body(self, event: tk.Event[tk.Misc]) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is not None and self._contains(widget):
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _contains(self, widget: tk.Misc) -> bool:
        current: tk.Misc | None = widget
        while current is not None:
            if current == self:
                return True
            current = current.master
        return False

    def clear(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)


class WuwaPlannerApp:
    """主窗口：角色卡片、图标材料和中文配装建议。"""

    def __init__(self, root: tk.Tk, data: dict[str, Any]) -> None:
        self.root = root
        self.data = data
        self.characters = data["characters"]
        self.filtered_characters = list(self.characters)
        self.current_character: dict[str, Any] | None = None
        self.character_buttons: dict[str, tk.Button] = {}
        self.images = ImageCache(
            root, Path(data["project_dir"]), data["assets"]
        )

        self.root.title("鸣潮养成助手 · 3.5 中文图鉴版")
        self.root.geometry("1260x820")
        self.root.minsize(980, 680)
        self.root.configure(background=BACKGROUND)
        self._configure_style()
        self._build_ui()
        self._refresh_character_list()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background=BACKGROUND)
        style.configure("Card.TFrame", background=CARD)
        style.configure(
            "Title.TLabel",
            background=BACKGROUND,
            foreground=TEXT,
            font=("TkDefaultFont", 21, "bold"),
        )
        style.configure("Subtle.TLabel", background=BACKGROUND, foreground=MUTED)
        style.configure(
            "Section.TLabel",
            background=CARD,
            foreground=TEXT,
            font=("TkDefaultFont", 12, "bold"),
        )
        style.configure(
            "Character.TLabel",
            background=CARD,
            foreground=TEXT,
            font=("TkDefaultFont", 22, "bold"),
        )
        style.configure("Meta.TLabel", background=CARD, foreground=MUTED)
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            padding=(10, 6),
        )
        style.map("Accent.TButton", background=[("active", "#35528f")])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=18)
        outer.pack(fill="both", expand=True)
        self._build_header(outer)

        content = ttk.Panedwindow(outer, orient="horizontal")
        content.pack(fill="both", expand=True)
        left_card = ttk.Frame(content, style="Card.TFrame", padding=12)
        right_card = ttk.Frame(content, style="Card.TFrame", padding=18)
        content.add(left_card, weight=1)
        content.add(right_card, weight=4)
        self._build_sidebar(left_card)
        self._build_detail(right_card)

        footer = ttk.Frame(outer, style="App.TFrame")
        footer.pack(fill="x", pady=(10, 0))
        self.status_label = ttk.Label(footer, text="", style="Subtle.TLabel")
        self.status_label.pack(side="left")
        ttk.Label(
            footer,
            text="本地图片与离线数据 · 配装为社区建议，并非官方唯一答案",
            style="Subtle.TLabel",
        ).pack(side="right")

    def _build_header(self, parent: tk.Misc) -> None:
        header = ttk.Frame(parent, style="App.TFrame")
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="鸣潮养成助手", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text=f"56 个战斗形态 · 游戏版本 {self.data['meta']['game_version']} · 完全离线",
            style="Subtle.TLabel",
        ).pack(side="left", padx=(14, 0), pady=(9, 0))

        filters = ttk.Frame(header, style="App.TFrame")
        filters.pack(side="right")
        ttk.Label(filters, text="伤害属性", style="Subtle.TLabel").pack(side="left")
        self.element_filter_var = tk.StringVar(value="全部")
        element_box = ttk.Combobox(
            filters,
            textvariable=self.element_filter_var,
            values=ELEMENT_FILTERS,
            state="readonly",
            width=7,
        )
        element_box.pack(side="left", padx=(7, 12))
        element_box.bind("<<ComboboxSelected>>", self._on_filter_change)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        search = ttk.Entry(filters, textvariable=self.search_var, width=25)
        search.pack(side="left")
        search.insert(0, "")
        search.bind("<Escape>", lambda _event: self._clear_filters())
        ttk.Button(filters, text="清空", command=self._clear_filters).pack(
            side="left", padx=(7, 0)
        )

    def _build_sidebar(self, parent: tk.Misc) -> None:
        title_row = ttk.Frame(parent, style="Card.TFrame")
        title_row.pack(fill="x", pady=(0, 8))
        ttk.Label(title_row, text="角色", style="Section.TLabel").pack(side="left")
        self.list_count_label = ttk.Label(title_row, text="", style="Meta.TLabel")
        self.list_count_label.pack(side="right")
        self.character_scroll = ScrollArea(parent)
        self.character_scroll.pack(fill="both", expand=True)

    def _build_detail(self, parent: tk.Misc) -> None:
        hero = ttk.Frame(parent, style="Card.TFrame")
        hero.pack(fill="x", pady=(0, 14))
        self.hero_image = ttk.Label(hero, background=CARD)
        self.hero_image.pack(side="left", padx=(0, 16))
        hero_text = ttk.Frame(hero, style="Card.TFrame")
        hero_text.pack(side="left", fill="x", expand=True)
        name_row = ttk.Frame(hero_text, style="Card.TFrame")
        name_row.pack(fill="x")
        self.name_label = ttk.Label(name_row, text="", style="Character.TLabel")
        self.name_label.pack(side="left")
        self.element_label = tk.Label(
            name_row, text="", borderwidth=0, padx=11, pady=4,
            font=("TkDefaultFont", 10, "bold"),
        )
        self.element_label.pack(side="left", padx=(12, 0))
        self.meta_label = ttk.Label(hero_text, text="", style="Meta.TLabel")
        self.meta_label.pack(anchor="w", pady=(8, 0))

        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        material_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=12)
        build_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=12)
        self.notebook.add(material_tab, text="养成材料")
        self.notebook.add(build_tab, text="配装建议")
        self._build_material_tab(material_tab)
        self.build_scroll = ScrollArea(build_tab)
        self.build_scroll.pack(fill="both", expand=True)

    def _build_material_tab(self, parent: tk.Misc) -> None:
        top = ttk.Frame(parent, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="计算口径", style="Section.TLabel").pack(side="left")
        self.mode_var = tk.StringVar(value="等级 + 技能合计")
        mode_box = ttk.Combobox(
            top,
            textvariable=self.mode_var,
            values=list(MODE_LABELS),
            state="readonly",
            width=18,
        )
        mode_box.pack(side="left", padx=(10, 0))
        mode_box.bind("<<ComboboxSelected>>", self._on_mode_change)
        self.scope_label = ttk.Label(top, text="", style="Meta.TLabel")
        self.scope_label.pack(side="right")

        self.range_controls = ttk.Frame(parent, style="Card.TFrame")
        self.range_controls.pack(fill="x", pady=(10, 10))
        self.level_group = ttk.Frame(self.range_controls, style="Card.TFrame")
        ttk.Label(self.level_group, text="角色等级", background=CARD).pack(side="left")
        allowed = self.data["level_curve"]["allowed_character_levels"]
        self.current_level_var = tk.StringVar(value="1")
        self.target_level_var = tk.StringVar(value="90")
        current = ttk.Combobox(
            self.level_group,
            textvariable=self.current_level_var,
            values=[str(value) for value in allowed[:-1]],
            state="readonly",
            width=4,
        )
        current.pack(side="left", padx=(8, 4))
        ttk.Label(self.level_group, text="→", background=CARD).pack(side="left")
        target = ttk.Combobox(
            self.level_group,
            textvariable=self.target_level_var,
            values=[str(value) for value in allowed[1:]],
            state="readonly",
            width=4,
        )
        target.pack(side="left", padx=(4, 0))
        current.bind("<<ComboboxSelected>>", self._on_range_change)
        target.bind("<<ComboboxSelected>>", self._on_range_change)

        self.skill_group = ttk.Frame(self.range_controls, style="Card.TFrame")
        ttk.Label(self.skill_group, text="五项技能", background=CARD).pack(side="left")
        self.current_skill_var = tk.StringVar(value="1")
        self.target_skill_var = tk.StringVar(value="10")
        skill_current = ttk.Combobox(
            self.skill_group,
            textvariable=self.current_skill_var,
            values=[str(value) for value in range(1, 10)],
            state="readonly",
            width=4,
        )
        skill_current.pack(side="left", padx=(8, 4))
        ttk.Label(self.skill_group, text="→", background=CARD).pack(side="left")
        skill_target = ttk.Combobox(
            self.skill_group,
            textvariable=self.target_skill_var,
            values=[str(value) for value in range(2, 11)],
            state="readonly",
            width=4,
        )
        skill_target.pack(side="left", padx=(4, 10))
        skill_current.bind("<<ComboboxSelected>>", self._on_range_change)
        skill_target.bind("<<ComboboxSelected>>", self._on_range_change)
        self.include_tree_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.skill_group,
            text="计入全部技能树节点",
            variable=self.include_tree_var,
            command=self._render_materials,
        ).pack(side="left")
        self._update_range_controls()

        summary_card = tk.Frame(parent, background="#f6f8fc", padx=12, pady=9)
        summary_card.pack(fill="x", pady=(0, 10))
        self.material_summary = tk.Label(
            summary_card,
            text="",
            background="#f6f8fc",
            foreground="#475467",
            anchor="w",
            justify="left",
        )
        self.material_summary.pack(fill="x")
        self.material_scroll = ScrollArea(parent)
        self.material_scroll.pack(fill="both", expand=True)

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.element_filter_var.set("全部")
        self._apply_filters()

    def _on_search_change(self, *_args: object) -> None:
        self._apply_filters()

    def _on_filter_change(self, _event: tk.Event[tk.Misc]) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        selected_id = self.current_character["id"] if self.current_character else None
        self.filtered_characters = list(
            search_characters(
                self.characters,
                self.search_var.get(),
                self.element_filter_var.get(),
            )
        )
        self._refresh_character_list(selected_id)

    def _refresh_character_list(self, selected_id: str | None = None) -> None:
        self.character_scroll.clear()
        self.character_buttons.clear()
        for character in self.filtered_characters:
            image = self.images.get(character["asset_key"], (58, 58))
            button = tk.Button(
                self.character_scroll.body,
                image=image,
                text=(
                    f"  {character['name']}\n"
                    f"  {character['element']} · {character['weapon_type']}"
                ),
                compound="left",
                anchor="w",
                justify="left",
                relief="flat",
                borderwidth=0,
                padx=8,
                pady=5,
                background=CARD,
                foreground=TEXT,
                activebackground="#e8eef9",
                activeforeground=TEXT,
                font=("TkDefaultFont", 11),
                command=lambda value=character: self._display_character(value),
            )
            button.pack(fill="x", pady=2)
            self.character_buttons[character["id"]] = button

        self.list_count_label.configure(text=f"{len(self.filtered_characters)} 项")
        if self.filtered_characters:
            selected = next(
                (
                    character
                    for character in self.filtered_characters
                    if character["id"] == selected_id
                ),
                self.filtered_characters[0],
            )
            self._display_character(selected)
            self.status_label.configure(
                text=f"找到 {len(self.filtered_characters)} 个战斗形态"
            )
        else:
            self._clear_character("没有符合文字与属性条件的角色")
            self.status_label.configure(text="没有搜索结果；可点击“清空”恢复全部")

    def _display_character(self, character: dict[str, Any]) -> None:
        self.current_character = character
        for character_id, button in self.character_buttons.items():
            button.configure(
                background="#e8eef9" if character_id == character["id"] else CARD
            )
        portrait = self.images.get(character["asset_key"], (116, 116))
        self.hero_image.configure(image=portrait)
        self.name_label.configure(text=character["name"])
        background, foreground = ELEMENT_COLORS[character["element"]]
        self.element_label.configure(
            text=character["element"], background=background, foreground=foreground
        )
        self.meta_label.configure(
            text=(
                f"{character['rarity']} 星 · {character['weapon_type']} · "
                f"{character['role']} · {character['release_version']} 实装"
            )
        )
        self._render_materials()
        self._render_builds()

    def _clear_character(self, message: str) -> None:
        self.current_character = None
        self.hero_image.configure(image="")
        self.name_label.configure(text=message)
        self.element_label.configure(text="", background=CARD)
        self.meta_label.configure(text="")
        self.material_scroll.clear()
        self.build_scroll.clear()
        self.scope_label.configure(text="")
        self.material_summary.configure(text="请调整筛选条件。")

    def _on_mode_change(self, _event: tk.Event[tk.Misc]) -> None:
        self._update_range_controls()
        self._render_materials()

    def _update_range_controls(self) -> None:
        self.level_group.pack_forget()
        self.skill_group.pack_forget()
        mode = MODE_LABELS[self.mode_var.get()]
        if mode in {"level", "total"}:
            self.level_group.pack(side="left", padx=(0, 24))
        if mode in {"skills", "total"}:
            self.skill_group.pack(side="left")

    def _on_range_change(self, _event: tk.Event[tk.Misc]) -> None:
        self._render_materials()

    def _render_materials(self) -> None:
        if self.current_character is None:
            return
        mode = MODE_LABELS[self.mode_var.get()]
        key = self.current_character["materials_key"]
        current_level = int(self.current_level_var.get())
        target_level = int(self.target_level_var.get())
        current_skill = int(self.current_skill_var.get())
        target_skill = int(self.target_skill_var.get())
        include_tree = self.include_tree_var.get()
        try:
            totals = calculate_materials(
                self.data["materials"],
                key,
                mode,
                level_curve=self.data["level_curve"],
                current_level=current_level,
                target_level=target_level,
                current_skill_level=current_skill,
                target_skill_level=target_skill,
                include_skill_tree=include_tree,
            )
        except (ValueError, KeyError, TypeError) as exc:
            self.material_scroll.clear()
            self.scope_label.configure(text="区间无效")
            self.material_summary.configure(text=f"无法计算：{exc}")
            return

        rows = material_rows(self.data["materials"], totals)
        self.material_scroll.clear()
        for index, row in enumerate(rows):
            row_background = "#ffffff" if index % 2 == 0 else "#f8f9fc"
            line = tk.Frame(
                self.material_scroll.body,
                background=row_background,
                padx=10,
                pady=7,
            )
            line.pack(fill="x")
            icon = self.images.get(str(row["asset_key"]), (44, 44))
            tk.Label(line, image=icon, background=row_background).pack(side="left")
            text = tk.Frame(line, background=row_background)
            text.pack(side="left", fill="x", expand=True, padx=(10, 0))
            tk.Label(
                text,
                text=str(row["name"]),
                background=row_background,
                foreground=TEXT,
                font=("TkDefaultFont", 11, "bold"),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                text,
                text=str(row["category"]),
                background=row_background,
                foreground=MUTED,
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                line,
                text=f"× {row['quantity']:,}",
                background=row_background,
                foreground=ACCENT,
                font=("TkDefaultFont", 12, "bold"),
            ).pack(side="right", padx=(12, 4))

        scope_parts: list[str] = []
        if mode in {"level", "total"}:
            scope_parts.append(f"角色 {current_level}→{target_level}")
        if mode in {"skills", "total"}:
            tree_text = "含技能树" if include_tree else "不含技能树"
            scope_parts.append(f"五项技能 {current_skill}→{target_skill}（{tree_text}）")
        self.scope_label.configure(text=" · ".join(scope_parts))

        summary = f"共 {len(rows)} 种材料"
        if mode in {"level", "total"}:
            details = calculate_level_details(
                self.data["materials"],
                self.data["level_curve"],
                key,
                current_level,
                target_level,
            )
            nodes = details["crossed_ascensions"]
            node_text = "、".join(str(value) for value in nodes) if nodes else "无"
            summary = (
                f"精确经验 {details['required_exp']:,}　升级贝币 "
                f"{details['leveling_credits']:,}　促剂建议溢出 "
                f"{details['overflow_exp']:,}　跨越突破节点：{node_text}　"
                f"共 {len(rows)} 种材料"
            )
        self.material_summary.configure(text=summary)

    def _render_builds(self) -> None:
        if self.current_character is None:
            return
        self.build_scroll.clear()
        source_map = {
            source["id"]: source["title"] for source in self.data["meta"]["sources"]
        }
        entries = self.data["builds"][self.current_character["builds_key"]]
        for build in entries:
            title = tk.Label(
                self.build_scroll.body,
                text=build["name"],
                background=CARD,
                foreground=TEXT,
                font=("TkDefaultFont", 16, "bold"),
                anchor="w",
            )
            title.pack(fill="x", pady=(4, 10))

            echo_card = tk.Frame(
                self.build_scroll.body,
                background="#f4f7fc",
                padx=14,
                pady=12,
            )
            echo_card.pack(fill="x", pady=(0, 12))
            main_echo = build["main_echo"]
            echo_image = self.images.get(main_echo["asset_key"], (88, 88))
            tk.Label(echo_card, image=echo_image, background="#f4f7fc").pack(
                side="left", padx=(0, 14)
            )
            echo_text = tk.Frame(echo_card, background="#f4f7fc")
            echo_text.pack(side="left", fill="x", expand=True)
            tk.Label(
                echo_text,
                text="推荐主声骸",
                background="#f4f7fc",
                foreground=MUTED,
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                echo_text,
                text=main_echo["name"],
                background="#f4f7fc",
                foreground=TEXT,
                font=("TkDefaultFont", 15, "bold"),
                anchor="w",
            ).pack(fill="x", pady=(2, 3))
            tk.Label(
                echo_text,
                text=f"{build['echo_set']} · 费用组合 {build['cost_layout']}",
                background="#f4f7fc",
                foreground=ACCENT,
                anchor="w",
            ).pack(fill="x")

            self._build_field("定位", build["role"])
            self._build_field(
                "推荐武器",
                "\n".join(
                    f"{index}. {value}"
                    for index, value in enumerate(build["weapons"], 1)
                ),
            )
            self._build_field(
                "主词条",
                "\n".join(
                    f"{slot}：{value}" for slot, value in build["main_stats"].items()
                ),
            )
            self._build_field("副词条优先级", " ＞ ".join(build["substat_priority"]))
            self._build_field("共鸣效率目标", build["energy_regen_target"])
            self._build_field("技能升级优先级", " ＞ ".join(build["skill_priority"]))
            self._build_field("使用说明", build["notes"])
            source_titles = [source_map[source_id] for source_id in build["source_ids"]]
            self._build_field(
                "资料说明",
                f"游戏版本 {build['game_version']} · 社区建议 · "
                f"来源：{'、'.join(source_titles)}",
                muted=True,
            )

    def _build_field(self, label: str, value: str, *, muted: bool = False) -> None:
        block = tk.Frame(self.build_scroll.body, background=CARD, pady=5)
        block.pack(fill="x")
        tk.Label(
            block,
            text=label,
            background=CARD,
            foreground=TEXT,
            font=("TkDefaultFont", 11, "bold"),
            anchor="nw",
            width=14,
        ).pack(side="left")
        tk.Label(
            block,
            text=value,
            background=CARD,
            foreground=MUTED if muted else "#344054",
            justify="left",
            anchor="nw",
            wraplength=720,
        ).pack(side="left", fill="x", expand=True)


def check_data() -> int:
    """校验本地 JSON 和图片引用，不创建 GUI。"""
    try:
        data = load_all_data()
    except DataValidationError as exc:
        print(f"数据检查失败：{exc}", file=sys.stderr)
        return 1
    print(
        f"数据检查通过：{len(data['characters'])} 个战斗形态、"
        f"{len(data['materials']['items'])} 种材料、"
        f"{len(data['assets'])} 张本地图片，游戏版本 {data['meta']['game_version']}。"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="鸣潮中文角色养成与配装助手")
    parser.add_argument(
        "--check-data", action="store_true", help="只校验本地数据和图片引用"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check_data:
        return check_data()
    if Image is None or ImageTk is None:
        print("缺少 Pillow：请先执行 pip install -r requirements.txt", file=sys.stderr)
        return 1
    try:
        data = load_all_data()
    except DataValidationError as exc:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("数据加载失败", str(exc), parent=root)
            root.destroy()
        except tk.TclError:
            print(f"数据加载失败：{exc}", file=sys.stderr)
        return 1
    root = tk.Tk()
    WuwaPlannerApp(root, data)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
