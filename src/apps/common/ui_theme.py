"""Shared Tkinter/matplotlib look-and-feel constants, used by every app in
src/apps/ that has a net picker, a status line, or a 3D plot -- kept here
(rather than defined once and imported from whichever app happened to
define them first) so no app depends on another app's module.
"""

DISABLED_SUFFIX = "  (not computed)"
COMPUTE_TOOLTIP = ("Solves the fold for every net that hasn't been computed "
                    "yet.\nThis may take a few minutes -- larger nets (like "
                    "the icosahedron)\ncan take up to a minute each.")

STATUS_COLORS = {
    "info": "#3b6ea5",
    "success": "#1a7f37",
    "error": "#cf222e",
    "warn": "#9a6700",
}

# Mirrors sv_ttk's own background colors (theme/{light,dark}.tcl -bg) so a
# matplotlib plot doesn't look like a mismatched white box dropped onto a
# dark window. fg/grid are the axis lines, ticks, labels and gridlines --
# these need to flip to a light color in dark mode to stay visible against
# -bg.
PLOT_THEME = {
    "light": {"bg": "#fafafa", "fg": "#1c1c1c", "grid": (0, 0, 0, 0.1)},
    "dark": {"bg": "#1c1c1c", "fg": "#e0e0e0", "grid": (1, 1, 1, 0.15)},
}


# A high-variety, fixed face-color palette (two named 8-color sets),
# deliberately more visually distinct than a qualitative colormap like
# Set2, which has only 8 base (fairly similar, muted) hues and blends
# washed-out intermediate tones once a net has more faces than that.
# Cycles (via modulo where it's used) for a net with more faces than
# colors (16 here).
_BRIGHT = ["#003a7d", "#008dff", "#ff73b6", "#c701ff",
           "#4ecb8d", "#ff9d3a", "#f9e858", "#d83034"]
_ALTERNATING_LIGHT_DARK = ["#8fd7d7", "#00b0be", "#ff8ca1", "#f45f74",
                           "#bdd373", "#98c127", "#ffcd8e", "#ffb255"]
FACE_COLORS = _BRIGHT + _ALTERNATING_LIGHT_DARK
