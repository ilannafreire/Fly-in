"""Terminal rendering of the simulation: colored text and animated map."""

import time
from collections import Counter
from typing import TextIO

from fly_in.models import Network, ZoneType
from fly_in.simulation import Turn

RESET = "\033[0m"
BOLD = "\033[1m"
CLEAR_SCREEN = "\033[H\033[2J"
# 256-color ANSI codes; any unknown color is displayed without color.
COLORS: dict[str, int] = {
    "black": 240, "gray": 245, "grey": 245, "white": 255,
    "red": 196, "darkred": 88, "crimson": 161, "maroon": 52,
    "brown": 130, "orange": 208, "gold": 220, "yellow": 226,
    "lime": 118, "green": 34, "cyan": 51, "blue": 33,
    "purple": 129, "violet": 177, "magenta": 201,
}
RAINBOW = (196, 208, 226, 34, 33, 129)


class Colorizer:
    """Apply the map colors to texts with ANSI escape codes.

    Attributes:
        enabled: Whether ANSI codes are emitted.
    """

    def __init__(self, network: Network, enabled: bool) -> None:
        """Create a colorizer for a network."""
        self._network = network
        self.enabled = enabled

    def zone(self, name: str, text: str | None = None) -> str:
        """Color a text with the color of a zone.

        Args:
            name: Zone name, or connection toward a restricted zone (the
                destination color is then used).
            text: Text to color; the name itself by default.

        Returns:
            The colored text (unchanged if the zone has no known color).
        """
        text = name if text is None else text
        zone = self._network.zones.get(name)
        if zone is None:
            zone = self._network.zones.get(name.split("-")[-1])
        if not self.enabled or zone is None or zone.color is None:
            return text
        if zone.color == "rainbow":
            return "".join(
                self._paint(char, RAINBOW[i % len(RAINBOW)])
                for i, char in enumerate(text))
        code = COLORS.get(zone.color)
        return text if code is None else self._paint(text, code)

    def bold(self, text: str) -> str:
        """Return the text in bold when colors are enabled."""
        return f"{BOLD}{text}{RESET}" if self.enabled else text

    def moves(self, turn: Turn) -> str:
        """Format the subject output line of a turn, colored."""
        return " ".join(f"D{move.drone_id}-{self.zone(move.target)}"
                        for move in turn.moves)

    @staticmethod
    def _paint(text: str, code: int) -> str:
        """Wrap a text with a 256-color ANSI code."""
        return f"\033[38;5;{code}m{text}{RESET}"


class Renderer:
    """Print one line of moves per turn, as required by the subject.

    Attributes:
        verbose: Whether zone occupancy is shown after each turn.
    """

    def __init__(self, network: Network, colors: Colorizer,
                 verbose: bool = False) -> None:
        """Create a text renderer for a network."""
        self._network = network
        self._colors = colors
        self.verbose = verbose

    def render(self, turns: list[Turn], output: TextIO) -> None:
        """Write the whole simulation to an output stream.

        Args:
            turns: The simulated turns.
            output: Stream to write to (e.g. sys.stdout).
        """
        for turn in turns:
            output.write(self._colors.moves(turn) + "\n")
            if self.verbose:
                output.write(self._format_state(turn) + "\n")
        if self.verbose:
            summary = (f"{len(turns)} turns to deliver "
                       f"{self._network.nb_drones} drones")
            output.write(self._colors.bold(summary) + "\n")

    def _format_state(self, turn: Turn) -> str:
        """Format the occupancy of every non-empty zone after the turn."""
        network = self._network
        cells = []
        for name, count in turn.zones.items():
            if count and name != network.start:
                capacity = network.capacity(name)
                cells.append(f"{self._colors.zone(name)} {count}/{capacity}")
        cells.append(f"{self._colors.zone(network.end)} "
                     f"{turn.delivered}/{network.nb_drones}")
        header = self._colors.bold(f"  [turn {turn.number}]")
        return f"{header} " + " | ".join(cells)


class MapRenderer:
    """Draw the zones on a grid and show the drones turn by turn.

    Zones are placed using their coordinates. Only the distinct x and y
    values are kept, so large or sparse coordinates still fit the screen.
    """

    CELL_WIDTH = 4
    LEGEND = "S start  E goal  # blocked  . empty  n = drones in the zone"

    def __init__(self, network: Network, colors: Colorizer,
                 delay: float = 0.5) -> None:
        """Build the grid of zone names from their coordinates.

        Args:
            network: The map to draw.
            colors: Colorizer used for zones and moves.
            delay: Seconds between two frames when animating.
        """
        self._network = network
        self._colors = colors
        self._delay = delay
        zones = network.zones.values()
        columns = {x: i for i, x in enumerate(sorted({z.x for z in zones}))}
        rows = {y: i for i, y in enumerate(sorted({z.y for z in zones}))}
        self._grid: list[list[list[str]]] = [
            [[] for _ in columns] for _ in rows]
        for zone in zones:
            self._grid[rows[zone.y]][columns[zone.x]].append(zone.name)

    def render(self, turns: list[Turn], output: TextIO,
               animate: bool) -> None:
        """Write one frame per turn, starting with the initial state.

        Args:
            turns: The simulated turns.
            output: Stream to write to.
            animate: Clear the screen and wait between frames.
        """
        network = self._network
        initial = Turn(0, zones=Counter({network.start: network.nb_drones}))
        frames = [initial, *turns]
        for index, turn in enumerate(frames):
            if animate:
                output.write(CLEAR_SCREEN)
            output.write(self.frame(turn, len(turns)))
            output.flush()
            if animate and index < len(frames) - 1:
                time.sleep(self._delay)

    def frame(self, turn: Turn, total: int) -> str:
        """Return the drawing of the map after a turn."""
        network = self._network
        in_flight = sum(move.target not in network.zones
                        for move in turn.moves)
        lines = [self._colors.bold(f"Turn {turn.number}/{total}"), ""]
        for row in self._grid:
            lines.append("".join(self._cell(names, turn) for names in row))
        lines += [
            "",
            f"moves: {self._colors.moves(turn) or '-'}",
            f"start: {turn.zones[network.start]}  in flight: {in_flight}  "
            f"delivered: {turn.delivered}/{network.nb_drones}",
            self.LEGEND,
        ]
        return "\n".join(lines) + "\n\n"

    def _cell(self, names: list[str], turn: Turn) -> str:
        """Return the fixed-width drawing of one grid position."""
        network = self._network
        if not names:
            return " " * self.CELL_WIDTH
        if network.start in names:
            label = "S"
        elif network.end in names:
            label = "E"
        elif all(network.zones[name].zone_type is ZoneType.BLOCKED
                 for name in names):
            label = "#"
        else:
            count = sum(turn.zones[name] for name in names)
            label = str(count) if count else "."
        return self._colors.zone(names[0],
                                 label.rjust(self.CELL_WIDTH - 1) + " ")
