"""Tests for the parser, the pathfinder and the simulation engine."""

from pathlib import Path

import pytest

from fly_in.gui import drone_location
from fly_in.map_parser import MapParser, ParseError
from fly_in.pathfinder import NoPathError, Pathfinder
from fly_in.simulation import Simulation, SimulationError, Turn

MAPS = Path(__file__).resolve().parent.parent / "maps"
OPTIMUMS = {
    "easy/01_linear_path.txt": 4,
    "easy/02_simple_fork.txt": 4,
    "easy/03_basic_capacity.txt": 4,
    "medium/01_dead_end_trap.txt": 8,
    "medium/02_circular_loop.txt": 10,
    "medium/03_priority_puzzle.txt": 6,
    "hard/01_maze_nightmare.txt": 13,
    "hard/02_capacity_hell.txt": 16,
    "hard/03_ultimate_challenge.txt": 26,
    "challenger/01_the_impossible_dream.txt": 43,
}


def simulate(text: str) -> list[Turn]:
    """Parse, plan and simulate a map given as text."""
    network = MapParser().parse_lines(text.splitlines())
    return Simulation(network, Pathfinder(network).plan_all()).run()


def lines(turns: list[Turn]) -> list[str]:
    """Return the output lines of a simulation."""
    return [str(turn) for turn in turns]


@pytest.mark.parametrize("name,optimum", OPTIMUMS.items())
def test_subject_maps_reach_optimum(name: str, optimum: int) -> None:
    """Every shipped map is solved in its optimal number of turns."""
    network = MapParser().parse_file(MAPS / name)
    turns = Simulation(network, Pathfinder(network).plan_all()).run()
    assert len(turns) == optimum
    assert turns[-1].delivered == network.nb_drones


def test_restricted_queue_matches_subject_example() -> None:
    """Two drones queue on a capacity-1 link toward a restricted zone."""
    turns = simulate(
        "nb_drones: 2\n"
        "start_hub: s 0 0\n"
        "hub: r 1 0 [zone=restricted max_drones=2]\n"
        "end_hub: e 2 0\n"
        "connection: s-r\n"
        "connection: r-e [max_link_capacity=2]\n")
    assert lines(turns) == ["D1-s-r", "D1-r D2-s-r", "D1-e D2-r", "D2-e"]


def test_blocked_zone_is_avoided() -> None:
    """Drones take the longer path instead of a blocked zone."""
    turns = simulate(
        "nb_drones: 1\n"
        "start_hub: s 0 0\n"
        "hub: wall 1 0 [zone=blocked]\n"
        "hub: a 1 1\n"
        "hub: b 2 1\n"
        "end_hub: e 2 0\n"
        "connection: s-wall\n"
        "connection: wall-e\n"
        "connection: s-a\n"
        "connection: a-b\n"
        "connection: b-e\n")
    assert lines(turns) == ["D1-a", "D1-b", "D1-e"]


def test_priority_zone_wins_ties() -> None:
    """With equal length, the path through a priority zone is chosen."""
    turns = simulate(
        "nb_drones: 1\n"
        "start_hub: s 0 0\n"
        "hub: plain 1 0\n"
        "hub: fast 1 1 [zone=priority]\n"
        "end_hub: e 2 0\n"
        "connection: s-plain\n"
        "connection: s-fast\n"
        "connection: plain-e\n"
        "connection: fast-e\n")
    assert lines(turns) == ["D1-fast", "D1-e"]


def test_disconnected_map_is_reported() -> None:
    """An unreachable end zone raises a clear error, not a crash."""
    with pytest.raises(NoPathError):
        simulate("nb_drones: 1\nstart_hub: s 0 0\nend_hub: e 1 0\n")


@pytest.mark.parametrize("text,message", [
    ("hub: a 0 0\n", "line 1: first line must be 'nb_drones"),
    ("nb_drones: 0\n", "line 1: 'nb_drones' must be a positive integer"),
    ("nb_drones: 1\nstart_hub: a 0 0\nstart_hub: b 1 1\n",
     "line 3: more than one start_hub"),
    ("nb_drones: 1\nhub: a 0 x\n", "line 2: invalid zone definition"),
    ("nb_drones: 1\nhub: a-b 0 0\n", "line 2: invalid zone definition"),
    ("nb_drones: 1\nhub: a 0 0\nhub: a 1 1\n", "line 3: duplicate zone"),
    ("nb_drones: 1\nhub: a 0 0 [zone=lava]\n", "line 2: invalid zone type"),
    ("nb_drones: 1\nhub: a 0 0 [max_drones=-1]\n",
     "line 2: 'max_drones' must be a positive integer"),
    ("nb_drones: 1\nhub: a 0 0 [speed=3]\n", "line 2: unknown metadata"),
    ("nb_drones: 1\nhub: a 0 0 [color]\n", "line 2: invalid metadata"),
    ("nb_drones: 1\nhub: a 0 0\nconnection: a-b\n", "line 3: unknown zone"),
    ("nb_drones: 1\nhub: a 0 0\nhub: b 1 1\nconnection: a-b\n"
     "connection: b-a\n", "line 5: duplicate connection"),
    ("nb_drones: 1\nhub: a 0 0\nhub: b 1 1\n"
     "connection: a-b [max_link_capacity=0]\n",
     "line 4: 'max_link_capacity' must be a positive integer"),
    ("nb_drones: 1\nstart_hub: a 0 0\n", "missing end_hub"),
    ("nb_drones: 1\nfoo: bar\n", "line 2: unknown line type"),
])
def test_parse_errors(text: str, message: str) -> None:
    """Invalid maps raise a ParseError naming the line and the cause."""
    with pytest.raises(ParseError, match=message):
        MapParser().parse_lines(text.splitlines())


def test_capacity_on_start_and_end_is_ignored() -> None:
    """max_drones on start/end is accepted and does not limit drones."""
    turns = simulate(
        "nb_drones: 3 # comment\n"
        "start_hub: s 0 0 [max_drones=1]\n"
        "end_hub: e 1 0 [max_drones=1]\n"
        "connection: s-e [max_link_capacity=3]\n")
    assert lines(turns) == ["D1-e D2-e D3-e"]


def test_drone_location_handles_transit() -> None:
    """The GUI places a drone in a zone or on a restricted connection."""
    path = [(0, "s"), (1, "a"), (3, "r"), (4, "e")]
    assert drone_location(path, 0) == ("s", "s")
    assert drone_location(path, 2) == ("a", "r")
    assert drone_location(path, 3) == ("r", "r")
    assert drone_location(path, 9) == ("e", "e")


def test_simulation_rejects_over_capacity() -> None:
    """The engine catches paths that overload a zone."""
    network = MapParser().parse_lines(
        "nb_drones: 2\nstart_hub: s 0 0\nhub: a 1 0\nend_hub: e 2 0\n"
        "connection: s-a [max_link_capacity=2]\nconnection: a-e\n"
        .splitlines())
    paths = [[(0, "s"), (1, "a"), (2, "e")],
             [(0, "s"), (1, "a"), (2, "a"), (3, "e")]]
    with pytest.raises(SimulationError, match="zone 'a' over capacity"):
        Simulation(network, paths).run()
