"""Turn-aware pathfinding with a reservation table (prioritized planning).

Each drone is planned one after the other on a time-expanded graph whose
states are ``(zone, turn)``. A drone takes the earliest-arrival path that
respects every capacity already reserved by the previous drones, then
reserves its own path. Since every planned path is final and conflict-free,
deadlocks and collisions cannot happen.
"""

import heapq
from collections import defaultdict
from dataclasses import dataclass, field

from fly_in.models import Connection, Network, ZoneType

# A path is the list of (turn, zone) states visited by one drone, starting
# with (0, start). A gap of 2 turns between two states is a restricted move.
Path = list[tuple[int, str]]


class NoPathError(Exception):
    """Raised when the end zone cannot be reached from the start zone."""


class ReservationTable:
    """Remember how much of each zone/connection is used at each turn."""

    def __init__(self, network: Network) -> None:
        """Create an empty table for the given network."""
        self._network = network
        self._zones: dict[tuple[str, int], int] = defaultdict(int)
        self._links: dict[tuple[str, int], int] = defaultdict(int)
        self.last_turn = 0

    def zone_is_free(self, zone_name: str, turn: int) -> bool:
        """Tell whether one more drone can be in a zone at a given turn."""
        used = self._zones.get((zone_name, turn), 0)
        return used < self._network.capacity(zone_name)

    def link_is_free(self, connection: Connection, turn: int) -> bool:
        """Tell whether one more drone can take a connection at a turn."""
        used = self._links.get((connection.name, turn), 0)
        return used < connection.max_link_capacity

    def reserve(self, path: Path) -> None:
        """Reserve every zone and connection used by a path.

        A connection is only counted on the turn the drone starts using it:
        for restricted moves it is freed on the turn the drone arrives.
        """
        for (turn, zone), (next_turn, next_zone) in zip(path, path[1:]):
            if zone != next_zone:
                connection = self._network.connection_between(zone, next_zone)
                self._links[(connection.name, turn + 1)] += 1
            if next_zone not in (self._network.start, self._network.end):
                self._zones[(next_zone, next_turn)] += 1
        self.last_turn = max(self.last_turn, path[-1][0])


@dataclass(order=True)
class _Label:
    """Best known way to reach a (zone, turn) state.

    Labels are compared on ``(idle, priority_bonus)``: fewer turns spent
    waiting outside the start zone first, then more priority zones visited.
    """

    idle: int
    priority_bonus: int
    parent: tuple[str, int] | None = field(compare=False)


class Pathfinder:
    """Plan conflict-free paths for every drone of a network."""

    def __init__(self, network: Network) -> None:
        """Prepare the pathfinder for a network."""
        self._network = network
        self._reservations = ReservationTable(network)

    def plan_all(self) -> list[Path]:
        """Plan one path per drone, in drone order.

        Returns:
            The list of paths, index i being the path of drone i + 1.

        Raises:
            NoPathError: If the end zone is unreachable.
        """
        shortest = self.shortest_time()
        paths: list[Path] = []
        for _ in range(self._network.nb_drones):
            # Worst case: wait at start until the map is empty, then go.
            horizon = self._reservations.last_turn + shortest
            path = self._plan_one(horizon)
            self._reservations.reserve(path)
            paths.append(path)
        return paths

    def shortest_time(self) -> int:
        """Return the minimum number of turns from start to end (Dijkstra).

        Capacities are ignored here: this is used to detect unreachable
        maps and to bound the space-time search.

        Raises:
            NoPathError: If the end zone is unreachable.
        """
        network = self._network
        distances = {network.start: 0}
        queue = [(0, network.start)]
        while queue:
            distance, zone_name = heapq.heappop(queue)
            if zone_name == network.end:
                return distance
            if distance > distances[zone_name]:
                continue
            for zone, _ in network.neighbors(zone_name):
                new_distance = distance + zone.zone_type.move_cost
                if new_distance < distances.get(zone.name, new_distance + 1):
                    distances[zone.name] = new_distance
                    heapq.heappush(queue, (new_distance, zone.name))
        raise NoPathError(
            f"no path connects '{network.start}' to '{network.end}'")

    def _plan_one(self, horizon: int) -> Path:
        """Find the earliest-arrival path for one drone.

        Time only moves forward, so the time-expanded graph is a DAG and we
        can relax states turn by turn. The first turn where the end zone is
        reached is the earliest arrival; the label breaks ties.
        """
        network = self._network
        labels: dict[tuple[str, int], _Label] = {
            (network.start, 0): _Label(0, 0, None)}
        frontier: dict[int, set[str]] = defaultdict(set)
        frontier[0].add(network.start)
        for turn in range(horizon + 1):
            if network.end in frontier[turn]:
                return self._rebuild(labels, (network.end, turn))
            for zone_name in frontier.pop(turn, set()):
                self._expand(labels, frontier, zone_name, turn)
        raise NoPathError("no conflict-free path found")

    def _expand(self, labels: dict[tuple[str, int], _Label],
                frontier: dict[int, set[str]], zone_name: str,
                turn: int) -> None:
        """Generate every legal next state from (zone_name, turn)."""
        network = self._network
        table = self._reservations
        label = labels[(zone_name, turn)]
        state = (zone_name, turn)

        if table.zone_is_free(zone_name, turn + 1):
            idle = label.idle + (zone_name != network.start)
            self._relax(labels, frontier, (zone_name, turn + 1),
                        _Label(idle, label.priority_bonus, state))

        for zone, connection in network.neighbors(zone_name):
            arrival = turn + zone.zone_type.move_cost
            if not table.link_is_free(connection, turn + 1):
                continue
            if not table.zone_is_free(zone.name, arrival):
                continue
            bonus = label.priority_bonus - (
                zone.zone_type is ZoneType.PRIORITY)
            self._relax(labels, frontier, (zone.name, arrival),
                        _Label(label.idle, bonus, state))

    @staticmethod
    def _relax(labels: dict[tuple[str, int], _Label],
               frontier: dict[int, set[str]], state: tuple[str, int],
               label: _Label) -> None:
        """Keep the label if it is better than the known one."""
        current = labels.get(state)
        if current is None or label < current:
            labels[state] = label
            frontier[state[1]].add(state[0])

    @staticmethod
    def _rebuild(labels: dict[tuple[str, int], _Label],
                 state: tuple[str, int]) -> Path:
        """Follow parent links back to the start to build the path."""
        path: Path = []
        current: tuple[str, int] | None = state
        while current is not None:
            path.append((current[1], current[0]))
            current = labels[current].parent
        path.reverse()
        return path
