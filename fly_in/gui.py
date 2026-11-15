"""Graphical window (tkinter) showing drone illustrations flying the map."""

import time
from functools import partial
import tkinter as tk
from pathlib import Path as FilePath

from fly_in.models import Network, ZoneType
from fly_in.pathfinder import Path

DRONE_IMAGE = FilePath(__file__).resolve().parent.parent / "assets/drone.png"
FRAME_MS = 16
ZONE_RADIUS = 18
MARGIN = 70
MAX_CELL = 140
LABEL_STAGGER_WIDTH = 120
# Below this column width, labels alternate above/below to avoid overlapping.
LABEL_FONT = ("TkDefaultFont", 8)
BACKGROUND = "#1e1e28"


class GuiError(Exception):
    """Raised when the graphical window cannot be opened."""


def drone_location(path: Path, turn: int) -> tuple[str, str]:
    """Locate a drone at the end of a turn.

    Args:
        path: The drone path, as (turn, zone) states.
        turn: Turn number (0 = initial state).

    Returns:
        (zone, zone) when the drone is in a zone, or (origin, destination)
        when it is flying toward a restricted zone.
    """
    for (current_turn, zone), (next_turn, next_zone) in zip(path, path[1:]):
        if current_turn <= turn < next_turn:
            if current_turn == turn:
                return zone, zone
            return zone, next_zone
    return path[-1][1], path[-1][1]


class GuiRenderer:
    """Animate the drones on a canvas, sliding from zone to zone.

    Controls: space pauses/resumes, Escape closes the window.
    """

    def __init__(self, network: Network, paths: list[Path],
                 delay: float = 0.5) -> None:
        """Build the window, draw the map and load the drone image.

        Args:
            network: The map to draw.
            paths: One planned path per drone.
            delay: Seconds spent animating one turn.

        Raises:
            GuiError: If no display is available.
        """
        self._network = network
        self._paths = paths
        self._total = max(path[-1][0] for path in paths)
        self._delay = delay
        self._turn = 0
        self._turn_started = time.monotonic()
        self._last_frame = self._turn_started
        self._paused = False
        self._cache: dict[int, list[tuple[float, float] | None]] = {}
        try:
            self._root = tk.Tk()
        except tk.TclError as error:
            raise GuiError(f"cannot open a window: {error}") from None
        self._root.title("Fly-in")
        self._pixels, self._stagger = self._compute_pixels()
        width = max(x for x, _ in self._pixels.values()) + MARGIN
        height = max(y for _, y in self._pixels.values()) + MARGIN + 60
        self._canvas = tk.Canvas(self._root, width=width, height=height,
                                 background=BACKGROUND, highlightthickness=0)
        self._canvas.pack()
        self._image = self._load_image()
        self._status = self._canvas.create_text(
            10, height - 20, anchor="w", fill="white",
            font=("TkDefaultFont", 12, "bold"))
        self._info = self._canvas.create_text(
            10, height - 45, anchor="w", fill="#ccccdd", font=LABEL_FONT,
            text="hover a zone to see its details")
        self._draw_map()
        self._drones = [self._create_drone(i + 1) for i in range(len(paths))]
        self._root.bind("<space>", self._toggle_pause)
        self._root.bind("<Escape>", lambda _event: self._root.destroy())

    def run(self) -> None:
        """Start the animation and block until the window is closed."""
        self._turn_started = self._last_frame = time.monotonic()
        self._draw_frame()
        self._root.mainloop()

    def _compute_pixels(self) -> tuple[dict[str, tuple[float, float]], bool]:
        """Scale the zone coordinates to canvas pixels.

        Each axis has its own scale so that the map fills the screen, while
        the relative order of the coordinates is kept.

        Returns:
            The pixel position of each zone, and whether columns are too
            narrow for labels to sit side by side.
        """
        zones = self._network.zones.values()
        min_x, min_y = min(z.x for z in zones), min(z.y for z in zones)
        span_x = max(z.x for z in zones) - min_x or 1
        span_y = max(z.y for z in zones) - min_y or 1
        screen_w = self._root.winfo_screenwidth() - 2 * MARGIN
        screen_h = self._root.winfo_screenheight() - 2 * MARGIN - 160
        scale_x = min(screen_w / span_x, MAX_CELL)
        scale_y = min(screen_h / span_y, MAX_CELL)
        pixels = {zone.name: (MARGIN + (zone.x - min_x) * scale_x,
                              MARGIN + (zone.y - min_y) * scale_y)
                  for zone in zones}
        return pixels, scale_x < LABEL_STAGGER_WIDTH

    def _load_image(self) -> tk.PhotoImage | None:
        """Load the drone illustration, or None to draw a simple shape."""
        try:
            return tk.PhotoImage(master=self._root, file=str(DRONE_IMAGE))
        except tk.TclError:
            return None

    def _color(self, name: str) -> str:
        """Return the zone color if tkinter knows it, gray otherwise."""
        color = self._network.zones[name].color
        try:
            self._root.winfo_rgb(color or "")
            return color or "gray"
        except tk.TclError:
            return "gray"

    def _draw_map(self) -> None:
        """Draw the connections, then the zones with their names."""
        canvas = self._canvas
        for connections in self._network.adjacency.values():
            for link in connections:
                (x1, y1), (x2, y2) = (self._pixels[link.zone_a],
                                      self._pixels[link.zone_b])
                canvas.create_line(x1, y1, x2, y2, fill="#555566",
                                   width=1 + 2 * link.max_link_capacity)
        for name, (x, y) in self._pixels.items():
            zone = self._network.zones[name]
            oval = canvas.create_oval(
                x - ZONE_RADIUS, y - ZONE_RADIUS,
                x + ZONE_RADIUS, y + ZONE_RADIUS,
                fill=self._color(name), outline="white",
                dash=(3, 2) if zone.zone_type is ZoneType.RESTRICTED else ())
            above = self._stagger and zone.x % 2 == 1
            offset = -(ZONE_RADIUS + 10) if above else ZONE_RADIUS + 10
            canvas.create_text(x, y + offset, text=name, fill="#ccccdd",
                               font=LABEL_FONT)
            canvas.tag_bind(oval, "<Enter>", partial(self._show_info, name))

    def _show_info(self, name: str,
                   _event: "tk.Event[tk.Canvas] | None" = None) -> None:
        """Show the details of the zone under the mouse."""
        zone = self._network.zones[name]
        capacity = ("unlimited" if name in (self._network.start,
                                            self._network.end)
                    else str(zone.max_drones))
        text = (f"{name}   type: {zone.zone_type.value}   "
                f"max_drones: {capacity}   color: {zone.color or '-'}   "
                f"coords: ({zone.x}, {zone.y})")
        self._canvas.itemconfigure(self._info, text=text)

    def _create_drone(self, drone_id: int) -> tuple[int, int]:
        """Create the canvas items of a drone (image and label)."""
        if self._image is not None:
            body = self._canvas.create_image(0, 0, image=self._image)
        else:
            body = self._canvas.create_oval(-10, -10, 10, 10, fill="orange")
        label = self._canvas.create_text(0, 0, text=f"D{drone_id}",
                                         fill="white",
                                         font=("TkDefaultFont", 8, "bold"))
        return body, label

    def _positions(self, turn: int) -> list[tuple[float, float] | None]:
        """Pixel position of each drone after a turn (None if delivered).

        Drones sharing a zone are spread around it so that they stay
        visible; in-flight drones are drawn halfway along the connection.
        Results are cached since each turn is used by many frames.
        """
        if turn in self._cache:
            return self._cache[turn]
        network = self._network
        groups: dict[tuple[str, str], list[int]] = {}
        for index, path in enumerate(self._paths):
            groups.setdefault(drone_location(path, turn), []).append(index)
        positions: list[tuple[float, float] | None] = [None] * len(self._paths)
        for (origin, target), drones in groups.items():
            if origin == target == network.end and turn > 0:
                continue
            (x1, y1), (x2, y2) = self._pixels[origin], self._pixels[target]
            x, y = (x1 + x2) / 2, (y1 + y2) / 2
            spread = origin == target and origin != network.start
            for rank, index in enumerate(drones):
                offset = 14.0 * rank if spread else 0.0
                positions[index] = (x + offset, y - offset)
        self._cache[turn] = positions
        return positions

    def _draw_frame(self) -> None:
        """Move every drone toward its next position.

        Progress is based on the clock, so a turn always lasts ``delay``
        seconds whatever the drawing speed of the machine.
        """
        now = time.monotonic()
        if self._paused:
            self._turn_started += now - self._last_frame
        self._last_frame = now
        elapsed = now - self._turn_started
        ratio = min(1.0, elapsed / self._delay) if self._delay else 1.0
        before = self._positions(self._turn)
        after = self._positions(min(self._turn + 1, self._total))
        for (body, label), start, end in zip(self._drones, before, after):
            if start is None or (end is None and ratio == 1.0):
                self._canvas.itemconfigure(body, state="hidden")
                self._canvas.itemconfigure(label, state="hidden")
                continue
            target = end or self._pixels[self._network.end]
            x = start[0] + (target[0] - start[0]) * ratio
            y = start[1] + (target[1] - start[1]) * ratio
            self._canvas.coords(body, x, y)
            self._canvas.coords(label, x, y - 28)
        self._update_status()
        if self._turn >= self._total:
            return
        if ratio >= 1.0:
            self._turn += 1
            self._turn_started = now
        self._root.after(FRAME_MS, self._draw_frame)

    def _update_status(self) -> None:
        """Show the turn number and the delivery progress."""
        delivered = sum(path[-1][0] <= self._turn for path in self._paths)
        text = (f"Turn {self._turn}/{self._total}   delivered "
                f"{delivered}/{len(self._paths)}   "
                f"{'[paused] ' if self._paused else ''}"
                "space: pause   esc: quit")
        self._canvas.itemconfigure(self._status, text=text)

    def _toggle_pause(self, _event: "tk.Event[tk.Misc]") -> None:
        """Pause or resume the animation."""
        self._paused = not self._paused
