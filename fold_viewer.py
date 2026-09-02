"""
Interactive viewer: drag a slider to fold a net from flat (t=0) to
fully folded (t=1). Run this locally (needs a GUI backend, e.g. TkAgg/Qt5Agg).

    python fold_viewer.py
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from net_fold_core import Net, fold


def build_cube_net():
    net = Net()
    s = 1.0

    def sq(x0, y0):
        return [(x0, y0), (x0 + s, y0), (x0 + s, y0 + s), (x0, y0 + s)]

    bottom = net.add_face(sq(0, 0))
    front  = net.add_face(sq(0, s))
    top    = net.add_face(sq(0, 2 * s))
    back   = net.add_face(sq(0, 3 * s))
    left   = net.add_face(sq(-s, s))
    right  = net.add_face(sq(s, s))

    root, hinges = net.build_tree(root=front)
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    return net, root, hinges, fold_angles


def main():
    net, root, hinges, fold_angles = build_cube_net()

    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(111, projection="3d")
    plt.subplots_adjust(bottom=0.15)

    colors = plt.cm.Set2(np.linspace(0, 1, len(net.faces)))

    def draw(t):
        ax.cla()
        verts = fold(net, root, hinges, fold_angles, t)
        for (fid, pts), color in zip(verts.items(), colors):
            poly = Poly3DCollection([pts], facecolor=color, edgecolor="k", alpha=0.9)
            ax.add_collection3d(poly)
        ax.set_xlim(-1.5, 2.5); ax.set_ylim(-0.5, 3.5); ax.set_zlim(-2, 1.5)
        ax.set_box_aspect([1, 1, 1])
        ax.set_title(f"fold t = {t:.2f}")
        fig.canvas.draw_idle()

    ax_slider = plt.axes([0.2, 0.03, 0.6, 0.03])
    slider = Slider(ax_slider, "fold", 0.0, 1.0, valinit=0.0)
    slider.on_changed(draw)

    draw(0.0)
    plt.show()


if __name__ == "__main__":
    main()
