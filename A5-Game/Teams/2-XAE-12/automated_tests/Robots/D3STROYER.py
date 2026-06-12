# compete against the provided test players by running runRobotRace.py
# adapt the file runRobotRace.py: register your module in robot_module_names
# python3 runRobotRace.py --number 100 --viz viz.gif
# file has to be in Game folder.
# extract frames:
# ffmpeg -i viz.gif -vf "select=eq(n\,0)" -q:v 3 firstframe.png

import math
import copy
from collections import deque
from Game.game_utils import Direction as D
from Game.game_utils import TileStatus
from Game.game_utils import Map
from Game.player_base import Player
from Game.shortestpaths import AllShortestPaths


class D3STROYER(Player):

    def reset(self, player_id, max_players, width, height):
        self.player_name = "D3STROYER"
        self.ourMap = Map(width, height)

    def round_begin(self, r):
        pass
    
    def _as_direction(self,curpos,nextpos):
            for d in D:
                    diff = d.as_xy()
                    if (curpos[0] + diff[0], curpos[1] + diff[1]) ==  nextpos:
                            return d
            return None

    def _as_directions(self,curpos,path):
            return [self._as_direction(x,y) for x,y in zip([curpos]+path,path)]
    
    def _update_map(self, status):
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if status.map[x,y].status != TileStatus.Unknown:
                    self.ourMap[x,y].status = status.map[x,y].status

    def _found_gold(self, status, gx, gy):
        # returns True if gold is in visible map
        tile = status.map[gx, gy]
        return tile.status != TileStatus.Unknown 
    
    def _affordable_moves(self, gold):
        """
        How many moves can we afford?
        cost(k) = 1+2+...+k = k*(k+1)/2  ≤ gold
        Solve for largest k where k*(k+1)/2 ≤ gold.
        """
        k = 0
        while (k+1) * (k+2) // 2 <= gold:
            k += 1
        return k 
    
    @staticmethod
    def _movement_cost(distance):
        return distance * (distance + 1) // 2
    
    
    def _map_bounds(self, pos):
        x, y = pos
        
        if x < 0 or x >= self.ourMap.width:
            return False

        if y < 0 or y >= self.ourMap.height:
            return False

        return True
    
    def _adj_cells(self, pos):

        x, y = pos

        for d in D:
            dx, dy = d.as_xy()
            nxt = (x + dx, y + dy)
            if self._map_bounds(nxt):
                yield nxt
    
    def _is_frontier(self, pos):

        if self.ourMap[pos].status != TileStatus.Empty:
            return False

        for cell in self._adj_cells(pos):

            if self.ourMap[cell].status == TileStatus.Unknown:
                return True

        return False
    
    def _shortest_path_to_frontier(self, start):

        queue = deque([start])
        visited = {start}
        prev = {}

        while queue:
            cur = queue.popleft()

            if cur != start and self._is_frontier(cur):
                path = [cur]
                while cur in prev:
                    cur = prev[cur]
                    path.append(cur)
                path.reverse()

                return path

            for nxt in self._adj_cells(cur):
                if nxt in visited:
                    continue

                if self.ourMap[nxt].status != TileStatus.Empty:
                    continue

                visited.add(nxt)
                prev[nxt] = cur
                queue.append(nxt)

        return []
    

    def _best_gold_target(self, status, curpos):
        best_score = -999999
        best_gold = None
        best_path = None

        for gLoc, gold_value in status.goldPots.items():

            tempMap = copy.deepcopy(self.ourMap)
            paths = AllShortestPaths(gLoc, tempMap)

            for other_status in status.others:

                if other_status is None:
                    continue

                other_pos = (other_status.x,other_status.y)
                other_path = paths.shortestPathFrom(other_pos)

                if other_path:
                    for tile in other_path[:2]:
                        tempMap[tile].status = TileStatus.Wall
                
            paths = AllShortestPaths(gLoc, tempMap)
            path = paths.shortestPathFrom(curpos)

            if not path:
                continue

            path = path[1:]
            path.append(gLoc)

            distance = len(path)

            score = gold_value - 2 * distance
            
            for other_status in status.others:
                if other_status is None:
                    continue

                enemy_pos = (other_status.x,other_status.y)

                enemy_path = paths.shortestPathFrom(enemy_pos)

                if enemy_path:
                    enemy_distance = len(enemy_path)
                    if enemy_distance < distance:
                        score -= 25

            if score > best_score:
                best_score = score
                best_gold = gLoc
                best_path = path
            
        return best_gold, best_path

    def move(self, status):
        self._update_map(status)

        curpos = (status.x,status.y)

        assert len(status.goldPots) > 0
        gLoc, bestpath = self._best_gold_target(status, curpos)

        if bestpath is None:

            frontier_path = self._shortest_path_to_frontier(curpos)

            if len(frontier_path) > 1:
                return self._as_directions(curpos,frontier_path[1:3])

            return []

        distance = len(bestpath)

        if distance > status.goldPotRemainingRounds:
            frontier_path = self._shortest_path_to_frontier(curpos)
            if len(frontier_path) > 1:
                return self._as_directions(curpos, frontier_path[1:2])
            return []

        pot_value = status.goldPots[gLoc]

        if pot_value < distance:

            frontier_path = self._shortest_path_to_frontier(curpos)

            if len(frontier_path) > 1:

                return self._as_directions(curpos,frontier_path[1:3])

            return []
        
        max_affordable = self._affordable_moves(status.gold)

        if pot_value > 50:

            numMoves = min(5,distance,max_affordable)

        elif pot_value > 20:

            numMoves = min(3,distance,max_affordable)

        else:
            numMoves = min(2,distance,max_affordable)

        move_cost = D3STROYER._movement_cost(numMoves)

        if move_cost >= pot_value:
            numMoves = 0
        # print(status.others, file=open("status_others.txt", "a"))
        
        if numMoves == 0:
            frontier_path = self._shortest_path_to_frontier(curpos)
            
            if len(frontier_path) > 1:
                return self._as_directions(curpos,frontier_path[1:2])
            return []

        return self._as_directions(curpos,bestpath[:numMoves])

    def set_mines(self, status):
        return []

players = [ D3STROYER()]