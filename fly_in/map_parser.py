"""Parser for the Fly-in map file format."""

import re
from pathlib import Path

from fly_in.models import Connection, Network, Zone, ZoneType

ZONE_PATTERN = re.compile(
    r"^(?P<name>[^\s\-\[\]]+)\s+(?P<x>-?\d+)\s+(?P<y>-?\d+)"
    r"(?:\s+\[(?P<meta>[^\]]*)\])?$"
)
CONNECTION_PATTERN = re.compile(
    r"^(?P<a>[^\s\-\[\]]+)-(?P<b>[^\s\-\[\]]+)"
    r"(?:\s+\[(?P<meta>[^\]]*)\])?$"
)
ZONE_KEYS = {"zone", "color", "max_drones"}
CONNECTION_KEYS = {"max_link_capacity"}


class ParseError(Exception):
    """Raised when the map file is invalid."""

    def __init__(self, line_number: int, message: str) -> None:
        """Build an error that points to the faulty line.

        Args:
            line_number: 1-based line number in the file (0 = whole file).
            message: Human readable cause.
        """
        location = f"line {line_number}: " if line_number else ""
        super().__init__(f"{location}{message}")
        self.line_number = line_number


class MapParser:
    """Read a map file and build a validated Network."""

    def __init__(self) -> None:
        """Initialize an empty parsing state."""
        self._nb_drones: int | None = None
        self._start: Zone | None = None
        self._end: Zone | None = None
        self._zones: dict[str, Zone] = {}
        self._connections: dict[frozenset[str], Connection] = {}

    def parse_file(self, path: str | Path) -> Network:
        """Parse a map file.

        Args:
            path: Path to the map file.

        Returns:
            The validated network.

        Raises:
            ParseError: If the content is invalid.
            OSError: If the file cannot be read.
        """
        with open(path, encoding="utf-8") as file:
            return self.parse_lines(file.read().splitlines())

    def parse_lines(self, lines: list[str]) -> Network:
        """Parse the map content line by line.

        Args:
            lines: Raw lines of the map file.

        Returns:
            The validated network.

        Raises:
            ParseError: If the content is invalid.
        """
        for number, raw in enumerate(lines, start=1):
            line = raw.split("#", 1)[0].strip()
            if line:
                self._parse_line(number, line)
        return self._build_network()

    def _parse_line(self, number: int, line: str) -> None:
        """Dispatch a meaningful line to the right handler."""
        prefix, separator, content = line.partition(":")
        if not separator:
            raise ParseError(number, f"missing ':' in '{line}'")
        prefix = prefix.strip()
        content = content.strip()
        if self._nb_drones is None and prefix != "nb_drones":
            raise ParseError(number, "first line must be 'nb_drones: <n>'")
        if prefix == "nb_drones":
            self._parse_nb_drones(number, content)
        elif prefix in ("start_hub", "end_hub", "hub"):
            self._parse_zone(number, prefix, content)
        elif prefix == "connection":
            self._parse_connection(number, content)
        else:
            raise ParseError(number, f"unknown line type '{prefix}'")

    def _parse_nb_drones(self, number: int, content: str) -> None:
        """Parse the 'nb_drones' line."""
        if self._nb_drones is not None:
            raise ParseError(number, "'nb_drones' defined more than once")
        self._nb_drones = self._positive_int(number, "nb_drones", content)

    def _parse_zone(self, number: int, prefix: str, content: str) -> None:
        """Parse a 'start_hub', 'end_hub' or 'hub' line."""
        match = ZONE_PATTERN.match(content)
        if match is None:
            raise ParseError(
                number, f"invalid zone definition '{content}' "
                "(expected '<name> <x> <y> [metadata]', no dash in name)")
        name = match["name"]
        if name in self._zones:
            raise ParseError(number, f"duplicate zone name '{name}'")
        meta = self._parse_metadata(number, match["meta"], ZONE_KEYS)
        try:
            zone_type = ZoneType(meta.get("zone", "normal"))
        except ValueError:
            raise ParseError(
                number, f"invalid zone type '{meta['zone']}'") from None
        max_drones = self._positive_int(
            number, "max_drones", meta.get("max_drones", "1"))
        zone = Zone(name, int(match["x"]), int(match["y"]), zone_type,
                    meta.get("color"), max_drones)
        if prefix == "start_hub":
            if self._start is not None:
                raise ParseError(number, "more than one start_hub")
            self._start = zone
        elif prefix == "end_hub":
            if self._end is not None:
                raise ParseError(number, "more than one end_hub")
            self._end = zone
        self._zones[name] = zone

    def _parse_connection(self, number: int, content: str) -> None:
        """Parse a 'connection' line."""
        match = CONNECTION_PATTERN.match(content)
        if match is None:
            raise ParseError(
                number, f"invalid connection '{content}' "
                "(expected '<zone1>-<zone2> [metadata]')")
        zone_a, zone_b = match["a"], match["b"]
        for name in (zone_a, zone_b):
            if name not in self._zones:
                raise ParseError(number, f"unknown zone '{name}'")
        if zone_a == zone_b:
            raise ParseError(number, f"zone '{zone_a}' linked to itself")
        key = frozenset((zone_a, zone_b))
        if key in self._connections:
            raise ParseError(
                number, f"duplicate connection '{zone_a}-{zone_b}'")
        meta = self._parse_metadata(number, match["meta"], CONNECTION_KEYS)
        capacity = self._positive_int(
            number, "max_link_capacity", meta.get("max_link_capacity", "1"))
        self._connections[key] = Connection(zone_a, zone_b, capacity)

    @staticmethod
    def _parse_metadata(number: int, block: str | None,
                        allowed: set[str]) -> dict[str, str]:
        """Parse a '[key=value ...]' block into a dictionary.

        Args:
            number: Line number, for error messages.
            block: Content between brackets, or None if absent.
            allowed: Keys accepted for this kind of line.

        Returns:
            The metadata as a key/value dictionary.
        """
        metadata: dict[str, str] = {}
        if block is None:
            return metadata
        for item in block.split():
            key, separator, value = item.partition("=")
            if not separator or not key or not value:
                raise ParseError(number, f"invalid metadata '{item}'")
            if key not in allowed:
                raise ParseError(number, f"unknown metadata key '{key}'")
            if key in metadata:
                raise ParseError(number, f"duplicate metadata key '{key}'")
            metadata[key] = value
        return metadata

    @staticmethod
    def _positive_int(number: int, label: str, value: str) -> int:
        """Convert a value to a strictly positive integer."""
        if not value.isdigit() or int(value) <= 0:
            raise ParseError(
                number, f"'{label}' must be a positive integer, got '{value}'")
        return int(value)

    def _build_network(self) -> Network:
        """Run global checks and assemble the Network."""
        if self._nb_drones is None:
            raise ParseError(0, "missing 'nb_drones' line")
        if self._start is None:
            raise ParseError(0, "missing start_hub")
        if self._end is None:
            raise ParseError(0, "missing end_hub")
        network = Network(self._nb_drones, self._start.name, self._end.name)
        for zone in self._zones.values():
            network.add_zone(zone)
        for connection in self._connections.values():
            network.add_connection(connection)
        return network
