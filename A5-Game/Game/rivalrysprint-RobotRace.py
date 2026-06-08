#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
import math
from game_utils import nameFromPlayerId
from game_utils import Direction as D, MoveStatus
from game_utils import Tile, TileStatus, TileObject
from game_utils import Map, Status
from simulator import Simulator
from player_base import Player
from shortestpaths import AllShortestPaths
from collections import deque
import numpy as np 

class NaivePlayer(Player):
    def reset(self, player_id, max_players, width, height):
        self.player_name = "RivalrySprint"
        self.Directions = {( 0,  1): D.up,
                    ( 0, -1): D.down,
                    (-1,  0):D.left,
                    ( 1,  0):D.right,
                    (-1,  1): D.up_left,
                    ( 1,  1): D.up_right,
                    ( -1, -1):D.down_left,
                    ( 1, -1):D.down_right} 

        self.ourMap = Map(width, height)
        self.enemy_history = {}
        
        self.player_id = player_id
        self.max_players = max_players
        
        self.estimated_scores = {i: 100 for i in range(max_players)}
        self.last_pots = {}
        self.last_my_pos = (0, 0)
        
    def round_begin(self, r):
        pass

    def set_mines(self, status):
        return []
    
    #------------------------------------------------
    # Enemy Tracker & Speed Calculator
    #------------------------------------------------
    def update_enemy_tracker(self, status):
        for other in status.others:
            if other is not None:
                curr_pos = (other.x, other.y)
                player_id = other.player
                
                if player_id in self.enemy_history:
                    last_pos = self.enemy_history[player_id]['last_pos']
                    dist_moved = abs(curr_pos[0] - last_pos[0]) + abs(curr_pos[1] - last_pos[1])
                    
                    if dist_moved <= 6:
                        old_avg = self.enemy_history[player_id]['avg_speed']
                        new_avg = (0.5 * old_avg) + (0.5 * dist_moved)
                        self.enemy_history[player_id]['avg_speed'] = new_avg
                    
                    self.enemy_history[player_id]['last_pos'] = curr_pos
                else:
                    self.enemy_history[player_id] = {'last_pos': curr_pos, 'avg_speed': 2.0}

    #------------------------------------------------
    # Dynamic Sprint & RIVALRY Calculator
    #------------------------------------------------
    def calculate_sprint(self, best_path, other_paths, budget, gAmount, rivalry_mode):
        print(rivalry_mode)
        distance_to_gold = len(best_path) - 1
        fastest_enemy_eta = float('inf')
        closest_enemy_dist = float('inf') 
        
        for enemy_id, e_path in other_paths:
            e_dist = len(e_path) - 1 
            speed = self.enemy_history.get(enemy_id, {}).get('avg_speed', 2.0)
            eta = e_dist / max(0.1, speed) 
            
            if eta < fastest_enemy_eta:
                fastest_enemy_eta = eta
            
            # Record the absolute closest physical threat
            if e_dist < closest_enemy_dist:
                closest_enemy_dist = e_dist
                
        # If we are in Rivalry mode but NO enemies are visible, assume the worst.
        if rivalry_mode and fastest_enemy_eta == float('inf'):
            fastest_enemy_eta = 1.0
            closest_enemy_dist = 1 # Assume they are 1 step away
        
        # If the enemy gets there THIS round (ETA <= 1), and they require fewer 
        # steps than us, they will grab the gold on an earlier sub-step.
        # It is physically impossible to beat them. Abort the race immediately!
        if fastest_enemy_eta <= 1.0 and closest_enemy_dist <= distance_to_gold:
            return False, 0
        
        our_normal_eta = distance_to_gold / 2.0
        
        if fastest_enemy_eta <= our_normal_eta:
            target_eta = max(1.0, fastest_enemy_eta - 1.0)
            desired_moves = math.ceil(distance_to_gold / target_eta)
            
            sprint_cost = (desired_moves * (desired_moves + 1)) // 2
            expected_profit = gAmount - sprint_cost
            
            min_profit = 0 if rivalry_mode else 1
            
            if expected_profit >= min_profit and sprint_cost <= budget:
                return True, desired_moves
            else:
                return False, 0 
        else:
            if budget > 100 and distance_to_gold <= 5:
                return True, distance_to_gold
            elif budget > 100:
                return True, 4
            return True, 2

    #------------------------------------------------
    # Map Boundaries & Neighbors
    #------------------------------------------------
    def check_map_boundaries(self, position): 
        x, y = position 
        if 0 <= x < self.ourMap.width and 0 <= y < self.ourMap.height:   
            return True
        return False   

    def get_neighbors(self, position): 
        x, y = position
        open_fields = ['.', '_']
        neighbors = []
        for dx, dy in self.Directions.keys(): 
            nx, ny = x + dx, y + dy
            if self.check_map_boundaries((nx, ny)):
                if hasattr(self, 'current_enemies') and (nx, ny) in self.current_enemies:
                    continue 
                neighbor_status = str(self.ourMap[nx, ny].status)
                if neighbor_status in open_fields: 
                    neighbors.append((nx, ny))
        return neighbors  

    #------------------------------------------------
    # Shortest Paths
    #------------------------------------------------
    def get_shortest_distances(self, start, get_all=True):
        height = self.ourMap.height
        width = self.ourMap.width
        distances = np.full((width, height), np.inf)
        distances[start] = 0
        predecessors = {}
        
        que = deque([start])
        while len(que) != 0: 
            current_node = que.popleft()
            current_length = distances[current_node]
            neighbors = self.get_neighbors(current_node)
            
            for n in neighbors: 
                if current_length + 1 < distances[n]: 
                    distances[n] = current_length + 1
                    que.append(n)
                    predecessors[n] = [current_node]
                elif current_length + 1 == distances[n]:
                    if get_all:
                       predecessors[n].append(current_node)
        return distances, predecessors
    
    def get_path(self, p, target): 
        path = [target] 
        current_node = target
        while current_node in p: 
            current_node = random.choice(p[current_node])
            path.append(current_node)
        return path[::-1]
        
    def path_cost(self, path):
        n_moves = 0
        cost = 0
        for i in range(1, len(path)): 
            n_moves += 1
            cost += n_moves
        return cost  

    def check_others(self, status):
        if not status.goldPots:
            return []
        gLoc = list(status.goldPots.keys())[0]   
        other_paths = []
         
        for other in status.others: 
            if other != None:
                position_other = (other.x, other.y)
                distances, p = self.get_shortest_distances(position_other)
                best_path = self.get_path(p, gLoc)
                other_paths.append((other.player, best_path))
        return other_paths  
   
    #------------------------------------------------
    # Main Move Function
    #------------------------------------------------
    def move(self, status): 
        # ---  THE SHADOW SCOREBOARD ---
        if hasattr(self, 'last_pots') and self.last_pots:
            for loc, amount in self.last_pots.items():
                if not status.goldPots or loc not in status.goldPots:
                    grabbed_by = None
                    
                    if status.others:
                        for other in status.others:
                            if other is not None:
                                # They must be standing on or right next to the pot's location THIS round
                                dist_to_vanished_pot = abs(other.x - loc[0]) + abs(other.y - loc[1])
                                if dist_to_vanished_pot <= 2:
                                    grabbed_by = other.player
                                    break
                    
                    if grabbed_by is not None:
                        self.estimated_scores[grabbed_by] += (amount - 5)
        
        # Sync our actual score and prep for next round
        self.estimated_scores[self.player_id] = status.gold
        self.last_pots = status.goldPots.copy() if status.goldPots else {}
        self.last_my_pos = (status.x, status.y)

        if not status.goldPots:
            return []

        self.update_enemy_tracker(status)
        
        self.current_enemies = set()
        for other in status.others:
            if other is not None:
                self.current_enemies.add((other.x, other.y))

        ourMap = self.ourMap
        curpos = (status.x, status.y)  
        budget = status.gold
        gLoc = list(status.goldPots.keys())[0]  
        gAmount = status.goldPots[gLoc]

        for x in range(ourMap.width):
            for y in range(ourMap.height):
                if status.map[x, y].status != TileStatus.Unknown:
                    ourMap[x, y].status = status.map[x, y].status
        
        distances, p = self.get_shortest_distances(curpos)
        exact_distance_to_gold = distances[gLoc]

        chasing_gold = True
        if (exact_distance_to_gold / 2) > status.goldPotRemainingRounds:
            chasing_gold = False

        # --- IDENTIFY THE RIVAL ---
        rival_id = None
        rival_score = -1
        for p_id, score in self.estimated_scores.items():
            if p_id != self.player_id and score > rival_score:
                rival_score = score
                rival_id = p_id
                
        # Are they beating us?
        rivalry_mode = False
        if rival_score > budget:
            rivalry_mode = True 

        other_paths = []
        if chasing_gold:
            best_path = self.get_path(p, gLoc)
            other_paths = self.check_others(status)

            # Pass the rivalry_mode flag into the sprint calculator!
            chasing_gold, num_moves = self.calculate_sprint(
                best_path, other_paths, budget, gAmount, rivalry_mode
            )

        if not chasing_gold:
            center_loc = (ourMap.width // 2, ourMap.height // 2)
            
            if center_loc in p or center_loc == curpos:
                best_path = self.get_path(p, center_loc)
            else:
                best_path = [curpos] 
            
            if budget >= 1:
                num_moves = 1
            else:
                num_moves = 0

        next_node = curpos
        best_path = best_path[1:]
        moves = []

        for i in range(min(num_moves, len(best_path))):
            current_node = next_node
            next_node = best_path[i]
            
            stop_path = False
            if other_paths:
                for enemy_id, e_path in other_paths:
                    if next_node in e_path:
                        if e_path.index(next_node) <= i + 1: 
                            stop_path = True
                            break
            
            if stop_path:
                break 

            x_diff = next_node[0] - current_node[0]
            y_diff = next_node[1] - current_node[1]
            
            if self.ourMap[next_node[0], next_node[1]].status == TileStatus.Empty:
                moves.append(self.Directions[(x_diff, y_diff)])

        return moves
    
players = [NaivePlayer()]