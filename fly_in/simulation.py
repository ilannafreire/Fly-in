"""Simulation engine: turn planned paths into turns and check every rule."""

from collections import Counter
from dataclasses import dataclass, field

from fly_in.models import Network, ZoneType
from fly_in.pathfinder import Path


class SimulationError(Exception):
    """Raised when a set of paths breaks a movement or capacity rule."""


@dataclass(frozen=True)
class Move:
    """One drone movement during a turn.

    Attributes:
        drone_id: 1-based drone identifier.
        target: Destination zone, or connection when flying to a
            restricted zone.
    """

    drone_id: int
    target: str

    def __str__(self) -> str:
        """Format the move as required by the subject: D<ID>-<target>."""
        return f"D{self.drone_id}-{self.target}"


@dataclass
class Turn:
    """Everything that happens during one simulation turn.

    Attributes:
        number: 1-based turn number.
        moves: Movements performed during the turn.
        zones: Drones in each zone at the end of the turn.
        links: Drones that started using each connection this turn.
        delivered: Total drones in the end zone at the end of the turn.
    """

    number: int
    moves: list[Move] = field(default_factory=list)
    zones: Counter[str] = field(default_factory=Counter)
    links: Counter[str] = field(default_factory=Counter)
    delivered: int = 0

    def __str__(self) -> str:
        """Format the turn as one output line."""
        return " ".join(str(move) for move in self.moves)


class Simulation:
    """Replay the paths turn by turn and validate them."""

    def __init__(self, network: Network, paths: list[Path]) -> None:
        """Store the network and the planned paths (one per drone)."""
        self._network = network
        self._paths = paths
        self._link_capacity = {
            connection.name: connection.max_link_capacity
            for connections in network.adjacency.values()
            for connection in connections}

    def run(self) -> list[Turn]:
        """Build the list of turns and check every rule.

        Returns:
            The turns, from turn 1 to the last delivery.

        Raises:
            SimulationError: If a rule is broken.
        """
        total = max((path[-1][0] for path in self._paths), default=0)
        turns = [Turn(number) for number in range(1, total + 1)]
        for drone_id, path in enumerate(self._paths, start=1):
            self._apply_path(turns, drone_id, path)
        for turn in turns:
            turn.moves.sort(key=lambda move: move.drone_id)
            self._validate(turn)
        return turns

    def _apply_path(self, turns: list[Turn], drone_id: int,
                    path: Path) -> None:
        """Record the moves and occupancy of one drone."""
        network = self._network
        if path[0] != (0, network.start) or path[-1][1] != network.end:
            raise SimulationError(f"D{drone_id} must go from start to end")
        for (turn, zone), (next_turn, next_zone) in zip(path, path[1:]):
            if zone != next_zone:
                connection = network.connection_between(zone, next_zone)
                zone_type = network.zones[next_zone].zone_type
                if zone_type is ZoneType.BLOCKED:
                    raise SimulationError(
                        f"D{drone_id} enters blocked zone {next_zone}")
                expected = zone_type.move_cost
                if next_turn - turn != expected:
                    raise SimulationError(
                        f"D{drone_id} has a wrong travel time to {next_zone}")
                turns[turn].links[connection.name] += 1
                if expected == 2:
                    turns[turn].moves.append(Move(drone_id, connection.name))
                turns[next_turn - 1].moves.append(Move(drone_id, next_zone))
            elif next_turn - turn != 1:
                raise SimulationError(f"D{drone_id} cannot wait in transit")
            if next_zone != network.end:
                turns[next_turn - 1].zones[next_zone] += 1
        for remaining in turns[path[-1][0] - 1:]:
            remaining.delivered += 1

    def _validate(self, turn: Turn) -> None:
        """Check zone and connection capacities for one turn."""
        network = self._network
        for zone_name, count in turn.zones.items():
            if count > network.capacity(zone_name):
                raise SimulationError(
                    f"turn {turn.number}: zone '{zone_name}' over capacity")
        for link_name, count in turn.links.items():
            if count > self._link_capacity[link_name]:
                raise SimulationError(
                    f"turn {turn.number}: connection '{link_name}' "
                    "over capacity")
