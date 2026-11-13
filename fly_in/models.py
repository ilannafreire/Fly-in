"""Domain models: zones, connections and the network that links them."""

from dataclasses import dataclass, field
from enum import Enum


class ZoneType(Enum):
    """Kind of zone, which defines the cost of entering it."""

    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"

    @property
    def move_cost(self) -> int:
        """Return how many turns it takes to enter a zone of this type."""
        return 2 if self is ZoneType.RESTRICTED else 1


@dataclass(frozen=True)
class Zone:
    """A node of the network.

    Attributes:
        name: Unique zone name.
        x: Horizontal coordinate.
        y: Vertical coordinate.
        zone_type: Type of the zone (normal, blocked, restricted, priority).
        color: Optional display color.
        max_drones: Maximum number of drones the zone can hold at once.
    """

    name: str
    x: int
    y: int
    zone_type: ZoneType = ZoneType.NORMAL
    color: str | None = None
    max_drones: int = 1


@dataclass(frozen=True)
class Connection:
    """A bidirectional edge between two zones.

    Attributes:
        zone_a: Name of the first zone.
        zone_b: Name of the second zone.
        max_link_capacity: Drones allowed to use the link in the same turn.
    """

    zone_a: str
    zone_b: str
    max_link_capacity: int = 1

    @property
    def name(self) -> str:
        """Return the connection name as written in the map file."""
        return f"{self.zone_a}-{self.zone_b}"

    def other(self, zone_name: str) -> str:
        """Return the zone at the opposite end of the connection.

        Args:
            zone_name: One of the two endpoints.

        Returns:
            The other endpoint.
        """
        return self.zone_b if zone_name == self.zone_a else self.zone_a


@dataclass
class Network:
    """The whole map: drones count, zones and connections.

    Attributes:
        nb_drones: Number of drones to deliver.
        start: Name of the start zone.
        end: Name of the end zone.
        zones: Zones indexed by name.
        adjacency: For each zone, the connections touching it.
    """

    nb_drones: int
    start: str
    end: str
    zones: dict[str, Zone] = field(default_factory=dict)
    adjacency: dict[str, list[Connection]] = field(default_factory=dict)

    def add_zone(self, zone: Zone) -> None:
        """Register a zone in the network."""
        self.zones[zone.name] = zone
        self.adjacency.setdefault(zone.name, [])

    def add_connection(self, connection: Connection) -> None:
        """Register a bidirectional connection in the network."""
        self.adjacency[connection.zone_a].append(connection)
        self.adjacency[connection.zone_b].append(connection)

    def neighbors(self, zone_name: str) -> list[tuple[Zone, Connection]]:
        """Return the reachable (non blocked) neighbors of a zone.

        Args:
            zone_name: Zone to inspect.

        Returns:
            Pairs of (neighbor zone, connection used to reach it).
        """
        result: list[tuple[Zone, Connection]] = []
        for connection in self.adjacency[zone_name]:
            zone = self.zones[connection.other(zone_name)]
            if zone.zone_type is not ZoneType.BLOCKED:
                result.append((zone, connection))
        return result

    def connection_between(self, zone_a: str, zone_b: str) -> Connection:
        """Return the connection linking two adjacent zones.

        Raises:
            KeyError: If the zones are not directly connected.
        """
        for connection in self.adjacency[zone_a]:
            if connection.other(zone_a) == zone_b:
                return connection
        raise KeyError(f"no connection between '{zone_a}' and '{zone_b}'")

    def capacity(self, zone_name: str) -> int:
        """Return how many drones a zone can hold.

        Start and end zones are unlimited, so they can hold every drone.
        """
        if zone_name in (self.start, self.end):
            return self.nb_drones
        return self.zones[zone_name].max_drones
