"""Polygon-side-count -> color palette (triangle green, gradually through blue to purple as `n`
grows) -- shared by interactive_builder_app's own palette/shape rendering, interactive_
inflater_app's "Polygon-specific" mode, and inflate_polyhedron_app's own "Polygon-specific" Colour
mode (2026-10-01, explicit bug report: "Polygon-specific colouring is wrong. It should use the
colour scheme in interactive_inflater, where triangles are green, and as n increases, it
gradually goes to blue then purple"). Moved out of interactive_builder_app/app.py (where it
originally lived alone) rather than having inflate_polyhedron_app import that whole Tkinter app
just for this table -- those two apps have otherwise always stayed decoupled (see the net-fold-
project skill's own untouchable.md); per this project's "shared code should be moved to utils"
convention, this is exactly that case.
"""
import colorsys

POLYGON_NS = [3, 4, 5, 6, 7, 8]

# One FIXED color per polygon type (never per-instance), as an explicit (hue_deg, lightness,
# saturation) table rather than a formula swept evenly across all 6 -- per-color tweaks over
# time left hues unevenly spaced, so an explicit table reads more clearly than exceptions
# bolted onto a formula. Order matches POLYGON_NS (triangle..8-gon); base lightness/saturation
# is 0.50/0.65 except where a color's own tweak departs from it.
_POLYGON_HLS = [
    (136, 0.38, 0.50),  # triangle: green (darker/less saturated)
    (172, 0.40, 0.65),  # square: turquoise, darkened a bit
    (208, 0.50, 0.65),  # pentagon: blue
    (244, 0.58, 0.65),  # hexagon: darker blue, lightened a bit
    (262, 0.50, 0.65),  # 7-gon: violet
    (280, 0.50, 0.65),  # 8-gon: purple
]


def hls_hex(hue_deg, lightness, saturation):
    r, g, b = colorsys.hls_to_rgb(hue_deg / 360.0, lightness, saturation)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


POLYGON_COLORS = {n: hls_hex(*hls) for n, hls in zip(POLYGON_NS, _POLYGON_HLS)}
