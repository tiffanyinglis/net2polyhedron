"""ui: small, generic Tkinter/matplotlib widgets and rendering helpers
shared by the apps in src/apps/ -- not specific to any one app, and not
net-folding domain logic (that lives in src/utils/).

Modules:
  tooltip        -- Tooltip: generic hover-tooltip for any Tk widget
  cullable_face  -- _CullableFace: a Poly3DCollection that backface-culls
                    itself for a closed convex solid (see its docstring)
"""
