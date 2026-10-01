"""Detects a relax_once trial that settled into a globally INSIDE-OUT
equilibrium relative to where it started -- a real failure mode
multi_trial_inflater's own pressure-calibration search can otherwise
mistake for an ordinary "needs less pressure" reading.

Diagnosed 2026-09-30 on tetrahedron.poly: at Level 2+, some seeds have a
genuine, numerically-converged but globally-inverted equilibrium at LOW
pressure (signed volume flips sign, stretch % roughly FLAT across a wide
low-pressure range instead of scaling with pressure -- the hallmark of a
spurious branch, not real physics) that is entirely separate from the
real, correctly-oriented equilibrium reachable only at meaningfully
higher pressure. Without this check, such a trial reads as an ordinary
sane-but-over-target trial (RMS stretch usually well above target), which
the bracket search responds to by LOWERING pressure -- driving it deeper
into the spurious branch and guaranteeing the correct one is never found.
A burst of real pressure at the start of Level 0 (tried and rejected,
2026-09-30 -- see git history) had no effect: Level 0/1 were already
orientation-consistent in every case tested, and the flip reproduced
fresh, inside Level 2's own relax_once call, regardless."""
from .stretchy_mesh import mesh_volume


class InsideOutChecker:
    """Compares a trial's own signed enclosed volume (mesh_volume) against
    a FIXED reference configuration's, both for the SAME faces -- a sign
    flip between them means the mesh has turned inside out relative to
    where it started. Built once per calibration search (the reference is
    the search's own starting `positions`, before any trial has run) and
    reused across every trial, so the reference volume is computed only
    once."""

    # Below this magnitude, the reference configuration's own volume is too close to zero (an
    # open/boundary-having net, or a not-yet-embedded flat/degenerate shape) for its SIGN alone
    # to mean anything -- is_inside_out reports False (can't tell) rather than risking a false
    # positive off numerical noise. A closed, non-degenerate starting shape's volume is never
    # this small in practice.
    MIN_REFERENCE_VOLUME_MAGNITUDE = 1e-6

    def __init__(self, reference_positions, faces):
        self._faces = faces
        self._reference_volume = mesh_volume(reference_positions, faces)

    def is_inside_out(self, positions):
        """True iff `positions`' own signed volume (over the SAME faces
        this checker was built from) has flipped sign relative to the
        reference. Always False when the reference volume's own
        magnitude is under MIN_REFERENCE_VOLUME_MAGNITUDE -- an
        open/boundary-having net has no reliable "inside out" notion via
        enclosed volume alone, so this never flags one."""
        if abs(self._reference_volume) < self.MIN_REFERENCE_VOLUME_MAGNITUDE:
            return False
        current_volume = mesh_volume(positions, self._faces)
        return (current_volume < 0) != (self._reference_volume < 0)
