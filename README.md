*This project has been created as part of the 42 curriculum by ifreire.*

# Fly-in

## Description

Fly-in routes a fleet of drones from a start zone to an end zone through a
network of connected zones, using as few simulation turns as possible.

The program:

1. **parses** a map file (zones, connections, capacities, zone types) and
   reports any error with its line number and cause;
2. **plans** a conflict-free route for every drone, taking into account zone
   types (`normal`, `priority`, `restricted`, `blocked`), zone capacities
   (`max_drones`) and connection capacities (`max_link_capacity`);
3. **simulates** the routes turn by turn, checks every rule again, and prints
   the moves in the format required by the subject, with colors.

Every map shipped with the subject is solved at its **exact optimum**,
including the bonus *Challenger* map:

| Map                    | Drones | Optimum | Fly-in |
|------------------------|-------:|--------:|-------:|
| easy/01 linear path    |      2 |       4 |      4 |
| easy/02 simple fork    |      4 |       4 |      4 |
| easy/03 basic capacity |      4 |       4 |      4 |
| medium/01 dead end     |      5 |       8 |      8 |
| medium/02 circular     |      6 |      10 |     10 |
| medium/03 priority     |      5 |       6 |      6 |
| hard/01 maze           |      8 |      13 |     13 |
| hard/02 capacity hell  |     12 |      16 |     16 |
| hard/03 ultimate       |     15 |      26 |     26 |
| challenger/01 (bonus)  |     25 |      43 |     43 |

## Instructions

Requirements: Python 3.10 or later.

```bash
make install                                   # flake8, mypy, pytest
make run MAP=maps/hard/02_capacity_hell.txt    # run a map
make run MAP=maps/easy/02_simple_fork.txt ARGS=--visual
make run MAP=maps/hard/03_ultimate_challenge.txt ARGS=--map
make debug MAP=maps/easy/01_linear_path.txt    # run under pdb
make lint                                      # flake8 + mypy
make lint-strict                               # flake8 + mypy --strict
make test                                      # unit tests (pytest)
make clean                                     # remove caches
```

Or directly:

```bash
python3 main.py <map_file> [--visual] [--map] [--delay SECONDS] [--no-color]
```

* `--visual` / `-v`: after each turn, print the occupancy of every non-empty
  zone (`zone count/capacity`) and the number of delivered drones.
* `--map` / `-m`: draw the map and animate the drones, one frame per turn
  (see [Visual representation](#visual-representation)).
* `--delay`: seconds between two animation frames (default `0.5`).
* `--no-color`: disable ANSI colors (they are also disabled automatically
  when the output is not a terminal, e.g. `| wc -l`).

On error (unreadable file, parsing error, unreachable end zone), a clear
message is printed on stderr and the program exits with status 1.

## Project structure

```
main.py               CLI entry point (argparse + error handling)
fly_in/models.py      ZoneType, Zone, Connection, Network
fly_in/map_parser.py  MapParser, ParseError
fly_in/pathfinder.py  ReservationTable, Pathfinder, NoPathError
fly_in/simulation.py  Move, Turn, Simulation, SimulationError
fly_in/display.py     Colorizer, Renderer (text), MapRenderer (animated map)
tests/                pytest test suite
maps/                 maps shipped with the subject
```

Each module has a single responsibility (models -> parser -> pathfinder ->
simulation -> display). No graph library is used: only the standard library
(`heapq`, `collections`, `dataclasses`, `re`, `argparse`).

## Algorithm

### Idea: prioritized planning on a time-expanded graph

Instead of computing paths in space and then trying to schedule them (which
causes collisions and deadlocks), the pathfinder searches directly in
**space-time**: a state is a pair `(zone, turn)`.

Drones are planned **one after the other**. Each drone takes the
**earliest-arrival** path that respects everything already reserved by the
previous drones, then reserves its own path in a `ReservationTable`:

* `zones[(zone, turn)]`: drones in a zone at the end of a turn;
* `links[(connection, turn)]`: drones starting to use a connection that turn.

From a state `(zone, t)`, a drone can:

| Action                      | Next state         | Condition                                           |
|-----------------------------|--------------------|-----------------------------------------------------|
| wait                        | `(zone, t+1)`      | `zone` not full at `t+1`                            |
| move to a normal/priority   | `(next, t+1)`      | link not full at `t+1`, `next` not full at `t+1`    |
| move to a restricted zone   | `(next, t+2)`      | link not full at `t+1`, `next` not full at `t+2`    |

Blocked zones are never generated as neighbors. The start and end zones have
no capacity limit.

Since time only moves forward, the space-time graph is a DAG: the search
simply processes turns in increasing order (`frontier[turn]`). The first
turn where the end zone appears is the earliest possible arrival. Ties
between paths that arrive at the same turn are broken by a label
`(idle, priority_bonus)`:

1. **fewer turns spent waiting outside the start zone**: a drone waits at
   the start (which is unlimited) instead of occupying a zone that other
   drones may need;
2. **more priority zones visited**: priority zones are preferred, as the
   subject requires.

### Why it works

* **No collisions, no deadlocks**: a drone's path is only accepted if it
  respects all reservations, and once reserved it never changes. Later
  drones plan around it.
* **Strategic waiting** is built in: waiting is just a `(zone, t) ->
  (zone, t+1)` edge.
* **Distribution over several paths** happens naturally: when the shortest
  path is saturated at some turn, a parallel path (or a wait) becomes the
  earliest arrival for the next drone.
* **Restricted zones**: the drone occupies the connection during the
  transit turn and must have a free spot in the destination two turns later.
  It can never get stuck on the connection. The connection is only counted
  on the turn the drone enters it, so it is free again on the turn the drone
  arrives (as in the subject's example).
* **Termination**: a drone can always wait in the start zone until every
  reservation has expired, then take the shortest path. The search is
  therefore bounded by `horizon = last reserved turn + shortest path time`.
* **Disconnected maps**: a Dijkstra on zone costs (`restricted` = 2,
  otherwise 1) is run first; if the end zone is unreachable, a `NoPathError`
  is reported.

### Complexity

With `Z` zones, `E` connections, `D` drones and `T` the horizon (number of
turns), one drone search is `O((Z + E) * T)` in the worst case, so
planning is `O(D * (Z + E) * T)`. `T` grows with `D` on throughput-limited
maps, so this is roughly quadratic in `D`. In practice: all subject maps run
in under 0.1 s; 200 drones on the ultimate map take about 0.3 s.

Memory: the reservation table holds one entry per used `(zone, turn)` and
`(connection, turn)` pair, i.e. `O(D * path length)`. Paths are not
recomputed: each drone is planned once, and the result is reused for both
the simulation and the display.

### Simulation engine

`Simulation` replays the paths and **independently re-checks** every rule
(path starts at start and ends at end, travel time matches the zone type, no
blocked zone, zone and connection capacities at every turn). If the planner
ever produced an invalid path, the program would stop with a
`SimulationError` instead of printing a wrong answer.

## Visual representation

* Each zone name is printed in its map `color` (256-color ANSI codes;
  `rainbow` is rendered letter by letter; unknown colors are printed
  without color). A drone in transit toward a restricted zone uses the
  destination color. This makes it easy to see which part of the map
  (traps, bottlenecks, priority lanes) each drone is crossing.
* With `--visual`, each turn is followed by the occupancy of every non-empty
  zone (`count/capacity`) and the delivery progress, so you can see
  bottlenecks filling up and draining turn by turn. A summary with the total
  number of turns is printed at the end.
* Colors only add escape codes around names, so the move lines keep the
  exact format required by the subject.
* With `--map`, the map itself is drawn and animated in the terminal (the
  screen is cleared between frames, `--delay` seconds apart). Each zone is
  placed on a grid using its coordinates (only distinct x/y values are kept,
  so sparse coordinates stay compact) and drawn in its color:
  `S` start, `E` goal, `#` blocked, `.` empty zone, or the number of drones
  currently in it. Below the grid: the moves of the turn, and how many
  drones are still at the start, flying toward a restricted zone, and
  delivered. You can watch the drones flow through the network, see where
  they queue and which paths are used in parallel.

  `python3 main.py maps/medium/03_priority_puzzle.txt --map`, turn 2:

  ```
  Turn 2/6

        1   .
    S   1   1   .   E

  moves: D1-fast_path D2-fast_junction D3-slow_path1 D5-start-slow_path1
  start: 1  in flight: 1  delivered: 0/5
  S start  E goal  # blocked  . empty  n = drones in the zone
  ```

  When the output is not a terminal (pipe or file), frames are printed one
  after the other, without animation or colors.

## Example

Input (`maps/medium/03_priority_puzzle.txt`):

```
nb_drones: 5

start_hub: start 0 0 [color=green]
hub: slow_path1 1 -1 [zone=restricted color=red]
hub: slow_path2 2 -1 [color=red]
hub: fast_junction 1 0 [zone=priority color=blue max_drones=2]
hub: fast_path 2 0 [zone=priority color=blue]
hub: merge_point 3 0 [color=yellow max_drones=3]
end_hub: goal 4 0 [color=green]

connection: start-slow_path1
connection: start-fast_junction
connection: slow_path1-slow_path2
connection: slow_path2-merge_point
connection: fast_junction-fast_path
connection: fast_path-merge_point
connection: merge_point-goal [max_link_capacity=2]
```

Output (`python3 main.py maps/medium/03_priority_puzzle.txt`), 6 turns:

```
D1-fast_junction D3-start-slow_path1
D1-fast_path D2-fast_junction D3-slow_path1 D5-start-slow_path1
D1-merge_point D2-fast_path D3-slow_path2 D4-fast_junction D5-slow_path1
D1-goal D2-merge_point D3-merge_point D4-fast_path D5-slow_path2
D2-goal D3-goal D4-merge_point D5-merge_point
D4-goal D5-goal
```

`D3-start-slow_path1` means that D3 is flying on the `start-slow_path1`
connection toward the restricted zone `slow_path1`, which it reaches on the
next turn.

Error example:

```
$ python3 main.py bad_map.txt
Parse error: line 3: invalid zone type 'foo'
```

## Resources

* [Multi-agent pathfinding (MAPF) overview](https://mapf.info/)
* D. Silver, *Cooperative Pathfinding* (2005): cooperative A* and
  reservation tables
* [Dijkstra's algorithm](https://en.wikipedia.org/wiki/Dijkstra%27s_algorithm)
  and [time-expanded networks](https://en.wikipedia.org/wiki/Flow_network)
* Python docs: [`heapq`](https://docs.python.org/3/library/heapq.html),
  [`dataclasses`](https://docs.python.org/3/library/dataclasses.html),
  [`typing`](https://docs.python.org/3/library/typing.html)
* [mypy](https://mypy.readthedocs.io/), [flake8](https://flake8.pycqa.org/),
  [PEP 257](https://peps.python.org/pep-0257/)
* [ANSI escape codes](https://en.wikipedia.org/wiki/ANSI_escape_code)

### Use of AI

AI (GitHub Copilot) was used to:

* read the subject and summarize the movement and capacity rules;
* discuss algorithm options (flow-based vs. reservation-based planning) and
  draft the reservation-table pathfinder;
* write test cases for parser errors and edge cases, and draft this README.

Every part was reviewed, run against all maps and lint tools, and is fully
understood and explained above.
