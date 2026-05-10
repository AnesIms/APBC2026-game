#!/usr/bin/env python3
import copy
import random
import argparse
import sys
import os

# --- THIS IMPORT MUTES THE SPAMMY PRINTS ---
from contextlib import redirect_stdout 

from Game import game_utils, simulator, player_base, shortestpaths
from Game.game_utils import nameFromPlayerId
from Game.game_utils import Direction as D, MoveStatus as D, MoveStatus
from Game.game_utils import Tile, TileStatus, TileObject
from Game.game_utils import Map, Status
from Game.illustrator import Illustrator
from Game.simulator import Simulator
from Game.player_base import Player

parser = argparse.ArgumentParser(description="Robot Race Simulator 7000")
parser.add_argument('--viz', help="filename for the visualization of the race", type=str)
parser.add_argument('--number', help="number of rounds", type=int, default=1000)
parser.add_argument('--density', help="map density", type=float, default=0.4)
parser.add_argument('--framerate', help="specify framerate of the visualization", type=int, default=8)
parser.add_argument('--map', help="specify map file", type=str,default=None)
parser.add_argument('--mine_mode', help="specify what mines do. Options are wall, scramble and damage", type=str, default="wall")
parser.add_argument('--allow_jumps', help="allow players to jump over walls by running into the same direction twice", action=argparse.BooleanOptionalAction)
parser.add_argument('--games', help="number of games to simulate", type=int, default=1)

args = parser.parse_args()

robot_module_names = {"Test_Erratic":"test-RobotRace",
                      "Beatme_SillyScout": "beatme-RobotRace",
                      "Adlhartm_Naive": "adlhartm-RobotRace"}


script_dir = os.path.dirname(os.path.realpath(__file__))
robots_dir = os.path.join(script_dir, 'Robots')
sys.path.insert(0, robots_dir)

robotmodules = { m:__import__(m) for m in robot_module_names.values() }

if args.map is not None:
   base_map = Map.read(args.map)
else:
   base_map = Map.makeRandom(30, 30, args.density)

# --- STAT TRACKERS ---
win_stats = {name: 0 for name in robot_module_names.keys()}
win_stats["Draw/None"] = 0
move_stats = {name: 0 for name in robot_module_names.keys()}

is_batch_run = args.games > 1

if is_batch_run:
    print(f"Starting {args.games} games silently... Please wait.")

# =====================================================================
# --- THE BUG FIX: ISOLATED TRACKER FACTORY ---
# This prevents the bots from sharing the same brain (Loop Closure Bug)
# and prevents the simulator from crashing when bots yield generators.
def attach_tracker(player_obj, method_name):
    original_brain = getattr(player_obj, method_name)
    
    def intercepted(*args, **kwargs):
        # Run the bot's normal brain
        raw_moves = original_brain(*args, **kwargs)
        
        # Convert the output to a safe list
        moves_list = [] if raw_moves is None else list(raw_moves)
            
        # Count the valid moves
        if moves_list:
            player_obj.total_moves_made += len(moves_list)
            
        return moves_list
        
    setattr(player_obj, method_name, intercepted)
# =====================================================================

for game_num in range(args.games):
    
    current_viz = None if is_batch_run else args.viz
    sim = Simulator(map=base_map, vizfile=current_viz, framerate=args.framerate)
    
    if is_batch_run:
        sim.printInitial = False
        sim.printRoundBegin = False
        sim.printEvents = False
        sim.printMoves = False

    # Keep a secure list of the PLAYER OBJECTS to check stats later
    team_mapping = []

    for name, module_name in robot_module_names.items():
        for p in robotmodules[module_name].players:
            fresh_player = copy.deepcopy(p) 
            fresh_player.player_modname = name
            fresh_player.total_moves_made = 0
            
            # Target the specific 'move' method found in your source code
            if hasattr(fresh_player, 'move'):
                attach_tracker(fresh_player, 'move')
            else:
                print(f"CRITICAL WARNING: Could not find 'move' method for {name}!")

            sim.add_player(fresh_player)
            team_mapping.append(fresh_player) # Store the actual player object!

    if not is_batch_run:
        print(f"Running Game {game_num + 1}/{args.games}...", end="\r")
    
    # --- MUTE THE SIMULATOR PRINTS ---
    if is_batch_run:
        with open(os.devnull, 'w') as f, redirect_stdout(f):
            result = sim.play(rounds=args.number, jumps_allowed=args.allow_jumps, mine_mode=args.mine_mode.lower())
    else:
        result = sim.play(rounds=args.number, jumps_allowed=args.allow_jumps, mine_mode=args.mine_mode.lower())

    # --- TALLY THE WINNER (Checking the Simulator Vault) ---
    winner_name = None
    max_gold = -1
    
    for i, player_obj in enumerate(team_mapping):
        team_name = player_obj.player_modname 
        player_gold = 0
        
        # Dig directly into the simulator's internal data arrays
        if len(sim._status) > i:
            if hasattr(sim._status[i], 'gold'):
                player_gold = sim._status[i].gold
            elif isinstance(sim._status[i], dict):
                player_gold = sim._status[i].get('gold', 0)
        
        if player_gold > max_gold:
            max_gold = player_gold
            winner_name = team_name
        elif player_gold == max_gold:
            winner_name = "Draw/None"

    if winner_name:
        win_stats[winner_name] += 1
        
    # --- TALLY THE MOVES ---
    for player_obj in team_mapping:
        team_name = player_obj.player_modname
        move_stats[team_name] += getattr(player_obj, 'total_moves_made', 0)

# --- FINAL PRINTOUT ---
print("\n--- STATISTICAL ANALYSIS ---")
for team, wins in win_stats.items():
    win_rate = (wins / args.games) * 100
    
    if team == "Draw/None":
        print(f"Draws/Ties: {wins} games ({win_rate:.1f}%)")
    else:
        avg_moves = move_stats[team] / args.games
        print(f"{team}: {wins} wins ({win_rate:.1f}%) | Avg Moves per Game: {avg_moves:.1f}")