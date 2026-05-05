#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import random
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
        
        self.player_name = "AdlhartNaive"
        self.moves = [D.up, D.left, D.down, D.right, D.up, D.up_left, D.down_left,
						D.down_right, D.up_right]
    
        
        
    def round_begin(self, r):
        
        pass

    def set_mines(self, status):
        return []
    
    
    def get_gold_direction(self, status, x, y): 
        # get preferred directions for pot of gold
        gold_pots_coordinates = list(status.goldPots.keys())
        
        x_gold, y_gold = gold_pots_coordinates[0]
        
        distance_x = x - x_gold
        distance_y = y - y_gold
        directions = []
        if distance_x < 0: 
            directions.append(D.right)
        
            if distance_y < 0: 
                directions.append(D.up_right)
                directions.append(D.up)
            elif distance_y > 0:
                directions.append(D.down_right)
                directions.append(D.down)
         
        elif distance_x > 0 :
            directions.append(D.left)
        
            if distance_y < 0: 
                directions.append(D.up_left)
                directions.append(D.up)
            elif distance_y > 0:
                directions.append(D.down_left)
                directions.append(D.down)
            
        elif distance_x == 0: 
            if distance_y < 0: 
                directions.append( D.up )
            else: 
                directions.append(  D.down)
      
        return directions
        
    def move(self, status): 
        
        
        gold_pots_coordinates = list(status.goldPots.keys())
        x_gold, y_gold = gold_pots_coordinates[0]
        
        if abs(x_gold - status.x) + abs(y_gold - status.y) > status.gold/2:
            num_moves = 0
        else:     
            num_moves = 2
        
        
        directions = []
        newx = status.x
        newy = status.y
        
        for n in range(num_moves):
            
            # try to move closer to gold if blocked make random move
            gold_directions = self.get_gold_direction(status, newx, newy)
            
            for gold_direction in gold_directions:
                gold_x, gold_y = gold_direction.as_xy()
                
                if newx+gold_x < 0 or newx+gold_x >= self.status.map.width:
                    continue
                if newy+gold_y < 0 or newy+gold_y >= self.status.map.height:
                    continue
                
                if not status.map.__getitem__([newx+gold_x, newy+gold_y]).is_blocked():       
                    directions.append(gold_direction)
                    newx  += gold_x
                    newy  += gold_y
                    break
            
            else:
              
                indices = [i for i in range(len(self.moves))]
                random.shuffle(indices)
                
                for move_index in indices: 
                    direction = self.moves[move_index]
                    d = direction.as_xy()
                    
                    if newx+d[0] < 0 or newx+d[0] >= self.status.map.width:
                        continue
                    if newy+d[1] < 0 or newy+d[1] >= self.status.map. height:
                        continue
                         
                    if not status.map.__getitem__([newx+d[0], newy+d[1]]).is_blocked():

                        directions.append(direction)
                        newx  += d[0]
                        newy  += d[1]
                      
                        break
           
        return directions
         




class AdvancedPlayer():
    
    def reset(self, player_id, max_players, width, height):
        
        self.Directions = {( 0,  1): D.up,
			        ( 0, -1): D.down,
			        (-1,  0):D.left,
			        ( 1,  0):D.right,
			        (-1,  1): D.up_left,
			        ( 1,  1): D.up_right,
			        ( -1, -1):D.down_left,
			        ( 1, -1):D.down_right} 
        
        
        
        self.player_name = "Adlhart"
        self.ourMap = Map(width, height)
        self.jumps = self.status.params.jumps_ok
        self.distance_cutoff = 0.80
        self.other_best_paths = []
        self.last_gLoc = None
        self.wait_next_gold = False
        self.center = (int(width/2), int(height/2))
        self.numMoves = 5
    
     
    
    
    def round_begin(self, r):
        status = self.status
        
        # update map 
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                
                if status.map[x, y].status != TileStatus.Unknown:
                    self.ourMap[x, y].status = status.map[x, y].status
                    
                    # update center to some empty tile if necessary
                    if (x,y) == self.center and status.map[x, y].status != TileStatus.Empty: 
                        center_updated = False
                        j = 1
                        while center_updated == False: 
                            for xd in [-j, j, 0]: 
                                if center_updated: 
                                    break
                                for yd in [-j, j, 0]:  
                                    if status.map[x+xd, y+yd].status == TileStatus.Empty: 
                                        self.center = (x+xd, y+yd)
                                        center_updated = True
                                        break
                            j+=1
                            
        for other in self.status.others: 
            if other != None:
                x,y = (other.x, other.y)
                self.ourMap[x, y].status = TileStatus.Wall
                
                
    def set_mines(self, status):
        
        mines = []
        return mines  
          
            
    def get_neighbors(self, position, include_jumps = True, include_unknown = True): 
        """ get neighbors of position """
        
        if include_unknown: 
            open_fields = ['.', '_']
            
        else: 
            open_fileds = ['.']
        
        neighbors = []
        
        for j in [-1, 1, 0]: 
            for i in [1, -1, 0]: 
                if i != 0 or j != 0:
                    
                    xnew = position[0]+i
                    ynew = position[1]+j
                    
                    if self.check_map_boundaries((xnew, ynew)):
                        neighbor_status = self.ourMap[xnew, ynew].status   
                        if str(neighbor_status) in open_fields: 
                            neighbors.append((xnew, ynew))
                        
                        if include_jumps:
                            if str(neighbor_status) == "#": 
                                if self.check_map_boundaries((xnew+i, ynew+j)):
                                    if str(self.ourMap[xnew+i, ynew+j]) in open_fields: 
                                        neighbors.append((xnew+i, ynew+j))
   
        return neighbors                
        
    def check_map_boundaries(self, position): 
        """check if position exists on map """

        x, y = position 

        if x >= 0 and y >= 0 and x < self.ourMap.width and y < self.ourMap.height:   
            return True
        
        else: 
            return False             
            
       
        
    
      
    def check_others(self):
        """get one shortest path of other players """
        # get shortest paths of all other visible players
        gLoc = list(self.status.goldPots.keys())[0]   
        other_paths = []
         
        for other in self.status.others: 
            if other != None:
                position_other = (other.x, other.y)
                distances, p = self.get_shortest_distances(position_other, include_jumps=False)
                best_path = self.get_path(p, gLoc)
                other_paths.append(best_path)
                
                 
        return other_paths      
     
    def get_shortest_distances(self, start, include_jumps=True, get_all =True):
        """ get shortest distance to all nodes """
        height = self.ourMap.height
        width = self.ourMap.width
        shape = (width, height)
        
        distances = np.full(shape, np.inf)
        
        
        distances[start] = 0
        predecessors = {}
        
        que = deque([start])
        
        while len(que) != 0: 
            
            current_node = que.popleft()
            current_length = distances[current_node]
            
            neighbors = self.get_neighbors(current_node, include_jumps)
           
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
        """ get a shortest path from predecessors """
        
        path = [target] 
        current_node = target
        while current_node in p: 
            current_node = random.choice(p[current_node])
            path.append(current_node)
            
        return path[::-1]
        

             
    def path_cost(self, path):
        """ evaluate cost of path """
        n_moves = 0
        jumps = 0
        cost = 0
        current_node = path[0]
    
        for i in range(1, len(path)): 
            next_node = path[i]
            x_diff = next_node[0] - current_node[0]
            y_diff = next_node[1] - current_node[1]
           
            if abs(x_diff) == 2 or abs(y_diff) == 2: 
                jumps +=1
                n_moves +=1
                cost += n_moves + 5
                
            else: 
                n_moves +=1
                cost += n_moves
                
            current_node = next_node    
            
        return cost  
    
    def move(self, status): 
                                           
        self.numMoves = 5
        self.other_paths = self.check_others()
        
        
        curpos = (status.x,status.y)  
        budget = status.gold
        gAmount = list(status.goldPots.values())[0]
        gLoc = list(status.goldPots.keys())[0]   
        
        
        # check if gold has moved and reset waiting
        if self.last_gLoc and gLoc != self.last_gLoc:
            self.wait_next_gold = False   
        self.last_gLoc = gLoc
      
       
        # get shortest path  lengths to gold including and excluding jumps  
        distances, p = self.get_shortest_distances(curpos, include_jumps=False)
        min_distance = distances[gLoc]
        best_path = self.get_path(p, gLoc)
        cost_full_path = self.path_cost(best_path)
        
        if self.jumps:
            jumping_distances, pj = self.get_shortest_distances(curpos, include_jumps=True)
            best_jumping_path = self.get_path(pj, gLoc)
            cost_full_jumping_path = self.path_cost(best_jumping_path)
            
    
            # choose jumping route if gain > 30 and less cost than without jumps
            if cost_full_path > cost_full_jumping_path and gAmount - cost_full_jumping_path > 30: 
                best_path = best_jumping_path
                cost_full_path = cost_full_jumping_path
                min_distance = jumping_distances[gLoc]
                
                
        
        # check if others closer than cutoff to gold than myself, if possible
        if len(self.other_paths) > 0:
            min_other_distances = min([len(x) for x in self.other_paths])
            # wait if others close
            if min_other_distances < min_distance * self.distance_cutoff : 
                self.wait_next_gold = True
                
               
        # wait for next gold if too far away
        if min_distance/self.numMoves > status.goldPotRemainingRounds:
                self.numMoves = 0
                self.wait_next_gold = True
              
        
              
        
        # if waiting for next gold, change path to center in steps of 2
        if self.wait_next_gold: 
            self.numMoves = 2
            if curpos != self.center:
                distances, p = self.get_shortest_distances(curpos, include_jumps=False)
                best_path = self.get_path(p, self.center) 
            else:
                best_path = []
            
        else: 
            # go directly for gold if gain more than 30 and in budget 
            if cost_full_path < budget and gAmount-cost_full_path > 30: 
               self.numMoves = len(best_path)-1
               
            else: 
               # switch to no jumping path if not going directly
               if self.jumps:
                   best_path= self.get_path(p, gLoc)

        

    
        # get moves
        next_node = curpos
        best_path = best_path[1:]
        moves = []
        stop_path = False
        cost = 0
        
        for i in range(min(self.numMoves, len(best_path))):
          
            current_node = next_node
            next_node = best_path[i]
            
            x_diff = next_node[0] - current_node[0]
            y_diff = next_node[1] - current_node[1]
            
            # stop if tile not empty
            if self.ourMap[next_node[0], next_node[1]].status == TileStatus.Empty:
              
                # check if my path on others shortest path and stop if other is closer
                if len(self.other_paths) != 0:
                    for x in self.other_paths: 
                        if next_node in x: 
                            if x.index(next_node)-1 <= i: 
                                stop_path = True
                                break
            
                # get directions
                if abs(x_diff) == 2 or abs(y_diff) == 2: 
                    direction = self.Directions[(x_diff/2, y_diff/2)]
                    tmp_directions = [direction, direction]
                    cost += i + 1 + 5
                else: 
                    direction = self.Directions[(x_diff, y_diff)]
                    tmp_directions = [direction]
                    cost += i+1
                  
            else: 
                stop_path = True
                
            if stop_path == True:
                break
            
            else: 
                if cost < budget:
                    moves.extend(tmp_directions)
                else: 
                    stop_path = True 
      
        return moves
    
    
players = [ AdvancedPlayer()]