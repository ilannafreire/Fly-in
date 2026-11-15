"""Colored terminal rendering of the simulation."""

from typing import TextIO

from fly_in.models import Network
from fly_in.simulation import Turn

RESET = "\033[0m"
BOLD = "\033[1m"
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
