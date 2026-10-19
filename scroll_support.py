"""Route wheel events in a scrollable settings pane before widget defaults."""

def bind_settings_wheel(canvas, content, scrollbar=None):
    # A private, first bindtag avoids bind_all and stops spinbox/combobox
    # defaults from changing values when the user intends to scroll the pane.
    tag = 'SettingsWheel_' + str(canvas)
    remainder = 0
    canvas.configure(yscrollincrement=24)

    def wheel(event):
        nonlocal remainder
        delta = getattr(event, 'delta', 0)
        if getattr(event, 'num', None) in (4, 5):
            delta = 120 if event.num == 4 else -120
        if remainder * delta < 0:
            remainder = 0
        remainder += delta
        steps = int(remainder / 120)
        remainder -= steps * 120
        if steps and canvas.yview() != (0.0, 1.0):
            canvas.yview_scroll(-steps * 3, 'units')
        return 'break'

    def attach(widget):
        tags = widget.bindtags()
        if tag not in tags:
            widget.bindtags((tag,) + tags)
        for child in widget.winfo_children():
            attach(child)

    for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
        canvas.bind_class(tag, event, wheel)
    attach(canvas)
    attach(content)
    if scrollbar is not None:
        attach(scrollbar)
