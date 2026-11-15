"""Fly-in entry point: parse a map, plan the drones and print the turns."""

import argparse
import os
import sys

from fly_in.display import Colorizer, Renderer
from fly_in.gui import GuiError, GuiRenderer
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
    parser.add_argument("-g", "--gui", action="store_true",
                        help="open a window with animated drone images")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="seconds per GUI turn (default: 0.5)")
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
    use_color = sys.stdout.isatty() and not args.no_color
    colors = Colorizer(network, enabled=use_color)
    try:
        Renderer(network, colors, args.visual).render(turns, sys.stdout)
        if args.gui:
            GuiRenderer(network, paths, args.delay).run()
    except GuiError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        # Reader closed the pipe (e.g. "| head"): silence the final flush.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


if __name__ == "__main__":
    sys.exit(main())
