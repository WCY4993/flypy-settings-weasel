"""Expand the existing table in place, retaining its data and event handlers."""
import tkinter as tk
from tkinter import ttk


def first_row(tree):
    children = tree.get_children()
    tree.yview_moveto(0)
    if children:
        tree.selection_set(children[0])
        tree.focus(children[0])
        tree.see(children[0])


class TableExpander:
    def __init__(self, tree):
        self.tree, self.frame = tree, tree.master
        self.root = tree.winfo_toplevel()
        self.active = False
        self.layouts = []
        self.tooltip = None
        self.tooltip_timer = None
        size = max(18, round(float(tree.tk.call('tk', 'scaling')) * 14))
        background = ttk.Style(tree).lookup('TFrame', 'background') or '#f0f0f0'
        self.icon = tk.Canvas(self.frame, width=size, height=size, background=background,
                              highlightthickness=1, highlightbackground=background,
                              highlightcolor='#0078d4', cursor='hand2', takefocus=True)
        horizontal = next((w for w in self.frame.winfo_children()
                           if isinstance(w, ttk.Scrollbar) and str(w.cget('orient')) == 'horizontal'), None)
        if horizontal is not None and horizontal.winfo_manager() == 'grid':
            row = int(horizontal.grid_info()['row'])
            self.icon.grid(row=row, column=1, sticky='se')
        else:
            self.icon.place(relx=1, rely=1, anchor='se')
        self.size = size
        self.draw()
        self.icon.bind('<Button-1>', self.toggle)
        self.icon.bind('<Return>', self.toggle)
        self.icon.bind('<space>', self.toggle)
        self.icon.bind('<Enter>', self.hover)
        self.icon.bind('<Leave>', self.hide_tip)
        self.icon.bind('<Destroy>', self.hide_tip)
        self.escape_binding = self.root.bind('<Escape>', self.escape, add='+')

    def draw(self):
        self.icon.delete('all')
        scale = self.size / 20
        lines = ([(4,8,4,4,8,4),(12,4,16,4,16,8),(16,12,16,16,12,16),(8,16,4,16,4,12)]
                 if not self.active else
                 [(3,7,7,7,7,3),(13,3,13,7,17,7),(17,13,13,13,13,17),(7,17,7,13,3,13)])
        for points in lines:
            self.icon.create_line(*[x*scale for x in points], fill='#505050', width=max(1,round(scale)))

    def hover(self, _event=None):
        self.hide_tip()
        self.tooltip_timer = self.icon.after(450, self.show_tip)

    def show_tip(self):
        self.tooltip_timer = None
        if not self.icon.winfo_exists():
            return
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.withdraw(); self.tooltip.overrideredirect(True)
        text = '還原表格（Esc）' if self.active else '放大表格'
        ttk.Label(self.tooltip, text=text, padding=6).pack()
        self.tooltip.update_idletasks()
        x = min(self.icon.winfo_rootx(), self.root.winfo_screenwidth()-self.tooltip.winfo_reqwidth()-8)
        y = max(0, self.icon.winfo_rooty()-self.tooltip.winfo_reqheight()-4)
        self.tooltip.geometry(f'+{x}+{y}'); self.tooltip.deiconify()

    def hide_tip(self, _event=None):
        if self.tooltip_timer:
            self.icon.after_cancel(self.tooltip_timer); self.tooltip_timer = None
        if self.tooltip:
            self.tooltip.destroy(); self.tooltip = None

    def toggle(self, _event=None):
        self.hide_tip()
        if self.active:
            self.restore()
        else:
            self.expand()
        return 'break'

    def expand(self):
        other = getattr(self.root, '_expanded_table', None)
        if other and other is not self:
            other.restore()
        self.old_state, self.old_geometry = self.root.state(), self.root.geometry()
        self.layouts = []
        widget = self.frame
        while widget is not self.root:
            parent = widget.master
            if widget.winfo_manager() == 'pack':
                layout = [(w, dict(w.pack_info())) for w in parent.pack_slaves()]
                hidden = [w for w, _ in layout if w is not widget and not getattr(w, '_table_zoom_keep', False)]
                if hidden:
                    self.layouts.append(layout)
                    for w in hidden: w.pack_forget()
            if isinstance(parent, ttk.Notebook):
                self.notebook, self.notebook_page = parent, str(widget)
                self.tab_binding = parent.bind('<<NotebookTabChanged>>', self.tab_changed, add='+')
            widget = parent
        self.active = True
        self.root._expanded_table = self
        self.root.state('zoomed')
        self.draw()

    def restore(self):
        if not self.active:
            return
        self.hide_tip()
        if hasattr(self, 'tab_binding'):
            self.notebook.unbind('<<NotebookTabChanged>>', self.tab_binding)
            del self.tab_binding
        for layout in reversed(self.layouts):
            existing = [(w, info) for w, info in layout if w.winfo_exists()]
            for w, _ in existing: w.pack_forget()
            for w, info in existing: w.pack(**info)
        self.layouts = []
        self.root.state(self.old_state)
        if self.old_state == 'normal': self.root.geometry(self.old_geometry)
        self.active = False
        self.root._expanded_table = None
        self.draw()

    def tab_changed(self, _event=None):
        if self.active and self.notebook.select() != self.notebook_page:
            self.restore()

    def escape(self, _event=None):
        # Do not consume Esc from an editor dialog owned by this window.
        if self.active:
            self.restore()
            return 'break'


def install_table_expanders(widget):
    for child in widget.winfo_children():
        if isinstance(child, ttk.Treeview) and child.cget('columns') and not hasattr(child, 'expander'):
            child.expander = TableExpander(child)
        else:
            install_table_expanders(child)
