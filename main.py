"""Fly-in entry point: parse a map, plan the drones and print the turns."""

import argparse
import os
import sys

from fly_in.display import Colorizer, MapRenderer, Renderer
from fly_in.map_parser import MapParser, ParseError
from fly_in.pathfinder import NoPathError, Pathfinder
from fly_in.simulation import Simulation, SimulationError


def build_arguments() -> argparse.ArgumentParser:
    """Describe the command line interface."""
    parser = argparse.ArgumentParser(
        description="Route a fleet of drones from start to end.")
    parser.add_argument("map_file", help="path to the map file")
    parser.add_argument("-v", "--visual", action="store_true",
                        help="show zone occupancy after each turn")
    parser.add_argument("-m", "--map", action="store_true",
                        help="draw the map and animate the drones")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="seconds between map frames (default: 0.5)")
    parser.add_argument("--no-color", action="store_true",
                        help="disable ANSI colors")
    return parser


def main() -> int:
    """Run the program.

    Returns:
        The process exit code (0 on success, 1 on error).
    """
    parser = build_arguments()
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("--delay must be positive")
    try:
        network = MapParser().parse_file(args.map_file)
        paths = Pathfinder(network).plan_all()
        turns = Simulation(network, paths).run()
    except OSError as error:
        print(f"Error: cannot read map: {error}", file=sys.stderr)
        return 1
    except ParseError as error:
        print(f"Parse error: {error}", file=sys.stderr)
        return 1
    except (NoPathError, SimulationError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    is_terminal = sys.stdout.isatty()
    colors = Colorizer(network, enabled=is_terminal and not args.no_color)
    try:
        if args.map:
            MapRenderer(network, colors, args.delay).render(
                turns, sys.stdout, animate=is_terminal)
        else:
            Renderer(network, colors, args.visual).render(turns, sys.stdout)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        # Reader closed the pipe (e.g. "| head"): silence the final flush.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


if __name__ == "__main__":
    sys.exit(main())
