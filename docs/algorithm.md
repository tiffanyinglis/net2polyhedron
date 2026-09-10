# Force-directed relaxation of stretchy polyhedral meshes

## Abstract

We describe a method for realizing a closed, combinatorially-specified
polyhedral net — one whose faces may share more than one edge with a
neighbor, precluding a rigid flat-faced embedding — as a physically
plausible, inflated 3D shape. The method has two stages: (1) a
random-start spring relaxation that recovers a well-separated, roughly
edge-length-correct embedding with no notion of pressure or face
orientation, and (2) an explicit, pressure-driven force relaxation that
inflates the embedding, subject only to Hooke's-law edge springs and a
per-face outward pressure force, walked in small steps to avoid the
spurious equilibria a Newton-style solver can converge to. A calibration
procedure estimates, for a given mesh, the pressure that yields a target
RMS edge stretch, exploiting an empirical near-linear relationship
between pressure and total rest surface area.

## 1. Problem statement

**Input.** A set of faces $F = \{f_1, \dots, f_m\}$, each a cyclic list
of vertex ids, together forming a closed, oriented, manifold mesh: every
undirected edge is shared by exactly two faces, traversed in opposite
directions by the winding convention (§2). No coordinates are given.

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
$v \to w$ and the other contains $w \to v$. This is verified at load time
by checking that every directed edge has exactly one reverse partner.

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
No pressure and no planarity term are present at this stage.

### 3.4 Orientation

A pure spring force has no notion of "outward": the relaxation is exactly
as likely to converge to a globally inside-out mesh as a right-side-out
one. A *uniform* inversion is corrected for free by reflecting every
vertex through the mesh centroid $\bar p$,

$$p_v \leftarrow 2\bar p - p_v,$$

a point reflection that preserves every pairwise distance (hence every
edge's stretch) while flipping every face's outward-normal sign at once.
A *mixed* result — some faces oriented one way, others the other — cannot
be corrected this cheaply and is passed on unchanged to Stage 2, whose
pressure term is relied on to resolve it.

## 4. Stage 2: pressure-driven inflation

### 4.1 Force

Each edge contributes the same spring force as §3.3. Each face
additionally contributes a real per-face outward force,

$$
\mathbf{F}_{\text{face}} = P \cdot \mathbf{A},\qquad
\mathbf A = \tfrac12 \sum_i p_i \times p_{i+1}
$$

($\mathbf A$: the face's area-weighted outward normal via Newell's
method, summed over its own — possibly non-planar — vertex loop), split
evenly across its vertices. A ($n \geq 4$)-gon face additionally receives
a weak restoring pull toward its own best-fit plane (SVD normal), keeping
faces close to flat as a light regularizer without constraining them
exactly.

### 4.2 Integration

The net force $\mathbf f_v$ on every vertex is computed and the whole
mesh advanced by one explicit step,

$$
p_v \leftarrow p_v + \Delta t\, \mathbf f_v,\qquad
\Delta t = \min\!\left(\Delta t_{\max},\ \frac{\alpha\, \ell_0}
{\max_v \lVert \mathbf f_v\rVert}\right)
$$

i.e. a step size self-normalized to the current largest force, capped
absolutely. This is a deliberate choice over a Newton/least-squares
solver: re-linearizing the whole system and jumping to the linearized
root can land on a distant, spurious equilibrium — e.g. a doubled-size,
heavily-stretched solution, or a uniform near-zero-volume implosion —
that is a genuine root of the same force-balance equations but one a
physical process starting from the current state would never actually
reach. Small explicit steps cannot skip over the physically-reachable
equilibrium this way.

### 4.3 Convergence

The relaxation stops when either (a) the largest per-vertex force drops
below a fixed tolerance $g_{\text{tol}}$, or (b) the RMS stretch's range
over the last $W$ steps falls below a tolerance — a plateau/stall
criterion, since some configurations settle into a persistent numerical
wobble or a very slow tail that never formally satisfies (a) despite the
shape having visibly stopped changing.

### 4.4 Why no volume, target, or stretch-limit term

Plain Hooke's-law springs cannot support unbounded pressure: pressure's
contribution grows with face area ($\sim \ell^2$) while a spring's
restoring force grows only linearly with stretch, so above a critical
pressure no equilibrium exists at all. Two additions were tried to paper
over this and both were rejected as fixing the wrong layer: a
target/reference-volume pressure term (which silently follows wherever
the mesh currently sits, compounding stretch across repeated
subdivide-then-inflate cycles) and a per-edge soft stretch limit (which
forces an equilibrium to exist even at a badly-chosen pressure, rather
than choosing pressure well in the first place). The force model contains
only direct physical quantities — a real spring force, a real pressure
force — and the actual fix for "how much pressure" is §5.

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
