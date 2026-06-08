#!/usr/bin/env python3
import random
import argparse

from game_utils import nameFromPlayerId
from game_utils import Direction as D, MoveStatus
from game_utils import Tile, TileStatus, TileObject
from game_utils import Map, Status
from simulator import Simulator
from player_base import Player
from stats import plot_stats

parser = argparse.ArgumentParser(description="Robot Race Simulator 7000")
parser.add_argument('--viz', help="filename for the visualization of the race", type=str)
parser.add_argument('--number', help="number of rounds", type=int, default=1000)
parser.add_argument('--density', help="map density", type=float, default=0.4)
parser.add_argument('--framerate', help="specify framerate of the visualization", type=int, default=8)
parser.add_argument('--map', help="specify map file", type=str,default=None)
parser.add_argument('--mine_mode', help="specify what mines do. Options are wall, scramble and damage", type=str, default="wall")
parser.add_argument('--allow_jumps', help="allow players to jump over walls by running into the same direction twice", action=argparse.BooleanOptionalAction)
# added statistics
parser.add_argument('--stats', help="generate statistics plots", action='store_true')

args = parser.parse_args()

robot_module_names = {"StrategyThreeOneBot":"XAE-12-S3_1",
					  "StrategyTwoBot":"XAE-12-S2",
					  "StalkerHunterPlayer":"stalkerhunter_stats-RobotRace",
					  "StrategyFiveBot": "XAE-12-S5",
					"StrategyFourBot": "XAE-12-S4"}

robotmodules = { m:__import__(m) for m in robot_module_names.values() }

if args.map is not None:
   m = Map.read(args.map)
else:
   m = Map.makeRandom(30, 30, args.density)

if __name__ == "__main__":
	sim = Simulator(map=m, vizfile=args.viz, framerate=args.framerate)

	# ============================================================
	# TEMP: keep active players so we can call optional game_over()
	# and pass readable bot names to debug summaries.
	# Remove this whole block later if no longer needed.
	# ============================================================
	active_players = []

	for name, module_name in robot_module_names.items():
		for p in robotmodules[module_name].players:
			p.player_modname = name
			sim.add_player(p)
			active_players.append(p)

	# Build player_id -> bot name mapping after all players were added.
	player_names = {}
	for p in active_players:
		if hasattr(p, "player_id"):
			player_names[p.player_id] = getattr(p, "player_modname", f"player {p.player_id}")

	# Give every bot access to the readable names.
	for p in active_players:
		p.player_names = player_names

	sim.play(rounds=args.number, jumps_allowed=args.allow_jumps, mine_mode=args.mine_mode.lower())

	# ============================================================
	# TEMP: build readable player names after the game
	# because player_id is definitely known now.
	# ============================================================
	player_names = {}

	for p in active_players:
		if hasattr(p, "player_id"):
			player_names[p.player_id] = getattr(p, "player_modname", f"player {p.player_id}")

	print("DEBUG player_names:", player_names)

	for p in active_players:
		p.player_names = player_names

	# Manually call optional game_over() hook for bots that define it.
	for p in active_players:
		if hasattr(p, "game_over"):
			p.game_over()

	if args.stats:
		plot_stats(sim, 'stats.png')