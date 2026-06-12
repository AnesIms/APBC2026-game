#!/usr/bin/env python3
import copy
import math
import random
import argparse
import sys
import os
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

# Add your robot player here
robot_module_names = {"MyPlayer":"group4",
                      "StrategyThreeOneBot":"XAE-12-S3_1",
                      "NaivePlayer":"rivalrysprint-RobotRace",
                      "StrategyFiveBot": "XAE-12-S5",
                      "D3STROYER": "D3STROYER",
                      }


# Ensure that the robot is the correct directory. It will search for a subdirectory from the local script directory
# In this case the subdirectory from the local script directory is "Robots"
script_dir = os.path.dirname(os.path.realpath(__file__))
robots_dir = os.path.join(script_dir, 'Robots')
sys.path.insert(0, robots_dir)

robotmodules = { m:__import__(m) for m in robot_module_names.values() }

if args.map is not None:
   base_map = Map.read(args.map)
else:
   base_map = Map.makeRandom(30, 30, args.density)

win_stats = {name: 0 for name in robot_module_names.keys()}
win_stats["Draw/None"] = 0
move_stats = {name: 0 for name in robot_module_names.keys()}

health_stats = {name: 0 for name in robot_module_names.keys()}
distance_stats = {name: 0 for name in robot_module_names.keys()}
gold_stats = {name: 0 for name in robot_module_names.keys()}

is_batch_run = args.games > 1

if is_batch_run:
    print(f"Starting {args.games} games silently... Please wait.")

def attach_tracker(player_obj, method_name):
    original_brain = getattr(player_obj, method_name)
    
    def intercepted(*args, **kwargs):
        status = None
        for arg in args:
            if hasattr(arg, 'x') and hasattr(arg, 'y'):
                status = arg
                break
        if not status and 'status' in kwargs:
            status = kwargs['status']
            
        if status:
            if player_obj.last_pos is not None:
                dx = status.x - player_obj.last_pos[0]
                dy = status.y - player_obj.last_pos[1]
                distance = math.sqrt(dx**2 + dy**2)
                player_obj.total_distance += distance
            
            player_obj.last_pos = (status.x, status.y)

        raw_moves = original_brain(*args, **kwargs)
        moves_list = [] if raw_moves is None else list(raw_moves)
            
        if moves_list:
            player_obj.total_moves_made += len(moves_list)
            
        return moves_list
        
    setattr(player_obj, method_name, intercepted)

for game_num in range(args.games):
    
    current_viz = None if is_batch_run else args.viz
    sim = Simulator(map=base_map, vizfile=current_viz, framerate=args.framerate)
    
	# This doesn't silence all output, but it will silence the print statements from the Simulator when running in batch mode
    if is_batch_run:
        sim.printInitial = False
        sim.printRoundBegin = False
        sim.printEvents = False
        sim.printMoves = False

    team_mapping = []

    for name, module_name in robot_module_names.items():
        for p in robotmodules[module_name].players:
            fresh_player = copy.deepcopy(p) 
            fresh_player.player_modname = name
            
            # Initialization
            fresh_player.total_moves_made = 0
            fresh_player.total_distance = 0.0  
            fresh_player.gold_collected = 0
            fresh_player.last_pos = None      
            
            if hasattr(fresh_player, 'move'):
                attach_tracker(fresh_player, 'move')

            sim.add_player(fresh_player)
            team_mapping.append(fresh_player)

    if not is_batch_run:
        print(f"Running Game {game_num + 1}/{args.games}...", end="\r")
    
    if is_batch_run:
		# redirect_stdout silences all print outputs that are still remaining from other modules
        with open(os.devnull, 'w') as f, redirect_stdout(f):
            result = sim.play(rounds=args.number, jumps_allowed=args.allow_jumps, mine_mode=args.mine_mode.lower())
    else:
        result = sim.play(rounds=args.number, jumps_allowed=args.allow_jumps, mine_mode=args.mine_mode.lower())

    winner_name = None
    max_gold = -1
    
    for i, player_obj in enumerate(team_mapping):
        team_name = player_obj.player_modname 
        player_gold = 0
        player_health = 0
        
        if len(sim._status) > i:
            status = sim._status[i]
            player_gold = status.gold
            player_health = status.health  

        if player_gold > max_gold:
            max_gold = player_gold
            winner_name = team_name

        elif player_gold == max_gold:
            winner_name = "Draw/None"
            
        health_stats[team_name] += player_health
        distance_stats[team_name] += player_obj.total_distance
        gold_stats[team_name] += player_gold

    if winner_name:
        win_stats[winner_name] += 1
        
    for player_obj in team_mapping:
        team_name = player_obj.player_modname
        move_stats[team_name] += player_obj.total_moves_made

print("\n--- STATISTICAL ANALYSIS ---\n")
for team, wins in win_stats.items():
    win_rate = (wins / args.games) * 100
    
    if team == "Draw/None":
        print(f"Draws/Ties: {wins} games ({win_rate:.1f}%)\n")
    else:
        avg_moves = move_stats[team] / args.games
        avg_health = health_stats[team] / args.games
        avg_distance = distance_stats[team] / args.games
        avg_gold = gold_stats[team] / args.games

        print(f"{team}: {wins} wins ({win_rate:.1f}%) | "
              f"Avg Gold: {avg_gold:.1f} | "
              f"Avg Distance: {avg_distance:.1f} | "
              f"Avg Moves: {avg_moves:.1f} | "
              f"Avg Health: {avg_health:.1f}\n")