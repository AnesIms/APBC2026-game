from game_utils import Direction as D
from game_utils import TileStatus
from game_utils import Map
from player_base import Player
import numpy as np


class BasicBot(Player):

        def __init__(self,*,random=False):
                self.random=random

        def reset(self, player_id, max_players, width, height):
                self.player_name = "GoldDigger-Bot-Basic"
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

        def move(self, status):
                
                #print("-" * 80)
                print("Status for %s" % self.player_name)
                print(status)

                curpos = (status.x,status.y)

                assert len(status.goldPots) > 0
                gLoc = next(iter(status.goldPots))

                ## move towards gold pot

                # find direction
                print("current position", curpos)
                print("gloc", gLoc)
                xDir = (gLoc[0] - curpos[0])
                yDir = (gLoc[1] - curpos[1])
                print(xDir, "xDir")
                print(yDir, "yDir")

                numMoves = 1
                
                # moves have format (newXPosition, newYPosition)
                # np.sign returns -1, 0 or 1 depending on the sign of the variable
                newX = int(curpos[0] + np.sign(xDir))
                newY = int(curpos[1] + np.sign(yDir))
                # avoid crashing into wall by staying on our current spot
                if self.check_for_obstacles(status, newX, newY):
                        move = (curpos[0], curpos[1])
                else: move = (newX, newY)                

                print(move, "move")
                # create path of size 1 (basic bot only moves 1 step at a time)
                path = [move]

                ## don't move if the pot is too far away
                # calculate manhattan distance between current position and gold pot 
                # TODO improve to account for diagonal moves
                distance = abs(xDir) + abs(yDir)
                
                if numMoves>0 and distance/numMoves > status.goldPotRemainingRounds:
                        numMoves = 0
                        print("BasicBot: Closest Pot too far -> waiting mode")

                return self._as_directions(curpos,path[:numMoves])
        
        def check_for_obstacles(self, status, x, y):
                '''
                checks a given tile for obstacles (walls & mines)
                Input: current status and x, y coordinates of tile to check
                Output: True -> obstacle on tile, False -> tile is clear, None if we cannot see the tile
                '''
                tileStatus = status.map[x, y].status
                if  tileStatus == TileStatus.Wall or tileStatus == TileStatus.Mine:
                        print("Found an obstacle")
                        return True
                elif tileStatus == TileStatus.Unknown: return None
                return False

players = [ BasicBot()]
