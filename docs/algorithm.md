# Force-directed relaxation of stretchy polyhedral meshes

## Abstract

We describe a method for realizing a closed or open, combinatorially-
specified polyhedral net — one whose faces may share more than one edge
with a neighbor, precluding a rigid flat-faced embedding — as a
physically plausible, inflated 3D shape. The method has two stages: (1) a
random-start spring relaxation that recovers a well-separated, roughly
edge-length-correct embedding with no notion of pressure or face
orientation, and (2) an explicit, pressure-driven force relaxation that
inflates the embedding, subject to a linear edge spring, an all-pairs
short-range repulsion, and a per-face outward pressure force, walked in
small steps to avoid the spurious equilibria a Newton-style solver can
converge to. A calibration procedure estimates,
for a given mesh, the pressure that yields a target RMS edge stretch,
exploiting an empirical near-linear relationship between pressure and
total rest surface area.

## 1. Problem statement

**Input.** A set of faces $F = \{f_1, \dots, f_m\}$, each a cyclic list
of vertex ids, together forming an oriented, manifold mesh, closed or
open: every undirected edge is shared by AT MOST two faces, traversed in
opposite directions where shared, by the winding convention (§2). An
edge with no second face is a free boundary edge, not an error. No
coordinates are given.

**Goal.** Produce vertex positions $p_v \in \mathbb{R}^3$ such that (a)
every edge's length is close to a common rest length $\ell_0$
(low *stretch*), (b) the mesh is not self-intersecting, and (c) the
enclosed volume is larger than the flat (zero-volume) configuration, as
if the net had been inflated like a balloon or a stuffed toy.

**Why this is nontrivial.** If two faces share three or more
non-collinear vertices, both are constrained to the single plane those
points determine — there is no dihedral fold that keeps them flat, rigid,
and distinct. A rigid hinge-and-fold-angle model (as used for ordinary,
one-shared-edge nets) is therefore inapplicable in general; the mesh must
be allowed to stretch.

## 2. Mesh representation and winding convention

Faces are stored as vertex-id loops (an "indexed face set", as in an
`.obj` file); adjacency is implicit in shared vertex ids, so a face pair
sharing multiple edges requires no special-casing. Every face is wound
counterclockwise as seen from outside the intended solid: for every edge
$(v, w)$ shared by two faces, one face's loop contains the directed edge
$v \to w$ and the other contains $w \to v$; an edge referenced by only one
face is a free boundary edge. This is verified at load time by checking
that no directed edge appears more than once.

## 3. Stage 1: random-start spring relaxation

### 3.1 Triangulation precondition

An unbraced polygon face (e.g. a plain quadrilateral) under edge springs
alone is a *mechanism* — free to flex, like an unbraced rectangular
frame — not a rigid structure, and gives spring relaxation no
well-defined shape to settle into. Each face is therefore fan-triangulated
about its own centroid before this stage runs, adding diagonal bracing.

### 3.2 Initialization

Each vertex is assigned an independent, uniformly random position in
$[-s/2, s/2]^3$ (all coordinates i.i.d.), with no relation to
$\ell_0$ or the mesh topology. This is not a meaningful embedding — it
supplies only enough spatial separation for the subsequent relaxation to
pull into one.

### 3.3 Force

Each edge $(a, b)$ contributes a Hooke's-law spring force along its own
direction, proportional to relative stretch:

$$
\mathbf{f}_{a\to b} = \frac{\lVert p_b - p_a\rVert - \ell_0}{\ell_0}\,
\hat{u}_{ab}, \qquad \hat u_{ab} = \frac{p_b - p_a}{\lVert p_b - p_a\rVert}
$$

applied as $+\mathbf f_{a\to b}$ on $b$ and $-\mathbf f_{a\to b}$ on $a$.
No pressure is present at this stage. This is the same plain linear
spring force Stage 2 (§4.1) now also uses.

### 3.4 Orientation and repulsion

A pure spring force has no notion of "outward": the relaxation is exactly
as likely to converge to a globally inside-out mesh, or a mesh with some
faces oriented one way and others the other, as a right-side-out one.
No global correction is applied; orientation is left exactly as the
physics settles it.

Stage 1 also applies an all-pairs, short-range, inverse-square repulsion
between every vertex (not just edge-connected ones) — the only force here
with any opinion about vertex pairs with no edge between them — keeping
the initial random cloud from leaving vertices piled on top of each other
before the spring network can spread them out. Each vertex's own
repulsion contribution is discarded whenever it points *inward* — its dot
product against that vertex's own outward normal (defined from incident
face winding, §4.1's face-normal convention) is negative — rather than
letting repulsion push a vertex further into a local fold.

Every fixed number of steps, every vertex also receives a single bounded
displacement kick along its own outward normal ("jiggle"), meant to jog a
locally stuck or folded region loose; it is gated to never coincide with
a convergence check, so a genuinely settled mesh is still reported
converged without waiting for a kick to re-settle first.

## 4. Stage 2: pressure-driven inflation

### 4.1 Force

Each edge contributes the same plain Hooke's-law linear spring force as
Stage 1 (§3.3), in terms of relative stretch
$s = (\lVert p_b-p_a\rVert - \ell_0)/\ell_0$:

$$
\mathbf f_{a\to b} = s\,\hat u_{ab},
$$

equivalent to a potential energy $U(s) = \tfrac12 s^2$ per edge. An
earlier version of this force law added a cubic hardening term,
$s + c\,s^3$ with $c = 0.5$ (potential $U(s) = \tfrac12 s^2 + \tfrac{c}{4}s^4$),
motivated by a genuine instability: a plain linear spring's restoring
force grows only linearly with stretch, while pressure's own push grows
with face area ($\sim \ell^2$), so past some critical pressure no
equilibrium exists at all and the mesh inflates without bound. Real
rubber does not have this problem because its stress-strain curve
stiffens sharply once its polymer chains run out of slack at large
stretch (the same mechanism behind the two-balloon experiment's
counter-intuitive behavior); the cubic term was the direct model
analogue, small near $s=0$ (recovering the linear spring's fast
near-rest response) and dominant for $s \gtrsim 1$. That term was
removed again (2026-10-01, explicit — "just use linear springs"), so
the force law above is now plain Hooke's law throughout both stages.
§4.4 discusses what the hardening term bought, why it was removed, and
what to watch for if the plain linear form stops being sufficient.

Each face additionally contributes a real per-face outward force,

$$
\mathbf{F}_{\text{face}} = P \cdot \mathbf{A},\qquad
\mathbf A = \tfrac12 \sum_i p_i \times p_{i+1}
$$

($\mathbf A$: the face's area-weighted outward normal via Newell's
method, summed over its own — possibly non-planar — vertex loop), split
evenly across its vertices. A face may be flagged to receive no pressure
force at all (an "open" wedge whose outer edge is not glued to another
polygon) while remaining fully present for the spring, repulsion, and
convergence terms. The same short-range all-pairs repulsion from Stage 1
(§3.4) continues to act here, weak enough relative to the spring's own
stiffness that it only meaningfully affects vertices already close
together; it may be restricted to a fixed subset of vertices to keep its
$O(n^2)$ cost from growing as the mesh is subdivided.

### 4.2 Integration

The net force $\mathbf f_v$ on every vertex is computed and the whole
mesh advanced by one explicit step,

$$
p_v \leftarrow p_v + \Delta t\, \mathbf f_v,\qquad \Delta t = \Delta t_{\max}
$$

a fixed fraction of the mesh's own rest edge length (currently 0.05 for
Stage 2, 0.1 for Stage 1 — even though both stages use the same linear
spring force, each stage's full force mix, including repulsion gating,
bursts, and pressure, tolerates a different step size before
overshooting into an undamped oscillation, verified directly by
bisecting the largest stable value on reproducing cases). $\Delta t$ was previously also divided by
the current largest force, an adaptive term that shrunk the step when
force was large; that term has been permanently removed (re-evaluated
and re-declined), leaving a flat step size. Either way, this explicit
walk is a deliberate choice over a Newton/least-squares solver:
re-linearizing the whole system and jumping to the linearized root can
land on a distant, spurious equilibrium — e.g. a doubled-size,
heavily-stretched solution, or a uniform near-zero-volume implosion —
that is a genuine root of the same force-balance equations but one a
physical process starting from the current state would never actually
reach. Small explicit steps cannot skip over the physically-reachable
equilibrium this way.

### 4.3 Convergence

The relaxation checks for convergence only once every $N$ steps (currently
$N=200$), rather than every step: the worst vertex's own displacement
since the last check is compared against $N \cdot g_{\text{tol}}$, the
same per-step rate scaled up to the longer window. (This, and comparing
displacement rather than the largest per-vertex force, are both changes
currently under active evaluation; either can be reverted to the
force-every-step comparison an earlier version used.) A run also ends if
`stop_event` is set or a hard step-count cap is reached — the family of
Platonic solids and other test nets settle in anywhere from tens to a
few thousand steps at typical target stretches, so the cap is set high
enough (currently 50,000) to be a genuine backstop, not a normal exit
path. An earlier plateau/stall criterion (declaring convergence once the
RMS stretch's range over a long window stopped moving, to catch a
persistent numerical wobble or a very slow tail that never formally
satisfies the tolerance) has been removed entirely: it used a threshold
independent of $g_{\text{tol}}$, so at a sufficiently tight tolerance it
could end a run well before the tolerance was actually satisfied.

### 4.4 Why no volume or target term, and the status of the stretch limit

A plain Hooke's-law spring cannot support unbounded pressure at all
(§4.1 above) — past some critical pressure for a given stretch target,
no linear-spring equilibrium exists. Two additions were tried to paper
over this and both were rejected as fixing the wrong layer: a
target/reference-volume pressure term (which silently follows wherever
the mesh currently sits, compounding stretch across repeated
subdivide-then-inflate cycles) and a per-edge soft stretch limit (which
forces an equilibrium to exist even at a badly-chosen pressure, rather
than choosing pressure well in the first place).

A third approach — a cubic hardening term added directly to the spring's
own force law ($s + c\,s^3$, by analogy with real rubber's
strain-stiffening at large stretch; see §4.1's earlier version) — was
tried, adopted, and ultimately removed again (2026-10-01, explicit —
"just use linear springs"), leaving plain Hooke's law throughout. Unlike
the two rejected additions above, the hardening term was a literal,
physically-motivated addition to the force law itself, not a clamp or a
bolted-on limit — but it added a tuning parameter ($c$) and nonlinearity
whose benefit, in practice, pressure calibration (§5) alone already
captured: calibration picks a pressure appropriate to the target stretch
and mesh, which for every net tested so far stays comfortably within the
plain linear spring's own stable range. If a future net or target pushes
close to or past that critical pressure, the hardening term above is the
fix to reintroduce — not a volume/target term or a stretch clamp.

## 5. Pressure calibration

Required pressure is not comparable across nets by raw magnitude — it
scales with total surface area, not vertex or face count. Given a target
RMS stretch $\sigma^*$ (percent of rest length), an initial pressure
estimate is formed from the mesh's total rest area $\mathcal A$
(computed in closed form from regular-polygon geometry, or via Heron's
formula per triangle for non-uniform rest lengths):

$$
P_0 = k \cdot \frac{\sigma^{*}}{100 \cdot \mathcal A}
$$

with $k$ an empirical constant obtained by bisecting, on each of the five
Platonic solids, the pressure giving 10% RMS stretch: the product
$P\cdot\mathcal A$ lands in a narrow band across all five despite raw
$P$ varying more than tenfold. $P_0$ is then refined by relaxing at that
pressure and rescaling by $\sigma^{*}/\sigma_{\text{achieved}}$ (clamped
to a bounded ratio per iteration), repeating a small, fixed number of
times. Because this assumes stretch increases monotonically with
pressure — false for at least one real net topology, where added faces
sharing an edge produce the opposite response — the procedure retains
whichever trial came closest to $\sigma^*$ rather than only the final
one, so a topology violating the assumption does not diverge chasing a
target that is moving away from it.

When a mesh has already been calibrated at another subdivision level,
that history gives a better starting guess than $P_0$ alone: since
subdivision quarters every triangle (roughly halving edge length) without
changing total rest area, matching the same target stretch at the next
level empirically takes about double the pressure. The search is
therefore seeded from whichever prior level's own recorded
$(\text{pressure}, \text{achieved stretch})$ pair landed *closest* to the
new target, scaled by $2^{\Delta\text{level}}$ — not a
`target / achieved` rescale of that pair, which explodes when the prior
achieved stretch was ~0 (pressure genuinely had no effect at that level,
e.g. before a later subdivision gives the mesh real degrees of freedom).
Either way this only reduces the number of trials needed, never changes
the final answer.

If several consecutive rescaling trials land within a tiny tolerance of
each other despite pressure being rescaled substantially each time, the
mesh is judged unresponsive to pressure at this level (e.g. two
identical, oppositely-wound faces whose pressure contributions cancel
exactly) and the search stops rather than escalating pressure without
bound; a later level's own starting guess then excludes this level's
pressure from its history.

## 6. Incremental subdivision

The mesh may be refined without re-solving from scratch: each triangle is
quartered by connecting edge midpoints (a "triforce" split). A new
vertex's position is interpolated from its parent edge's current (already
possibly stretched) endpoints, so inflation already achieved carries
forward; its rest length, in contrast, is derived analytically from the
*original*, flat unit-edge reference geometry (exact halving, or the
midsegment theorem for a quartering's new internal edge) rather than from
current positions — so the target shape a further relaxation is pulled
toward does not drift as resolution increases, letting repeated
inflate-then-subdivide cycles converge toward one consistent target
rather than each level chasing a shape defined by whatever stretch
happened to exist at the moment it was created.

## 7. Complexity and practical notes

Per-step cost is dominated by $O(V + E + F)$ vectorized array operations
(edges and same-sided faces batched via precomputed index arrays), a few
hundredths of a second per evaluation for a mesh of a few hundred
vertices. No global spatial search, cache, or precomputed solve is
involved: every session begins from fresh random noise and reaches its
final shape entirely through the local force iteration described above.
