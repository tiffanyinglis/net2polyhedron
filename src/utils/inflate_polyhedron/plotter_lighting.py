"""Shared PyVista lighting rig for rendering an inflate_polyhedron mesh -- used by both
inflate_polyhedron_app and interactive_inflater_app (2026-10-01, explicit: "make sure they are
using shared code whenever possible. shared code should be moved to utils" -- previously
duplicated verbatim, including this entire tuning-history comment, in both apps' own app.py).

Explicit 3-light camera-relative rig, replacing a plotter's own default headlight kit (a
headlight lights a convex surface almost uniformly regardless of smooth_shading, so there's no
real contrast to shade with). `light_type="camera light"` tracks the camera automatically as the
user rotates/pans -- "camera light" space has the camera at (0, 0, 1) looking at the origin.

KEY_LIGHT/FILL_LIGHT sit at a deliberate off-axis angle (2026-10-01, explicit bug report: "every
face, regardless of how it's subdivided and inflated, all get one phong lighting... shouldn't
the individual subdivisions get different lighting/shading"). Diagnosed, NOT a shading-
computation bug: VTK's per-vertex normals and Phong interpolation were already both correct
(confirmed by direct inspection -- real normal variation up to 50+ degrees within one subdivided
macro face, and an isolated high-res render of one face showing a clean gradient). The ORIGINAL
position (0.55, 0.7, 0.85) was simply still too close to the camera's own view axis -- lighting
a roughly dome-shaped inflated face from nearly the same angle it's being VIEWED from produces a
radially-symmetric "glow" (bright center fading evenly toward the rim in every direction) rather
than a left-to-right/top-to-bottom directional gradient, which at a small panel size reads as
"basically one flat shade plus a highlight blob" even though the underlying per-vertex shading
is genuinely varying. Moving the light to a real side/grazing angle makes the SAME underlying
curvature produce an obviously directional, clearly-per-subdivision-varying gradient instead.

HEADLIGHT added (2026-10-01, explicit: "it's not actually brighter. maybe what i want is for
the light source to be more from the viewer's eyes" -- after bumping MATERIAL_DIFFUSE/
MATERIAL_SPECULAR alone didn't read as brighter). Root cause: KEY/FILL's own off-axis angle
means the diffuse dot-product against a camera-FACING surface is small regardless of the
material's diffuse coefficient -- raising the coefficient alone can't fix a weak incidence
angle. HEADLIGHT sits essentially AT the camera, so camera-facing surfaces get real direct
illumination. Kept separate from, not a replacement for, KEY/FILL -- those still provide the
off-axis directional gradient that makes individual subdivisions read as differently-shaded;
HEADLIGHT only adds overall brightness on top.

Positions/intensities below are the current, several-times-retuned values (each explicit
request, same day: "make things a tad brighter" / "make the phong lighting brighter" / "i still
want the diffuse and phong lighting to be brighter" / "lower diffuse and specular to before" /
"lower ambient" / "can you move the phong lights closer?" (clarified as "Narrow the angle a
bit" -- position DISTANCE is a no-op for a directional "camera light", confirmed by rendering
with the position scaled to 30% of its length and diffing pixel output identical, so KEY_LIGHT_
POSITION/FILL_LIGHT_POSITION were instead blended 30% of the way toward (0, 0, 1), narrowing
their off-axis angle rather than their distance) / "ok now bump up the key_light, fill_light,
headlight" / "undo the bumping for fill light and key light" / "ok looks now. now dim all the
key/fill/headlights a bit" / "drop key light to 0.4" / "change fill_light to 0.2") -- do not
re-derive these from the reasoning above, which only explains the POSITIONS/mechanism, not the
final tuned intensities."""
import pyvista as pv

__all__ = [
    "SMOOTH_SHADING", "MATERIAL_AMBIENT", "MATERIAL_DIFFUSE", "MATERIAL_SPECULAR",
    "MATERIAL_SPECULAR_POWER", "KEY_LIGHT_POSITION", "KEY_LIGHT_INTENSITY",
    "FILL_LIGHT_POSITION", "FILL_LIGHT_INTENSITY", "HEADLIGHT_POSITION", "HEADLIGHT_INTENSITY",
    "setup_plotter_lighting",
]

SMOOTH_SHADING = False
MATERIAL_AMBIENT = 0.18
MATERIAL_DIFFUSE = 0.85
MATERIAL_SPECULAR = 0.5
MATERIAL_SPECULAR_POWER = 20

KEY_LIGHT_POSITION = (0.9, 0.15, 0.1)
KEY_LIGHT_INTENSITY = 0.3
FILL_LIGHT_POSITION = (-0.7, -0.2, 0.7)
FILL_LIGHT_INTENSITY = 0.15

HEADLIGHT_POSITION = (0.0, 0.0, 1.0)
HEADLIGHT_INTENSITY = 0.75


def setup_plotter_lighting(plotter):
    """Replaces `plotter`'s own default light kit with the explicit KEY/FILL/HEADLIGHT
    camera-relative rig. Must be called after every `pv.Plotter(...)` construction AND after
    every `plotter.clear()` -- clear() calls remove_all_lights() internally, so a one-time setup
    right after construction is silently undone by the first real draw."""
    plotter.remove_all_lights()
    key_light = pv.Light(light_type="camera light", intensity=KEY_LIGHT_INTENSITY)
    key_light.position = KEY_LIGHT_POSITION
    plotter.add_light(key_light)
    fill_light = pv.Light(light_type="camera light", intensity=FILL_LIGHT_INTENSITY)
    fill_light.position = FILL_LIGHT_POSITION
    plotter.add_light(fill_light)
    headlight = pv.Light(light_type="camera light", intensity=HEADLIGHT_INTENSITY)
    headlight.position = HEADLIGHT_POSITION
    plotter.add_light(headlight)
